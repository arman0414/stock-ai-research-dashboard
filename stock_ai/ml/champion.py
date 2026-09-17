"""Phase 7: champion model training with calibration and validated signal gating.

Builds production-ready per-horizon artifacts (classifier + regressor +
calibration + validated bullish/bearish thresholds + reliability tables +
setup-quality cutoffs + regression uncertainty) that stock_ai/services/prediction.py
loads at prediction time. Absolute prediction only -- no relative/ranking targets.

Selection discipline enforced throughout:
  * calibration mapping is fit on one half of validation ("calib_fit")
  * calibration method choice, threshold search, and reliability tables used
    for SELECTION are computed on the other half ("calib_eval")
  * the test set is only ever used for final, non-selective reporting
    (honest reliability numbers + walk-forward stability of the already-chosen
    thresholds), never to pick a method, threshold, or hyperparameter.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import balanced_accuracy_score, brier_score_loss, f1_score, log_loss
from sqlalchemy.orm import Session

from stock_ai.config import PROJECT_ROOT
from stock_ai.features.targets import DEFAULT_HORIZONS
from stock_ai.ml.config import CLASS_LABELS
from stock_ai.ml.evaluation import class_distribution, classification_metrics, regression_metrics
from stock_ai.ml.phase5 import add_phase5_targets, load_prices_for_tickers
from stock_ai.ml.phase6 import _build_base_features, _compute_setup_quality, _setup_quality_cutoffs, _setup_quality_stats, target_price_accuracy
from stock_ai.ml.signal_research import PreparedSplit, _backtest_frame, _decode, _predict_proba, prepare_split
from stock_ai.universe import REFERENCE_UNIVERSE
from stock_ai.utils.json_safe import sanitize_json, write_json_file


CHAMPION_HORIZONS = ("5d", "10d", "15d")
PRIMARY_RESEARCH_HORIZON = "5d"
DEFAULT_SEEDS = (42, 43, 44, 45, 46)
DEFAULT_MIN_EVIDENCE = 50
RELIABILITY_BUCKETS = ((0.40, 0.50), (0.50, 0.60), (0.60, 0.70), (0.70, 0.80), (0.80, 0.90), (0.90, 1.0001))
CANDIDATE_THRESHOLDS = (0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80)
DEFAULT_ARTIFACTS_ROOT = PROJECT_ROOT / "artifacts" / "models" / "champions"


def _rf_classifier(random_state: int) -> RandomForestClassifier:
    return RandomForestClassifier(
        n_estimators=200,
        max_depth=8,
        min_samples_leaf=5,
        max_features="sqrt",
        class_weight="balanced",
        random_state=random_state,
        n_jobs=-1,
    )


def _rf_regressor(random_state: int = 42) -> RandomForestRegressor:
    return RandomForestRegressor(
        n_estimators=150,
        max_depth=8,
        min_samples_leaf=5,
        max_features="sqrt",
        random_state=random_state,
        n_jobs=-1,
    )


def train_champion_models(
    db: Session,
    horizons: tuple[str, ...] = CHAMPION_HORIZONS,
    seeds: tuple[int, ...] = DEFAULT_SEEDS,
    min_evidence: int = DEFAULT_MIN_EVIDENCE,
    artifacts_root: Path | None = None,
) -> dict:
    artifacts_root = artifacts_root or DEFAULT_ARTIFACTS_ROOT
    prices, price_summary = load_prices_for_tickers(db, REFERENCE_UNIVERSE)
    base = _build_base_features(prices)
    dataset = add_phase5_targets(base, target_mode="fixed_3pct")

    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "product_scope": "absolute_stock_prediction_only",
        "baseline_used": "phase6_fixed_3pct_target_random_forest",
        "primary_research_horizon": PRIMARY_RESEARCH_HORIZON,
        "price_summary": price_summary,
        "min_evidence": min_evidence,
        "seeds": list(seeds),
        "horizons": {},
    }

    for horizon in horizons:
        prepared = prepare_split(dataset, horizon)
        horizon_report, artifact_bundle = train_one_horizon(prepared, horizon, seeds=seeds, min_evidence=min_evidence)
        report["horizons"][horizon] = horizon_report
        _save_champion_artifact(artifact_bundle, artifacts_root / horizon)

    return report


@dataclass
class ChampionArtifactBundle:
    classifier: Any
    calibrated_model: Any
    regressor: Any
    feature_columns: list[str]
    labels: list[str]
    metadata: dict


def train_one_horizon(prepared: PreparedSplit, horizon: str, seeds: tuple[int, ...], min_evidence: int) -> tuple[dict, ChampionArtifactBundle]:
    primary_seed = seeds[0]
    classifier = _rf_classifier(primary_seed)
    classifier.fit(prepared.X_train, prepared.y_train_class)

    calib_fit_mask, calib_eval_mask = _split_validation_for_calibration(prepared, horizon)
    X_calib_fit = prepared.X_validation.loc[calib_fit_mask]
    y_calib_fit = prepared.y_validation_class[calib_fit_mask]
    X_calib_eval = prepared.X_validation.loc[calib_eval_mask]
    y_calib_eval = prepared.y_validation_class[calib_eval_mask]
    calib_eval_frame = prepared.validation.loc[calib_eval_mask]

    calibration_choice = _select_calibration_method(classifier, X_calib_fit, y_calib_fit, X_calib_eval, y_calib_eval, prepared.labels)
    calibrated_model = calibration_choice["model"]
    method = calibration_choice["method"]

    calib_eval_proba_raw = _predict_proba(classifier, X_calib_eval, len(prepared.labels))
    calib_eval_proba_cal = _predict_proba(calibrated_model, X_calib_eval, len(prepared.labels))
    calib_eval_backtest = _backtest_frame(
        calib_eval_frame, horizon, calib_eval_proba_cal.argmax(axis=1), calib_eval_proba_cal, np.zeros(len(calib_eval_frame)), prepared.labels
    )
    calib_eval_backtest["max_calibrated_probability"] = calib_eval_proba_cal.max(axis=1)

    bullish_selection = select_class_threshold(calib_eval_backtest, "UP", min_evidence=min_evidence)
    bearish_selection = select_class_threshold(calib_eval_backtest, "DOWN", min_evidence=min_evidence)

    test_proba_raw = _predict_proba(classifier, prepared.X_test, len(prepared.labels))
    test_proba_cal = _predict_proba(calibrated_model, prepared.X_test, len(prepared.labels))
    test_backtest = _backtest_frame(prepared.test, horizon, test_proba_cal.argmax(axis=1), test_proba_cal, np.zeros(len(prepared.test)), prepared.labels)
    test_backtest["max_calibrated_probability"] = test_proba_cal.max(axis=1)

    walk_forward_bullish = walk_forward_threshold_stability(test_backtest, "UP", bullish_selection["threshold"], min_evidence=min_evidence)
    walk_forward_bearish = walk_forward_threshold_stability(test_backtest, "DOWN", bearish_selection["threshold"], min_evidence=min_evidence)

    test_evaluation_bullish = _evaluate_single_threshold(test_backtest, "UP", bullish_selection["threshold"], min_evidence=min_evidence)
    test_evaluation_bearish = _evaluate_single_threshold(test_backtest, "DOWN", bearish_selection["threshold"], min_evidence=min_evidence)

    multi_seed = multi_seed_robustness(prepared, seeds=seeds, horizon=horizon)

    regressor = _rf_regressor()
    regressor.fit(prepared.X_train, prepared.y_train_return)
    validation_pred_return = np.asarray(regressor.predict(prepared.X_validation), dtype=float)
    test_pred_return = np.asarray(regressor.predict(prepared.X_test), dtype=float)
    regression_report = {
        "validation": {**regression_metrics(prepared.y_validation_return, validation_pred_return), **target_price_accuracy(prepared.validation, horizon, validation_pred_return)},
        "test": {**regression_metrics(prepared.y_test_return, test_pred_return), **target_price_accuracy(prepared.test, horizon, test_pred_return)},
        "uncertainty": _regression_uncertainty(prepared.y_validation_return, validation_pred_return),
    }

    setup_stats = _setup_quality_stats(prepared.train)
    setup_train_scores = _compute_setup_quality(prepared.train, setup_stats)
    setup_low_cut, setup_high_cut = _setup_quality_cutoffs(setup_train_scores)
    pressure_stats = _raw_column_stats(prepared.train, ("buyer_pressure_score", "seller_pressure_score"))

    metadata = {
        "horizon": horizon,
        "purge_gap": DEFAULT_HORIZONS[horizon],
        "is_primary_research_horizon": horizon == PRIMARY_RESEARCH_HORIZON,
        "feature_columns": prepared.feature_columns,
        "labels": prepared.labels,
        "classifier_random_state": primary_seed,
        "calibration_method": method,
        "calibration_selection_metrics": calibration_choice["selection_metrics"],
        "reliability_tables": {
            "calibration_eval_raw": reliability_table(calib_eval_proba_raw, y_calib_eval),
            "calibration_eval_calibrated": reliability_table(calib_eval_proba_cal, y_calib_eval),
            "test_raw": reliability_table(test_proba_raw, prepared.y_test_class),
            "test_calibrated": reliability_table(test_proba_cal, prepared.y_test_class),
        },
        "thresholds": {
            "bullish": bullish_selection,
            "bearish": bearish_selection,
        },
        "walk_forward": {
            "bullish": walk_forward_bullish,
            "bearish": walk_forward_bearish,
        },
        "test_evaluation": {
            "bullish": test_evaluation_bullish,
            "bearish": test_evaluation_bearish,
            "note": "Held-out test performance of the already-selected threshold. This -- not the validation selection numbers above -- is what production should surface as historical_signal_accuracy, since it was never used to choose anything.",
        },
        "multi_seed_robustness": multi_seed,
        "regression": regression_report,
        "setup_quality": {
            "columns": list(setup_stats.keys()),
            "stats": {k: list(v) for k, v in setup_stats.items()},
            "low_cut": float(setup_low_cut),
            "high_cut": float(setup_high_cut),
            "pressure_stats": {k: list(v) for k, v in pressure_stats.items()},
        },
        "split_summary": _split_summary(prepared),
        "min_evidence": min_evidence,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    horizon_report = {
        "class_distribution": class_distribution(_decode(prepared.y_test_class, prepared.labels)),
        "classifier_test_metrics": classification_metrics(
            _decode(prepared.y_test_class, prepared.labels), _decode(test_proba_cal.argmax(axis=1), prepared.labels), test_proba_cal, labels=prepared.labels
        ),
        "calibration_method": method,
        "calibration_selection_metrics": calibration_choice["selection_metrics"],
        "thresholds": {"bullish": bullish_selection, "bearish": bearish_selection},
        "walk_forward": {"bullish": walk_forward_bullish, "bearish": walk_forward_bearish},
        "test_evaluation": {"bullish": test_evaluation_bullish, "bearish": test_evaluation_bearish},
        "multi_seed_robustness": multi_seed,
        "regression": regression_report,
        "reliability_test_calibrated": reliability_table(test_proba_cal, prepared.y_test_class),
    }

    bundle = ChampionArtifactBundle(
        classifier=classifier,
        calibrated_model=calibrated_model,
        regressor=regressor,
        feature_columns=prepared.feature_columns,
        labels=prepared.labels,
        metadata=metadata,
    )
    return horizon_report, bundle


# ---------------------------------------------------------------------------
# Calibration selection (validation-only)
# ---------------------------------------------------------------------------

def _select_calibration_method(classifier: Any, X_calib_fit, y_calib_fit, X_calib_eval, y_calib_eval, labels: list[str]) -> dict:
    candidates: dict[str, Any] = {"uncalibrated": classifier}
    for method in ("sigmoid", "isotonic"):
        try:
            calibrated = CalibratedClassifierCV(classifier, method=method, cv="prefit")
            calibrated.fit(X_calib_fit, y_calib_fit)
            candidates[method] = calibrated
        except Exception:
            continue

    selection_metrics: dict[str, dict] = {}
    for name, model in candidates.items():
        proba = _predict_proba(model, X_calib_eval, len(labels))
        pred = proba.argmax(axis=1)
        selection_metrics[name] = {
            "log_loss": float(log_loss(y_calib_eval, proba, labels=list(range(len(labels))))),
            "multiclass_brier": float(_multiclass_brier(y_calib_eval, proba, len(labels))),
            "balanced_accuracy": float(balanced_accuracy_score(y_calib_eval, pred)),
            "macro_f1": float(f1_score(_decode(y_calib_eval, labels), _decode(pred, labels), labels=labels, average="macro", zero_division=0)),
        }

    calibrated_names = [name for name in selection_metrics if name != "uncalibrated"]
    if not calibrated_names:
        best_name = "uncalibrated"
    else:
        best_name = min(calibrated_names, key=lambda name: selection_metrics[name]["multiclass_brier"])
        if selection_metrics[best_name]["multiclass_brier"] >= selection_metrics["uncalibrated"]["multiclass_brier"]:
            best_name = "uncalibrated"

    return {"method": best_name, "model": candidates[best_name], "selection_metrics": selection_metrics}


def _multiclass_brier(y_true_encoded: np.ndarray, probabilities: np.ndarray, n_classes: int) -> float:
    encoded = np.zeros_like(probabilities, dtype=float)
    encoded[np.arange(len(y_true_encoded)), np.asarray(y_true_encoded, dtype=int)] = 1.0
    return float(np.mean(np.sum((probabilities - encoded) ** 2, axis=1)))


def _split_validation_for_calibration(prepared: PreparedSplit, horizon: str) -> tuple[np.ndarray, np.ndarray]:
    dates = pd.to_datetime(prepared.validation["date"])
    unique_dates = pd.Index(sorted(dates.unique()))
    purge = DEFAULT_HORIZONS[horizon]
    mid = len(unique_dates) // 2

    if len(unique_dates) > 2 * purge + 4:
        fit_dates = unique_dates[: max(mid - purge, 1)]
        eval_dates = unique_dates[mid:]
    else:
        fit_dates = unique_dates[:mid]
        eval_dates = unique_dates[mid:]

    fit_mask = dates.isin(fit_dates).to_numpy()
    eval_mask = dates.isin(eval_dates).to_numpy()
    return fit_mask, eval_mask


# ---------------------------------------------------------------------------
# Reliability tables (section 4)
# ---------------------------------------------------------------------------

def reliability_table(probabilities: np.ndarray, y_true_encoded: np.ndarray, buckets: tuple = RELIABILITY_BUCKETS) -> list[dict]:
    max_probability = probabilities.max(axis=1)
    predicted = probabilities.argmax(axis=1)
    correct = predicted == np.asarray(y_true_encoded)
    rows = []
    for low, high in buckets:
        mask = (max_probability >= low) & (max_probability < high)
        count = int(mask.sum())
        avg_predicted = float(max_probability[mask].mean()) if count else float("nan")
        actual_rate = float(correct[mask].mean()) if count else float("nan")
        rows.append(
            {
                "bucket": f"{low:.2f}-{min(high, 1.0):.2f}",
                "count": count,
                "average_predicted_probability": avg_predicted,
                "actual_success_rate": actual_rate,
                "difference": float(avg_predicted - actual_rate) if count else float("nan"),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Threshold selection with minimum-evidence gating (sections 6/7/10/11/12)
# ---------------------------------------------------------------------------

def evaluate_class_thresholds(backtest: pd.DataFrame, class_label: str, thresholds: tuple[float, ...] = CANDIDATE_THRESHOLDS, min_evidence: int = DEFAULT_MIN_EVIDENCE) -> list[dict]:
    total = len(backtest)
    actual_positive_total = int((backtest["actual_class"] == class_label).sum())
    rows = []
    for threshold in thresholds:
        fired = backtest[(backtest["predicted_class"] == class_label) & (backtest["max_calibrated_probability"] >= threshold)]
        sample_count = int(len(fired))
        coverage = float(sample_count / total) if total else 0.0
        precision = float((fired["actual_class"] == class_label).mean()) if sample_count else float("nan")
        true_positive = int((fired["actual_class"] == class_label).sum())
        recall = float(true_positive / actual_positive_total) if actual_positive_total else float("nan")
        avg_future_return = float(fired["actual_return"].mean()) if sample_count else float("nan")
        status = "OK" if sample_count >= min_evidence else "INSUFFICIENT_EVIDENCE"
        rows.append(
            {
                "threshold": threshold,
                "sample_count": sample_count,
                "coverage": coverage,
                "precision": precision,
                "recall": recall,
                "average_future_return": avg_future_return,
                "status": status,
            }
        )
    return rows


def select_class_threshold(backtest: pd.DataFrame, class_label: str, thresholds: tuple[float, ...] = CANDIDATE_THRESHOLDS, min_evidence: int = DEFAULT_MIN_EVIDENCE) -> dict:
    table = evaluate_class_thresholds(backtest, class_label, thresholds=thresholds, min_evidence=min_evidence)
    base_rate = float((backtest["actual_class"] == class_label).mean()) if len(backtest) else float("nan")

    eligible = [row for row in table if row["status"] == "OK" and row["precision"] == row["precision"] and row["precision"] > base_rate]
    if eligible:
        best = max(eligible, key=lambda row: (row["precision"], row["sample_count"]))
        return {
            "class_label": class_label,
            "threshold": best["threshold"],
            "status": "VALIDATED",
            "precision": best["precision"],
            "recall": best["recall"],
            "sample_count": best["sample_count"],
            "coverage": best["coverage"],
            "average_future_return": best["average_future_return"],
            "base_rate": base_rate,
            "table": table,
        }

    return {
        "class_label": class_label,
        "threshold": 1.01,
        "status": "INSUFFICIENT_EVIDENCE",
        "precision": float("nan"),
        "recall": float("nan"),
        "sample_count": 0,
        "coverage": 0.0,
        "average_future_return": float("nan"),
        "base_rate": base_rate,
        "table": table,
    }


def _evaluate_single_threshold(backtest: pd.DataFrame, class_label: str, threshold: float, min_evidence: int = DEFAULT_MIN_EVIDENCE) -> dict:
    if threshold > 1.0:
        return {"class_label": class_label, "threshold": threshold, "status": "NOT_APPLICABLE", "sample_count": 0, "precision": float("nan"), "coverage": 0.0}
    row = evaluate_class_thresholds(backtest, class_label, thresholds=(threshold,), min_evidence=min_evidence)[0]
    return row


def walk_forward_threshold_stability(test_backtest: pd.DataFrame, class_label: str, threshold: float, segments: int = 3, min_evidence: int = DEFAULT_MIN_EVIDENCE) -> dict:
    if test_backtest.empty or threshold > 1.0:
        return {"class_label": class_label, "threshold": threshold, "status": "NOT_APPLICABLE", "segments": []}

    data = test_backtest.sort_values("prediction_date").copy()
    data["segment"] = pd.qcut(pd.to_datetime(data["prediction_date"]).rank(method="first"), q=segments, labels=False, duplicates="drop")

    segment_rows = []
    for segment, frame in data.groupby("segment", sort=True):
        fired = frame[(frame["predicted_class"] == class_label) & (frame["max_calibrated_probability"] >= threshold)]
        sample_count = int(len(fired))
        precision = float((fired["actual_class"] == class_label).mean()) if sample_count else float("nan")
        segment_rows.append(
            {
                "segment": int(segment),
                "start": pd.to_datetime(frame["prediction_date"]).min().date().isoformat(),
                "end": pd.to_datetime(frame["prediction_date"]).max().date().isoformat(),
                "sample_count": sample_count,
                "coverage": float(sample_count / len(frame)) if len(frame) else 0.0,
                "precision": precision,
            }
        )

    fired_segments = [row for row in segment_rows if row["sample_count"] > 0]
    overall_precision = float(np.nanmean([row["precision"] for row in fired_segments])) if fired_segments else float("nan")
    consistent = (
        len(fired_segments) >= max(1, segments - 1)
        and all(row["precision"] == row["precision"] and row["precision"] >= overall_precision - 0.15 for row in fired_segments)
    )

    return {
        "class_label": class_label,
        "threshold": threshold,
        "status": "STABLE" if consistent else "UNSTABLE",
        "segments_with_signal": len(fired_segments),
        "total_segments": len(segment_rows),
        "segments": segment_rows,
    }


# ---------------------------------------------------------------------------
# Multi-seed robustness (section 5)
# ---------------------------------------------------------------------------

def multi_seed_robustness(prepared: PreparedSplit, seeds: tuple[int, ...], horizon: str) -> dict:
    balanced_accuracies = []
    macro_f1s = []
    calibrated_errors = []
    up_precisions = []
    down_precisions = []
    coverages = []

    for seed in seeds:
        model = _rf_classifier(seed)
        model.fit(prepared.X_train, prepared.y_train_class)
        test_proba = _predict_proba(model, prepared.X_test, len(prepared.labels))
        test_pred = test_proba.argmax(axis=1)

        balanced_accuracies.append(float(balanced_accuracy_score(prepared.y_test_class, test_pred)))
        macro_f1s.append(float(f1_score(_decode(prepared.y_test_class, prepared.labels), _decode(test_pred, prepared.labels), labels=prepared.labels, average="macro", zero_division=0)))
        calibrated_errors.append(float(_multiclass_brier(prepared.y_test_class, test_proba, len(prepared.labels))))

        backtest = _backtest_frame(prepared.test, horizon, test_pred, test_proba, np.zeros(len(test_pred)), prepared.labels)
        backtest["max_calibrated_probability"] = test_proba.max(axis=1)
        signal_threshold = 0.60
        up_fired = backtest[(backtest["predicted_class"] == "UP") & (backtest["max_calibrated_probability"] >= signal_threshold)]
        down_fired = backtest[(backtest["predicted_class"] == "DOWN") & (backtest["max_calibrated_probability"] >= signal_threshold)]
        up_precisions.append(float((up_fired["actual_class"] == "UP").mean()) if len(up_fired) else float("nan"))
        down_precisions.append(float((down_fired["actual_class"] == "DOWN").mean()) if len(down_fired) else float("nan"))
        coverages.append(float((len(up_fired) + len(down_fired)) / len(backtest)) if len(backtest) else float("nan"))

    return {
        "seeds": list(seeds),
        "balanced_accuracy": {"mean": float(np.mean(balanced_accuracies)), "std": float(np.std(balanced_accuracies)), "values": balanced_accuracies},
        "macro_f1": {"mean": float(np.mean(macro_f1s)), "std": float(np.std(macro_f1s)), "values": macro_f1s},
        "multiclass_brier": {"mean": float(np.mean(calibrated_errors)), "std": float(np.std(calibrated_errors)), "values": calibrated_errors},
        "signal_precision_at_0.60": {
            "up_precision_mean": float(np.nanmean(up_precisions)),
            "down_precision_mean": float(np.nanmean(down_precisions)),
        },
        "signal_coverage_at_0.60": {"mean": float(np.nanmean(coverages)), "std": float(np.nanstd(coverages))},
    }


# ---------------------------------------------------------------------------
# Regression uncertainty (section 16)
# ---------------------------------------------------------------------------

def _regression_uncertainty(y_validation_actual: np.ndarray, y_validation_predicted: np.ndarray) -> dict:
    residuals = np.asarray(y_validation_actual, dtype=float) - np.asarray(y_validation_predicted, dtype=float)
    residuals = residuals[np.isfinite(residuals)]
    if len(residuals) == 0:
        return {"p50_abs_error": None, "residual_p10": None, "residual_p90": None}
    return {
        "p50_abs_error": float(np.median(np.abs(residuals))),
        "residual_p10": float(np.quantile(residuals, 0.10)),
        "residual_p90": float(np.quantile(residuals, 0.90)),
    }


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _save_champion_artifact(bundle: ChampionArtifactBundle, artifact_dir: Path) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle.classifier, artifact_dir / "classifier.joblib")
    joblib.dump(bundle.calibrated_model, artifact_dir / "calibrated_model.joblib")
    joblib.dump(bundle.regressor, artifact_dir / "regressor.joblib")
    write_json_file(artifact_dir / "metadata.json", bundle.metadata, indent=2, sort_keys=True)


def load_champion_artifact(artifact_dir: Path) -> dict:
    classifier = joblib.load(artifact_dir / "classifier.joblib")
    calibrated_model = joblib.load(artifact_dir / "calibrated_model.joblib")
    regressor = joblib.load(artifact_dir / "regressor.joblib")
    metadata = json.loads((artifact_dir / "metadata.json").read_text())
    return {"classifier": classifier, "calibrated_model": calibrated_model, "regressor": regressor, "metadata": metadata}


def _json_safe(value: Any) -> Any:
    return sanitize_json(value)


def _raw_column_stats(frame: pd.DataFrame, columns: tuple[str, ...]) -> dict[str, tuple[float, float]]:
    stats = {}
    for column in columns:
        values = pd.to_numeric(frame.get(column), errors="coerce").dropna()
        mean = float(values.mean()) if len(values) else 0.0
        std = float(values.std()) if len(values) > 1 else 0.0
        stats[column] = (mean, std if std and not np.isnan(std) else 1.0)
    return stats


def _split_summary(prepared: PreparedSplit) -> dict:
    def one(frame: pd.DataFrame) -> dict:
        dates = pd.to_datetime(frame["date"])
        return {"rows": int(len(frame)), "start": dates.min().date().isoformat(), "end": dates.max().date().isoformat()}

    return {"train": one(prepared.train), "validation": one(prepared.validation), "test": one(prepared.test)}


def save_champion_report(report: dict, root: Path | None = None) -> Path:
    root = root or PROJECT_ROOT / "artifacts" / "benchmarks"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"phase7_champions_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    write_json_file(path, report, indent=2, sort_keys=True)
    return path
