"""Phase 6: absolute-prediction quality research.

This module stays focused on ABSOLUTE stock direction / return prediction.
It never introduces relative-return, ranking, or peer-outperform targets --
`target_class_*` and `target_return_*` always describe one stock's own
future move, exactly as in Phase 5.

It extends (does not replace) stock_ai/ml/phase5.py and
stock_ai/ml/signal_research.py: horizon-specific and volatility-adjusted
absolute targets, feature sets, and chronological splitting are reused as-is.
New work added here:

  * calibration auditing (reliability tables, sigmoid/isotonic calibration)
  * strong-move absolute binary classification (STRONG_UP vs STRONG_DOWN)
  * separate UP-vs-rest / DOWN-vs-rest binary classifiers
  * a setup-quality filter combined with confidence thresholds
  * regression target transforms (winsorized, signed-log) + target-price accuracy
  * recency sample weighting, ticker-identity one-hot, per-stock models
  * regime slicing (trend / volatility) and walk-forward stability
  * simple baselines models must beat to be called useful
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.calibration import CalibratedClassifierCV
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.utils.class_weight import compute_sample_weight
from sqlalchemy.orm import Session

from stock_ai.features.dataset import build_feature_dataset
from stock_ai.features.context import add_context_features
from stock_ai.features.targets import DEFAULT_HORIZONS
from stock_ai.ml.config import CLASS_LABELS
from stock_ai.ml.evaluation import class_distribution, classification_metrics, regression_metrics
from stock_ai.ml.feature_pruning import prune_features
from stock_ai.ml.phase5 import HORIZON_SPECIFIC_THRESHOLDS, TARGET_MODES, add_phase5_targets, load_prices_for_tickers
from stock_ai.ml.preprocessing import select_model_feature_columns
from stock_ai.ml.signal_research import PreparedSplit, _backtest_frame, _decode, _predict_proba, prepare_split
from stock_ai.ml.signals import residual_uncertainty, select_signal_threshold, threshold_table
from stock_ai.ml.split import chronological_split
from stock_ai.universe import FOCUS_STOCKS, REFERENCE_ASSETS, REFERENCE_UNIVERSE


try:
    from xgboost import XGBClassifier, XGBRegressor
except Exception:  # pragma: no cover
    XGBClassifier = None
    XGBRegressor = None


SHORT_HORIZONS = ("5d", "10d", "15d")
SKIP_PER_STOCK_UNLESS_SUFFICIENT = ("SNDK", "PONY", "RDDT")
MIN_PER_STOCK_TRAIN_ROWS = 400
MIN_PER_STOCK_TEST_ROWS = 25
STRONG_MOVE_MULTIPLIER = 1.5
RECENCY_HALF_LIFE_DAYS = 504  # ~2 trading years
CALIBRATION_BUCKETS = ((0.50, 0.60), (0.60, 0.70), (0.70, 0.80), (0.80, 1.0001))
SETUP_QUALITY_COLUMNS = ("adx_14", "trend_clarity", "pressure_imbalance", "relative_volume")


def run_phase6_research(db: Session, horizons: tuple[str, ...] = SHORT_HORIZONS, min_signal_samples: int = 30) -> dict:
    prices, price_summary = load_prices_for_tickers(db, REFERENCE_UNIVERSE)
    base = _build_base_features(prices)
    training_tickers = [ticker for ticker in REFERENCE_UNIVERSE if ticker not in REFERENCE_ASSETS]
    target_datasets = {mode: add_phase5_targets(base, target_mode=mode) for mode in TARGET_MODES}

    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "product_scope": "absolute_stock_prediction_only",
        "focus_stocks": list(FOCUS_STOCKS),
        "horizons": list(horizons),
        "price_summary": price_summary,
        "target_modes": {},
        "baselines": {},
        "strong_move_binary": {},
        "separate_up_down_classifiers": {},
        "regression": {},
        "calibration": {},
        "setup_quality_and_confidence_filter": {},
        "regime_slicing": {},
        "recency_weighting": {},
        "stock_identity_feature": {},
        "per_stock_models": {},
        "walk_forward": {},
    }

    prepared_cache: dict[tuple[str, str], PreparedSplit] = {}

    for mode in TARGET_MODES:
        report["target_modes"][mode] = {}
        for horizon in horizons:
            prepared = prepare_split(target_datasets[mode], horizon)
            prepared_cache[(mode, horizon)] = prepared
            model_results, bundles = train_and_eval_classifiers(prepared, horizon, min_signal_samples=min_signal_samples)
            report["target_modes"][mode][horizon] = {
                "class_distribution": class_distribution(target_datasets[mode][f"target_class_{horizon}"].dropna()),
                "row_count": int(len(prepared.dataset)),
                "split": _split_summary(prepared),
                "models": model_results,
            }
            if mode == "fixed_3pct":
                report["target_modes"][mode][horizon]["_bundles"] = bundles  # stripped before saving

    # --- Section 28: simple baselines (fixed_3pct target) ---
    for horizon in horizons:
        report["baselines"][horizon] = compute_baselines(prepared_cache[("fixed_3pct", horizon)])

    # --- Section 7: strong-move absolute binary classification ---
    for horizon in horizons:
        report["strong_move_binary"][horizon] = strong_move_experiment(target_datasets["horizon_specific"], horizon)

    # --- Section 17: separate UP-vs-rest / DOWN-vs-rest classifiers ---
    for horizon in horizons:
        prepared = prepared_cache[("fixed_3pct", horizon)]
        multiclass_rf = report["target_modes"]["fixed_3pct"][horizon]["models"]["random_forest"]["test"]["class_metrics"]
        report["separate_up_down_classifiers"][horizon] = separate_up_down_experiment(prepared, multiclass_rf)

    # --- Sections 8-11, 22, 23: regression, transforms, outliers, target price ---
    for horizon in horizons:
        report["regression"][horizon] = regression_experiment(prepared_cache[("fixed_3pct", horizon)], horizon)

    # --- Section 15: calibration audit ---
    # --- Section 14/16: setup quality + confidence filter grid ---
    # --- Section 13/12: regime slicing ---
    # --- Section 21: walk-forward stability ---
    for horizon in horizons:
        prepared = prepared_cache[("fixed_3pct", horizon)]
        bundle = report["target_modes"]["fixed_3pct"][horizon].pop("_bundles")["random_forest"]
        report["calibration"][horizon] = calibration_experiment(bundle["model"], prepared)
        report["setup_quality_and_confidence_filter"][horizon] = setup_quality_experiment(prepared, bundle, horizon)
        report["regime_slicing"][horizon] = regime_experiment(prepared, bundle["test_backtest"])
        report["walk_forward"][horizon] = temporal_stability(bundle["test_backtest"], bundle["threshold"])
    for mode in TARGET_MODES:
        for horizon in horizons:
            report["target_modes"][mode][horizon].pop("_bundles", None)

    # --- Section 20: recency weighting ---
    for horizon in horizons:
        report["recency_weighting"][horizon] = recency_weighting_experiment(prepared_cache[("fixed_3pct", horizon)])

    # --- Section 19: ticker identity feature ---
    for horizon in horizons:
        report["stock_identity_feature"][horizon] = stock_identity_experiment(prepared_cache[("fixed_3pct", horizon)])

    # --- Section 18: per-stock vs global models ---
    for horizon in horizons:
        report["per_stock_models"][horizon] = per_stock_experiment(prepared_cache[("fixed_3pct", horizon)])

    report["assessment"] = assess_report(report)
    return report


# ---------------------------------------------------------------------------
# Feature construction
# ---------------------------------------------------------------------------

def _build_base_features(prices: pd.DataFrame) -> pd.DataFrame:
    base = build_feature_dataset(prices, include_targets=False, include_price_action=True)
    dataset = add_context_features(base, prices)
    training_tickers = [ticker for ticker in REFERENCE_UNIVERSE if ticker not in REFERENCE_ASSETS]
    return dataset[dataset["ticker"].isin(training_tickers)].sort_values(["ticker", "date"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Section 3/4/5/6: classification model comparison per target mode
# ---------------------------------------------------------------------------

def train_and_eval_classifiers(prepared: PreparedSplit, horizon: str, min_signal_samples: int) -> tuple[dict, dict]:
    candidates: list[tuple[str, Any, np.ndarray | None]] = [
        ("dummy", DummyClassifier(strategy="most_frequent"), None),
        ("logistic_balanced", LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42), None),
        (
            "random_forest",
            RandomForestClassifier(
                n_estimators=200,
                max_depth=8,
                min_samples_leaf=5,
                max_features="sqrt",
                class_weight="balanced",
                random_state=42,
                n_jobs=-1,
            ),
            None,
        ),
    ]
    if XGBClassifier is not None:
        weights = compute_sample_weight("balanced", prepared.y_train_class)
        candidates.append(
            (
                "xgboost",
                XGBClassifier(
                    objective="multi:softprob",
                    eval_metric="mlogloss",
                    n_estimators=200,
                    max_depth=3,
                    learning_rate=0.05,
                    subsample=0.85,
                    colsample_bytree=0.85,
                    tree_method="hist",
                    random_state=42,
                    n_jobs=2,
                ),
                weights,
            )
        )

    results: dict[str, dict] = {}
    bundles: dict[str, dict] = {}
    for name, model, weight in candidates:
        if weight is not None:
            model.fit(prepared.X_train, prepared.y_train_class, sample_weight=weight)
        else:
            model.fit(prepared.X_train, prepared.y_train_class)

        val_proba = _predict_proba(model, prepared.X_validation, len(prepared.labels))
        test_proba = _predict_proba(model, prepared.X_test, len(prepared.labels))
        val_pred = val_proba.argmax(axis=1)
        test_pred = test_proba.argmax(axis=1)
        val_backtest = _backtest_frame(prepared.validation, horizon, val_pred, val_proba, np.zeros(len(val_pred)), prepared.labels)
        test_backtest = _backtest_frame(prepared.test, horizon, test_pred, test_proba, np.zeros(len(test_pred)), prepared.labels)
        threshold_selection = select_signal_threshold(val_backtest, min_samples=min_signal_samples)
        selected_threshold = threshold_selection["threshold"]
        test_table = threshold_table(test_backtest)

        results[name] = {
            "validation": classification_metrics(
                _decode(prepared.y_validation_class, prepared.labels), _decode(val_pred, prepared.labels), val_proba, labels=prepared.labels
            ),
            "test": classification_metrics(
                _decode(prepared.y_test_class, prepared.labels), _decode(test_pred, prepared.labels), test_proba, labels=prepared.labels
            ),
            "selected_threshold": threshold_selection,
            "test_threshold_table": test_table,
            "test_at_selected_threshold": test_table.get(f"{selected_threshold:.2f}", {}),
        }
        bundles[name] = {
            "model": model,
            "val_proba": val_proba,
            "test_proba": test_proba,
            "test_backtest": test_backtest,
            "threshold": selected_threshold,
        }

    return results, bundles


# ---------------------------------------------------------------------------
# Section 28: simple baselines
# ---------------------------------------------------------------------------

def compute_baselines(prepared: PreparedSplit) -> dict:
    actual = _decode(prepared.y_test_class, prepared.labels)
    train_actual = _decode(prepared.y_train_class, prepared.labels)
    dominant = pd.Series(train_actual).value_counts().idxmax()
    dominant_pred = np.full(len(actual), dominant)

    momentum_col = "return_10d" if "return_10d" in prepared.test.columns else "return_20d"
    momentum = pd.to_numeric(prepared.test.get(momentum_col), errors="coerce").to_numpy()
    momentum_pred = np.where(momentum > 0, "UP", np.where(momentum < 0, "DOWN", "NEUTRAL"))

    ma_flag = pd.to_numeric(prepared.test.get("price_above_sma50"), errors="coerce").to_numpy()
    ma_pred = np.where(ma_flag == 1, "UP", np.where(ma_flag == 0, "DOWN", "NEUTRAL"))

    def summarize(pred: np.ndarray) -> dict:
        return {
            "accuracy": float(accuracy_score(actual, pred)),
            "balanced_accuracy": float(balanced_accuracy_score(actual, pred)) if len(set(actual)) > 1 else float("nan"),
        }

    return {
        "dominant_class": {"class": str(dominant), **summarize(dominant_pred)},
        "momentum_rule": {"feature_used": momentum_col, **summarize(momentum_pred)},
        "moving_average_rule": {"feature_used": "price_above_sma50", **summarize(ma_pred)},
    }


# ---------------------------------------------------------------------------
# Section 7: strong-move absolute binary classification
# ---------------------------------------------------------------------------

def strong_move_experiment(dataset: pd.DataFrame, horizon: str, multiplier: float = STRONG_MOVE_MULTIPLIER) -> dict:
    thresholds = HORIZON_SPECIFIC_THRESHOLDS[horizon]
    strong_up = thresholds.up * multiplier
    strong_down = thresholds.down * multiplier

    working = dataset.dropna(subset=[f"target_return_{horizon}"]).copy()
    returns = pd.to_numeric(working[f"target_return_{horizon}"], errors="coerce")
    label = np.select([returns > strong_up, returns < strong_down], ["STRONG_UP", "STRONG_DOWN"], default=None)
    working["strong_label"] = label
    filtered = working.dropna(subset=["strong_label"]).copy()
    coverage = float(len(filtered) / len(working)) if len(working) else float("nan")

    if len(filtered) < 150 or filtered["strong_label"].nunique() < 2:
        return {"status": "INSUFFICIENT_SAMPLE", "sample_count": int(len(filtered)), "coverage_of_all_moves": coverage}

    split = chronological_split(filtered, purge_gap=DEFAULT_HORIZONS[horizon])
    feature_columns = select_model_feature_columns(split.train)
    kept, _ = prune_features(split.train, feature_columns)
    preprocessor = Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())])
    X_train = pd.DataFrame(preprocessor.fit_transform(_clean(split.train[kept])), columns=kept, index=split.train.index)
    X_test = pd.DataFrame(preprocessor.transform(_clean(split.test[kept])), columns=kept, index=split.test.index)
    y_train = (split.train["strong_label"] == "STRONG_UP").astype(int).to_numpy()
    y_test = (split.test["strong_label"] == "STRONG_UP").astype(int).to_numpy()

    if len(np.unique(y_train)) < 2 or len(y_test) < 20 or len(np.unique(y_test)) < 2:
        return {
            "status": "INSUFFICIENT_TEST_SAMPLE",
            "sample_count": int(len(filtered)),
            "coverage_of_all_moves": coverage,
            "train_rows": int(len(split.train)),
            "test_rows": int(len(split.test)),
        }

    model = RandomForestClassifier(
        n_estimators=200, max_depth=6, min_samples_leaf=5, class_weight="balanced", random_state=42, n_jobs=-1
    )
    model.fit(X_train, y_train)
    pred = model.predict(X_test)

    return {
        "status": "OK",
        "strong_up_threshold": float(strong_up),
        "strong_down_threshold": float(strong_down),
        "sample_count": int(len(filtered)),
        "coverage_of_all_moves": coverage,
        "train_rows": int(len(split.train)),
        "test_rows": int(len(split.test)),
        "accuracy": float(accuracy_score(y_test, pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_test, pred)),
        "up_precision": float(precision_score(y_test, pred, pos_label=1, zero_division=0)),
        "down_precision": float(precision_score(y_test, pred, pos_label=0, zero_division=0)),
        "f1": float(f1_score(y_test, pred, zero_division=0)),
    }


# ---------------------------------------------------------------------------
# Section 17: separate UP-vs-rest and DOWN-vs-rest classifiers
# ---------------------------------------------------------------------------

def separate_up_down_experiment(prepared: PreparedSplit, multiclass_test_class_metrics: dict) -> dict:
    up_index = prepared.labels.index("UP")
    down_index = prepared.labels.index("DOWN")

    y_up_train = (prepared.y_train_class == up_index).astype(int)
    y_down_train = (prepared.y_train_class == down_index).astype(int)
    y_up_test = (prepared.y_test_class == up_index).astype(int)
    y_down_test = (prepared.y_test_class == down_index).astype(int)

    up_model = LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42).fit(prepared.X_train, y_up_train)
    down_model = LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42).fit(prepared.X_train, y_down_train)

    up_prob_test = up_model.predict_proba(prepared.X_test)[:, 1]
    down_prob_test = down_model.predict_proba(prepared.X_test)[:, 1]
    up_pred = (up_prob_test >= 0.5).astype(int)
    down_pred = (down_prob_test >= 0.5).astype(int)

    combined = np.select(
        [(up_prob_test > down_prob_test) & (up_prob_test >= 0.5), (down_prob_test > up_prob_test) & (down_prob_test >= 0.5)],
        ["UP", "DOWN"],
        default="NO_STRONG_SIGNAL",
    )
    actual = _decode(prepared.y_test_class, prepared.labels)
    covered = combined != "NO_STRONG_SIGNAL"
    coverage = float(covered.mean())
    accuracy_when_signal = float((combined[covered] == actual[covered]).mean()) if covered.any() else float("nan")

    return {
        "up_vs_rest": {
            "precision": float(precision_score(y_up_test, up_pred, zero_division=0)),
            "recall": float(recall_score(y_up_test, up_pred, zero_division=0)),
        },
        "down_vs_rest": {
            "precision": float(precision_score(y_down_test, down_pred, zero_division=0)),
            "recall": float(recall_score(y_down_test, down_pred, zero_division=0)),
        },
        "combined_signal_coverage": coverage,
        "combined_signal_accuracy": accuracy_when_signal,
        "multiclass_rf_comparison": {
            "up_precision": multiclass_test_class_metrics.get("UP", {}).get("precision"),
            "up_recall": multiclass_test_class_metrics.get("UP", {}).get("recall"),
            "down_precision": multiclass_test_class_metrics.get("DOWN", {}).get("precision"),
            "down_recall": multiclass_test_class_metrics.get("DOWN", {}).get("recall"),
        },
    }


# ---------------------------------------------------------------------------
# Sections 8-11, 22, 23: regression, transforms, outliers, target price
# ---------------------------------------------------------------------------

def regression_experiment(prepared: PreparedSplit, horizon: str) -> dict:
    y_train = prepared.y_train_return
    clean_train = y_train[~np.isnan(y_train)]
    distribution = {
        "median": float(np.median(clean_train)),
        "std": float(np.std(clean_train)),
        "p1": float(np.percentile(clean_train, 1)),
        "p5": float(np.percentile(clean_train, 5)),
        "p95": float(np.percentile(clean_train, 95)),
        "p99": float(np.percentile(clean_train, 99)),
    } if len(clean_train) else {}

    clip_low, clip_high = (np.percentile(clean_train, 1), np.percentile(clean_train, 99)) if len(clean_train) else (-np.inf, np.inf)
    y_train_winsorized = np.clip(y_train, clip_low, clip_high)

    def to_signed_log(values: np.ndarray) -> np.ndarray:
        return np.sign(values) * np.log1p(np.abs(values))

    def from_signed_log(values: np.ndarray) -> np.ndarray:
        return np.sign(values) * np.expm1(np.abs(values))

    model_specs: list[tuple[str, Any]] = [
        ("ridge", Ridge(alpha=1.0, random_state=42)),
        ("random_forest", RandomForestRegressor(n_estimators=150, max_depth=8, min_samples_leaf=5, max_features="sqrt", random_state=42, n_jobs=-1)),
        ("hist_gb", HistGradientBoostingRegressor(random_state=42, max_depth=4, learning_rate=0.05)),
    ]
    if XGBRegressor is not None:
        model_specs.append(
            (
                "xgboost",
                XGBRegressor(objective="reg:squarederror", n_estimators=200, max_depth=3, learning_rate=0.05, subsample=0.85, colsample_bytree=0.85, tree_method="hist", random_state=42, n_jobs=2),
            )
        )

    results: dict[str, dict] = {}
    for name, base_model in model_specs:
        results[f"{name}_raw"] = _fit_and_evaluate_regressor(clone(base_model), prepared, horizon, y_train, transform=None, inverse=None)
        results[f"{name}_winsorized_1_99"] = _fit_and_evaluate_regressor(clone(base_model), prepared, horizon, y_train_winsorized, transform=None, inverse=None)
        results[f"{name}_signed_log"] = _fit_and_evaluate_regressor(clone(base_model), prepared, horizon, y_train, transform=to_signed_log, inverse=from_signed_log)

    best_name = min(results.items(), key=lambda item: item[1]["validation"]["mae"])[0]

    direction_consistency = regression_direction_consistency(
        prepared.y_test_return, results[best_name]["_raw_test_pred"]
    )
    for entry in results.values():
        entry.pop("_raw_test_pred", None)
        entry.pop("_raw_validation_pred", None)

    return {
        "train_target_distribution": distribution,
        "winsorize_bounds": {"low": float(clip_low), "high": float(clip_high)},
        "models": results,
        "best_by_validation_mae": best_name,
        "regression_direction_consistency_at_thresholds": direction_consistency,
    }


def _fit_and_evaluate_regressor(model: Any, prepared: PreparedSplit, horizon: str, y_train: np.ndarray, transform, inverse) -> dict:
    y_fit = transform(y_train) if transform else y_train
    valid = ~np.isnan(y_fit)
    model.fit(prepared.X_train[valid], y_fit[valid])

    val_pred = np.asarray(model.predict(prepared.X_validation), dtype=float)
    test_pred = np.asarray(model.predict(prepared.X_test), dtype=float)
    if inverse:
        val_pred = inverse(val_pred)
        test_pred = inverse(test_pred)

    return {
        "validation": {**regression_metrics(prepared.y_validation_return, val_pred), **target_price_accuracy(prepared.validation, horizon, val_pred)},
        "test": {**regression_metrics(prepared.y_test_return, test_pred), **target_price_accuracy(prepared.test, horizon, test_pred)},
        "uncertainty": residual_uncertainty(prepared.y_validation_return, val_pred),
        "_raw_test_pred": test_pred,
        "_raw_validation_pred": val_pred,
    }


def target_price_accuracy(frame: pd.DataFrame, horizon: str, predicted_return: np.ndarray) -> dict:
    current_price = pd.to_numeric(frame["close"], errors="coerce").to_numpy(dtype=float)
    actual_price = pd.to_numeric(frame[f"target_close_{horizon}"], errors="coerce").to_numpy(dtype=float)
    predicted_price = current_price * (1 + predicted_return)

    abs_error = np.abs(predicted_price - actual_price)
    with np.errstate(invalid="ignore", divide="ignore"):
        pct_error = np.abs(predicted_price / actual_price - 1)
    mask = np.isfinite(abs_error) & np.isfinite(pct_error)
    abs_error = abs_error[mask]
    pct_error = pct_error[mask]

    if len(abs_error) == 0:
        return {"target_price_mae": float("nan"), "target_price_mape": float("nan"), "within_3pct": float("nan"), "within_5pct": float("nan"), "within_10pct": float("nan"), "target_price_sample_count": 0}

    return {
        "target_price_mae": float(np.mean(abs_error)),
        "target_price_mape": float(np.mean(pct_error)),
        "within_3pct": float(np.mean(pct_error <= 0.03)),
        "within_5pct": float(np.mean(pct_error <= 0.05)),
        "within_10pct": float(np.mean(pct_error <= 0.10)),
        "target_price_sample_count": int(len(abs_error)),
    }


def regression_direction_consistency(actual_return: np.ndarray, predicted_return: np.ndarray) -> list[dict]:
    rows = []
    for threshold in (0.0, 0.01, 0.02, 0.03, 0.05):
        mask = np.abs(predicted_return) >= threshold
        mask &= np.isfinite(actual_return) & np.isfinite(predicted_return)
        if mask.sum() == 0:
            rows.append({"min_abs_predicted_return": threshold, "count": 0, "direction_accuracy": float("nan")})
            continue
        accuracy = float((np.sign(actual_return[mask]) == np.sign(predicted_return[mask])).mean())
        rows.append({"min_abs_predicted_return": threshold, "count": int(mask.sum()), "direction_accuracy": accuracy})
    return rows


# ---------------------------------------------------------------------------
# Section 15: calibration audit
# ---------------------------------------------------------------------------

def calibration_experiment(model: Any, prepared: PreparedSplit) -> dict:
    val_proba = _predict_proba(model, prepared.X_validation, len(prepared.labels))
    test_proba = _predict_proba(model, prepared.X_test, len(prepared.labels))

    uncalibrated_validation = _reliability_table(val_proba, prepared.y_validation_class)
    uncalibrated_test = _reliability_table(test_proba, prepared.y_test_class)

    calibrated: dict[str, Any] = {}
    for method in ("sigmoid", "isotonic"):
        try:
            calibrated_model = CalibratedClassifierCV(model, method=method, cv="prefit")
            calibrated_model.fit(prepared.X_validation, prepared.y_validation_class)
            calibrated_test_proba = _predict_proba(calibrated_model, prepared.X_test, len(prepared.labels))
            calibrated[method] = _reliability_table(calibrated_test_proba, prepared.y_test_class)
        except Exception as exc:  # pragma: no cover - depends on sample sizes
            calibrated[method] = {"error": str(exc)}

    return {
        "uncalibrated_validation": uncalibrated_validation,
        "uncalibrated_test": uncalibrated_test,
        "calibrated_test": calibrated,
    }


def _reliability_table(probabilities: np.ndarray, y_true_encoded: np.ndarray) -> list[dict]:
    max_probability = probabilities.max(axis=1)
    predicted = probabilities.argmax(axis=1)
    correct = predicted == y_true_encoded
    rows = []
    for low, high in CALIBRATION_BUCKETS:
        mask = (max_probability >= low) & (max_probability < high)
        rows.append(
            {
                "bucket": f"{low:.2f}-{min(high, 1.0):.2f}",
                "count": int(mask.sum()),
                "average_predicted_probability": float(max_probability[mask].mean()) if mask.any() else float("nan"),
                "actual_success_rate": float(correct[mask].mean()) if mask.any() else float("nan"),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Section 14/16: setup-quality score + confidence/setup threshold grid
# ---------------------------------------------------------------------------

def _derived_setup_frame(frame: pd.DataFrame) -> pd.DataFrame:
    derived = pd.DataFrame(index=frame.index)
    derived["adx_14"] = pd.to_numeric(frame.get("adx_14"), errors="coerce")
    derived["trend_clarity"] = pd.to_numeric(frame.get("trend_structure_score"), errors="coerce").abs()
    buyer = pd.to_numeric(frame.get("buyer_pressure_score"), errors="coerce")
    seller = pd.to_numeric(frame.get("seller_pressure_score"), errors="coerce")
    derived["pressure_imbalance"] = (buyer - seller).abs()
    derived["relative_volume"] = pd.to_numeric(frame.get("relative_volume"), errors="coerce")
    return derived


def _setup_quality_stats(train_frame: pd.DataFrame) -> dict[str, tuple[float, float]]:
    derived = _derived_setup_frame(train_frame)
    stats = {}
    for column in SETUP_QUALITY_COLUMNS:
        values = derived[column].dropna()
        mean = float(values.mean()) if len(values) else 0.0
        std = float(values.std()) if len(values) > 1 else 0.0
        stats[column] = (mean, std if std and not np.isnan(std) else 1.0)
    return stats


def _compute_setup_quality(frame: pd.DataFrame, stats: dict[str, tuple[float, float]]) -> np.ndarray:
    derived = _derived_setup_frame(frame)
    n = len(frame)
    z_sum = np.zeros(n)
    z_count = np.zeros(n)
    for column in SETUP_QUALITY_COLUMNS:
        mean, std = stats[column]
        z = (derived[column].to_numpy(dtype=float) - mean) / std
        mask = np.isfinite(z)
        z_sum[mask] += z[mask]
        z_count[mask] += 1
    with np.errstate(invalid="ignore"):
        return np.divide(z_sum, z_count, out=np.full(n, np.nan), where=z_count > 0)


def _setup_quality_cutoffs(train_scores: np.ndarray) -> tuple[float, float]:
    valid = train_scores[np.isfinite(train_scores)]
    if len(valid) < 10:
        return float("-inf"), float("inf")
    return tuple(np.quantile(valid, [1 / 3, 2 / 3]))


def _setup_quality_labels(scores: np.ndarray, low_cut: float, high_cut: float) -> np.ndarray:
    labels = np.full(scores.shape, "WEAK", dtype=object)
    labels[~np.isfinite(scores)] = "UNKNOWN"
    labels[scores >= high_cut] = "STRONG"
    labels[(scores >= low_cut) & (scores < high_cut)] = "MODERATE"
    return labels


def setup_quality_experiment(prepared: PreparedSplit, bundle: dict, horizon: str) -> dict:
    stats = _setup_quality_stats(prepared.train)
    train_scores = _compute_setup_quality(prepared.train, stats)
    low_cut, high_cut = _setup_quality_cutoffs(train_scores)

    test_scores = _compute_setup_quality(prepared.test, stats)
    test_bucket = _setup_quality_labels(test_scores, low_cut, high_cut)

    backtest = bundle["test_backtest"].copy()
    backtest["setup_quality"] = test_bucket
    backtest["max_probability"] = bundle["test_proba"].max(axis=1)
    total = len(backtest)

    rows = []
    for probability_threshold in (0.55, 0.60, 0.65, 0.70, 0.75):
        for setup_filter, allowed in (("ANY", None), ("MODERATE_PLUS", {"MODERATE", "STRONG"}), ("STRONG_ONLY", {"STRONG"})):
            subset = backtest[backtest["max_probability"] >= probability_threshold]
            if allowed is not None:
                subset = subset[subset["setup_quality"].isin(allowed)]
            row = {
                "probability_threshold": probability_threshold,
                "setup_filter": setup_filter,
                "sample_count": int(len(subset)),
                "coverage": float(len(subset) / total) if total else 0.0,
            }
            if len(subset) == 0:
                row.update({"accuracy": float("nan"), "up_precision": float("nan"), "down_precision": float("nan"), "avg_future_return_bullish": float("nan"), "avg_future_return_bearish": float("nan")})
            else:
                up_rows = subset[subset["predicted_class"] == "UP"]
                down_rows = subset[subset["predicted_class"] == "DOWN"]
                row.update(
                    {
                        "accuracy": float((subset["predicted_class"] == subset["actual_class"]).mean()),
                        "up_precision": float((up_rows["actual_class"] == "UP").mean()) if len(up_rows) else float("nan"),
                        "down_precision": float((down_rows["actual_class"] == "DOWN").mean()) if len(down_rows) else float("nan"),
                        "avg_future_return_bullish": float(up_rows["actual_return"].mean()) if len(up_rows) else float("nan"),
                        "avg_future_return_bearish": float(down_rows["actual_return"].mean()) if len(down_rows) else float("nan"),
                    }
                )
            rows.append(row)

    return {"low_cut": float(low_cut), "high_cut": float(high_cut), "grid": rows}


# ---------------------------------------------------------------------------
# Sections 12/13: regime slicing (inputs only -- target stays absolute)
# ---------------------------------------------------------------------------

def regime_experiment(prepared: PreparedSplit, backtest: pd.DataFrame) -> dict:
    test_frame = prepared.test
    train_vol = pd.to_numeric(prepared.train.get("volatility_20d"), errors="coerce")
    vol_cut = float(train_vol.quantile(0.5)) if train_vol.notna().any() else float("nan")
    vol = pd.to_numeric(test_frame.get("volatility_20d"), errors="coerce")
    trend_flag = pd.to_numeric(test_frame.get("sma50_above_sma200"), errors="coerce")

    trend_regime = np.full(len(test_frame), "UNKNOWN", dtype=object)
    trend_regime[trend_flag.to_numpy() == 1] = "UPTREND"
    trend_regime[trend_flag.to_numpy() == 0] = "DOWNTREND_OR_SIDEWAYS"

    vol_regime = np.full(len(test_frame), "UNKNOWN", dtype=object)
    if not np.isnan(vol_cut):
        vol_np = vol.to_numpy()
        vol_regime[vol_np <= vol_cut] = "LOW_VOL"
        vol_regime[vol_np > vol_cut] = "HIGH_VOL"

    frame = backtest.copy()
    frame["trend_regime"] = trend_regime
    frame["vol_regime"] = vol_regime

    def summarize(column: str) -> list[dict]:
        rows = []
        for value, group in frame.groupby(column):
            if len(group) < 20 or group["actual_class"].nunique() < 2:
                rows.append({column: value, "status": "INSUFFICIENT_SAMPLE", "count": int(len(group))})
                continue
            rows.append(
                {
                    column: value,
                    "count": int(len(group)),
                    "accuracy": float((group["predicted_class"] == group["actual_class"]).mean()),
                    "balanced_accuracy": float(balanced_accuracy_score(group["actual_class"], group["predicted_class"])),
                    "macro_f1": float(f1_score(group["actual_class"], group["predicted_class"], labels=CLASS_LABELS, average="macro", zero_division=0)),
                }
            )
        return rows

    return {"by_trend_regime": summarize("trend_regime"), "by_volatility_regime": summarize("vol_regime")}


# ---------------------------------------------------------------------------
# Section 21: walk-forward stability
# ---------------------------------------------------------------------------

def temporal_stability(backtest: pd.DataFrame, threshold: float, segments: int = 3) -> list[dict]:
    data = backtest.sort_values("prediction_date").copy()
    if data.empty:
        return []
    data["segment"] = pd.qcut(pd.to_datetime(data["prediction_date"]).rank(method="first"), q=segments, labels=False, duplicates="drop")
    rows = []
    for segment, frame in data.groupby("segment", sort=True):
        signals = frame[frame["predicted_probability"] >= threshold]
        rows.append(
            {
                "segment": int(segment),
                "start": pd.to_datetime(frame["prediction_date"]).min().date().isoformat(),
                "end": pd.to_datetime(frame["prediction_date"]).max().date().isoformat(),
                "balanced_accuracy": float(balanced_accuracy_score(frame["actual_class"], frame["predicted_class"])) if frame["actual_class"].nunique() > 1 else float("nan"),
                "macro_f1": float(f1_score(frame["actual_class"], frame["predicted_class"], labels=CLASS_LABELS, average="macro", zero_division=0)),
                "signal_coverage": float(len(signals) / len(frame)) if len(frame) else 0.0,
                "signal_accuracy": float((signals["predicted_class"] == signals["actual_class"]).mean()) if len(signals) else float("nan"),
                "signal_count": int(len(signals)),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Section 20: recency sample weighting
# ---------------------------------------------------------------------------

def recency_weighting_experiment(prepared: PreparedSplit, half_life_days: int = RECENCY_HALF_LIFE_DAYS) -> dict:
    train_dates = pd.to_datetime(prepared.train["date"])
    age_days = (train_dates.max() - train_dates).dt.days.to_numpy(dtype=float)
    weights = np.exp(-np.log(2) * age_days / half_life_days)

    def fit_and_score(sample_weight: np.ndarray | None) -> dict:
        model = RandomForestClassifier(n_estimators=200, max_depth=8, min_samples_leaf=5, max_features="sqrt", class_weight="balanced", random_state=42, n_jobs=-1)
        if sample_weight is not None:
            model.fit(prepared.X_train, prepared.y_train_class, sample_weight=sample_weight)
        else:
            model.fit(prepared.X_train, prepared.y_train_class)
        proba = _predict_proba(model, prepared.X_test, len(prepared.labels))
        pred = proba.argmax(axis=1)
        metrics = classification_metrics(_decode(prepared.y_test_class, prepared.labels), _decode(pred, prepared.labels), proba, labels=prepared.labels)
        return {"accuracy": metrics["accuracy"], "balanced_accuracy": metrics["balanced_accuracy"], "macro_f1": metrics["macro_f1"]}

    return {
        "half_life_days": half_life_days,
        "equal_weight_test": fit_and_score(None),
        "recency_weighted_test": fit_and_score(weights),
    }


# ---------------------------------------------------------------------------
# Section 19: ticker identity feature
# ---------------------------------------------------------------------------

def stock_identity_experiment(prepared: PreparedSplit) -> dict:
    train_dummies = pd.get_dummies(prepared.train["ticker"].astype(str), prefix="ticker")
    train_dummies.index = prepared.X_train.index
    X_train_augmented = pd.concat([prepared.X_train, train_dummies], axis=1)

    test_dummies = pd.get_dummies(prepared.test["ticker"].astype(str), prefix="ticker").reindex(columns=train_dummies.columns, fill_value=0)
    test_dummies.index = prepared.X_test.index
    X_test_augmented = pd.concat([prepared.X_test, test_dummies], axis=1)

    def fit_and_score(X_train: pd.DataFrame, X_test: pd.DataFrame) -> dict:
        model = RandomForestClassifier(n_estimators=200, max_depth=8, min_samples_leaf=5, max_features="sqrt", class_weight="balanced", random_state=42, n_jobs=-1)
        model.fit(X_train, prepared.y_train_class)
        proba = _predict_proba(model, X_test, len(prepared.labels))
        pred = proba.argmax(axis=1)
        metrics = classification_metrics(_decode(prepared.y_test_class, prepared.labels), _decode(pred, prepared.labels), proba, labels=prepared.labels)
        return {"accuracy": metrics["accuracy"], "balanced_accuracy": metrics["balanced_accuracy"], "macro_f1": metrics["macro_f1"]}

    return {
        "without_ticker_identity": fit_and_score(prepared.X_train, prepared.X_test),
        "with_ticker_identity_one_hot": fit_and_score(X_train_augmented, X_test_augmented),
    }


# ---------------------------------------------------------------------------
# Section 18: per-stock vs global models
# ---------------------------------------------------------------------------

def per_stock_experiment(prepared: PreparedSplit) -> dict:
    global_model = RandomForestClassifier(n_estimators=200, max_depth=8, min_samples_leaf=5, max_features="sqrt", class_weight="balanced", random_state=42, n_jobs=-1)
    global_model.fit(prepared.X_train, prepared.y_train_class)
    global_test_proba = _predict_proba(global_model, prepared.X_test, len(prepared.labels))
    global_test_pred = _decode(global_test_proba.argmax(axis=1), prepared.labels)
    actual = _decode(prepared.y_test_class, prepared.labels)

    results: dict[str, dict] = {}
    for ticker in FOCUS_STOCKS:
        train_mask = (prepared.train["ticker"] == ticker).to_numpy()
        test_mask = (prepared.test["ticker"] == ticker).to_numpy()
        train_rows = int(train_mask.sum())
        test_rows = int(test_mask.sum())

        if ticker in SKIP_PER_STOCK_UNLESS_SUFFICIENT and train_rows < MIN_PER_STOCK_TRAIN_ROWS:
            results[ticker] = {"status": "SKIPPED_INSUFFICIENT_HISTORY", "train_rows": train_rows, "test_rows": test_rows}
            continue
        if train_rows < MIN_PER_STOCK_TRAIN_ROWS or test_rows < MIN_PER_STOCK_TEST_ROWS:
            results[ticker] = {"status": "INSUFFICIENT_SAMPLE", "train_rows": train_rows, "test_rows": test_rows}
            continue

        y_train_ticker = prepared.y_train_class[train_mask]
        y_test_ticker = prepared.y_test_class[test_mask]
        if len(np.unique(y_train_ticker)) < 2 or len(np.unique(y_test_ticker)) < 2:
            results[ticker] = {"status": "INSUFFICIENT_CLASS_VARIETY", "train_rows": train_rows, "test_rows": test_rows}
            continue

        stock_model = RandomForestClassifier(n_estimators=150, max_depth=5, min_samples_leaf=5, class_weight="balanced", random_state=42, n_jobs=-1)
        stock_model.fit(prepared.X_train.loc[train_mask], y_train_ticker)
        stock_proba = _predict_proba(stock_model, prepared.X_test.loc[test_mask], len(prepared.labels))
        stock_pred = _decode(stock_proba.argmax(axis=1), prepared.labels)
        actual_ticker = _decode(y_test_ticker, prepared.labels)

        global_pred_ticker = global_test_pred[test_mask]

        results[ticker] = {
            "status": "OK",
            "train_rows": train_rows,
            "test_rows": test_rows,
            "stock_specific_model": {
                "accuracy": float(accuracy_score(actual_ticker, stock_pred)),
                "balanced_accuracy": float(balanced_accuracy_score(actual_ticker, stock_pred)),
            },
            "global_model_on_this_stock": {
                "accuracy": float(accuracy_score(actual_ticker, global_pred_ticker)),
                "balanced_accuracy": float(balanced_accuracy_score(actual_ticker, global_pred_ticker)),
            },
        }
    return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)


def _split_summary(prepared: PreparedSplit) -> dict:
    def one(frame: pd.DataFrame) -> dict:
        dates = pd.to_datetime(frame["date"])
        return {"rows": int(len(frame)), "start": dates.min().date().isoformat(), "end": dates.max().date().isoformat()}

    return {"train": one(prepared.train), "validation": one(prepared.validation), "test": one(prepared.test)}


def assess_report(report: dict) -> dict:
    horizon_scores = []
    for horizon in report["horizons"]:
        rf_test = report["target_modes"]["fixed_3pct"][horizon]["models"]["random_forest"]["test"]
        dominant = report["baselines"][horizon]["dominant_class"]
        gap = rf_test["balanced_accuracy"] - dominant["balanced_accuracy"]
        horizon_scores.append(gap)

    calibration_monotonic = []
    for horizon in report["horizons"]:
        rates = [row["actual_success_rate"] for row in report["calibration"][horizon]["uncalibrated_test"] if row["count"] > 0]
        calibration_monotonic.append(all(b >= a - 0.05 for a, b in zip(rates, rates[1:])))

    stable_walk_forward = []
    for horizon in report["horizons"]:
        segments = report["walk_forward"][horizon]
        values = [segment["balanced_accuracy"] for segment in segments if segment["balanced_accuracy"] == segment["balanced_accuracy"]]
        stable_walk_forward.append((max(values) - min(values)) < 0.15 if len(values) >= 2 else False)

    average_gap = float(np.mean(horizon_scores)) if horizon_scores else float("nan")
    beats_baseline = average_gap is not float("nan") and average_gap > 0.03
    calibration_ok = sum(calibration_monotonic) >= len(calibration_monotonic) / 2 if calibration_monotonic else False
    stability_ok = sum(stable_walk_forward) >= len(stable_walk_forward) / 2 if stable_walk_forward else False

    if beats_baseline and calibration_ok and stability_ok:
        verdict = "PROMISING"
    elif beats_baseline or calibration_ok:
        verdict = "MIXED"
    else:
        verdict = "WEAK"

    return {
        "verdict": verdict,
        "average_balanced_accuracy_gap_vs_dominant_baseline": average_gap,
        "calibration_roughly_monotonic_by_horizon": dict(zip(report["horizons"], calibration_monotonic)),
        "walk_forward_stable_by_horizon": dict(zip(report["horizons"], stable_walk_forward)),
    }
