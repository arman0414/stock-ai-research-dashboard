from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.utils.class_weight import compute_sample_weight
from sqlalchemy.orm import Session

from stock_ai.config import PROJECT_ROOT
from stock_ai.features.context import add_context_features
from stock_ai.features.dataset import build_feature_dataset
from stock_ai.features.targets import DEFAULT_HORIZONS, DirectionThresholds, add_future_targets
from stock_ai.ml.evaluation import classification_metrics, regression_metrics
from stock_ai.ml.feature_pruning import diagnose_features, prune_features
from stock_ai.ml.phase5 import load_prices_for_tickers
from stock_ai.ml.preprocessing import select_model_feature_columns
from stock_ai.ml.signals import residual_uncertainty, select_signal_threshold, threshold_table
from stock_ai.ml.split import chronological_split
from stock_ai.universe import FOCUS_STOCKS, REFERENCE_ASSETS, REFERENCE_UNIVERSE
from stock_ai.utils.json_safe import write_json_file


try:
    from xgboost import XGBClassifier, XGBRegressor
except Exception:  # pragma: no cover
    XGBClassifier = None
    XGBRegressor = None


SHORT_HORIZONS = ("5d", "10d", "15d")
CLASS_LABELS = ["DOWN", "NEUTRAL", "UP"]


@dataclass(frozen=True)
class PreparedSplit:
    dataset: pd.DataFrame
    feature_columns: list[str]
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame
    preprocessor: Pipeline
    X_train: pd.DataFrame
    X_validation: pd.DataFrame
    X_test: pd.DataFrame
    y_train_class: np.ndarray
    y_validation_class: np.ndarray
    y_test_class: np.ndarray
    y_train_return: np.ndarray
    y_validation_return: np.ndarray
    y_test_return: np.ndarray
    labels: list[str]
    pruning_report: Any


def run_signal_research(db: Session, horizons: tuple[str, ...] = SHORT_HORIZONS, min_signal_samples: int = 30) -> dict:
    started = time.perf_counter()
    prices, price_summary = load_prices_for_tickers(db, REFERENCE_UNIVERSE)
    build_started = time.perf_counter()
    feature_sets = build_feature_sets(prices)
    feature_build_seconds = time.perf_counter() - build_started

    experiments: dict[str, dict] = {}
    champions: dict[str, dict] = {}
    for horizon in horizons:
        experiments[horizon] = {}
        candidates = []
        for feature_set, dataset in feature_sets.items():
            prepared = prepare_split(dataset, horizon)
            model_results = train_candidate_models(prepared, horizon=horizon, min_signal_samples=min_signal_samples)
            experiments[horizon][feature_set] = {
                "dataset_rows": int(len(dataset)),
                "split": _split_summary(prepared),
                "feature_diagnostics": diagnose_features(prepared.train, select_model_feature_columns(prepared.train)),
                "pruning": _pruning_report_dict(prepared.pruning_report),
                "models": model_results,
            }
            for model_name, result in model_results["classification"].items():
                candidates.append(
                    {
                        "feature_set": feature_set,
                        "model_name": model_name,
                        "validation_macro_f1": result["validation"]["macro_f1"],
                        "validation_balanced_accuracy": result["validation"]["balanced_accuracy"],
                        "threshold": result["selected_threshold"]["threshold"],
                        "threshold_reason": result["selected_threshold"]["reason"],
                    }
                )
        champion = max(candidates, key=lambda item: (item["validation_macro_f1"], item["validation_balanced_accuracy"]))
        champions[horizon] = build_champion_report(
            horizon=horizon,
            feature_set=champion["feature_set"],
            model_name=champion["model_name"],
            experiment=experiments[horizon][champion["feature_set"]],
            min_signal_samples=min_signal_samples,
        )

    elapsed = time.perf_counter() - started
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline_phase5_report": str(PROJECT_ROOT / "artifacts" / "benchmarks" / "phase5_focus_20260915_054136.json"),
        "focus_stocks": list(FOCUS_STOCKS),
        "horizons": list(horizons),
        "price_summary": price_summary,
        "runtime_seconds": elapsed,
        "feature_build_seconds": feature_build_seconds,
        "experiments": experiments,
        "champions": champions,
        "assessment": assess_report(champions),
    }


def build_feature_sets(prices: pd.DataFrame) -> dict[str, pd.DataFrame]:
    technical = add_future_targets(build_feature_dataset(prices, include_targets=False), thresholds=DirectionThresholds())
    price_action = add_future_targets(build_feature_dataset(prices, include_targets=False, include_price_action=True), thresholds=DirectionThresholds())
    context_base = build_feature_dataset(prices, include_targets=False, include_price_action=True)
    context = add_future_targets(add_context_features(context_base, prices), thresholds=DirectionThresholds())
    training_tickers = [ticker for ticker in REFERENCE_UNIVERSE if ticker not in REFERENCE_ASSETS]
    return {
        "technical": _training_rows(technical, training_tickers),
        "technical_price_action": _training_rows(price_action, training_tickers),
        "technical_price_action_context": _training_rows(context, training_tickers),
    }


def prepare_split(dataset: pd.DataFrame, horizon: str) -> PreparedSplit:
    target_class = f"target_class_{horizon}"
    target_return = f"target_return_{horizon}"
    target_close = f"target_close_{horizon}"
    prepared = dataset.dropna(subset=[target_class, target_return, target_close]).copy()
    split = chronological_split(prepared, purge_gap=DEFAULT_HORIZONS[horizon])
    all_features = select_model_feature_columns(split.train)
    kept_features, pruning_report = prune_features(split.train, all_features)
    preprocessor = Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())])
    X_train = pd.DataFrame(preprocessor.fit_transform(_clean(split.train[kept_features])), columns=kept_features, index=split.train.index)
    X_validation = pd.DataFrame(preprocessor.transform(_clean(split.validation[kept_features])), columns=kept_features, index=split.validation.index)
    X_test = pd.DataFrame(preprocessor.transform(_clean(split.test[kept_features])), columns=kept_features, index=split.test.index)
    encoder = LabelEncoder().fit(CLASS_LABELS)
    return PreparedSplit(
        dataset=prepared,
        feature_columns=kept_features,
        train=split.train,
        validation=split.validation,
        test=split.test,
        preprocessor=preprocessor,
        X_train=X_train,
        X_validation=X_validation,
        X_test=X_test,
        y_train_class=encoder.transform(split.train[target_class].astype(str)),
        y_validation_class=encoder.transform(split.validation[target_class].astype(str)),
        y_test_class=encoder.transform(split.test[target_class].astype(str)),
        y_train_return=pd.to_numeric(split.train[target_return], errors="coerce").to_numpy(dtype=float),
        y_validation_return=pd.to_numeric(split.validation[target_return], errors="coerce").to_numpy(dtype=float),
        y_test_return=pd.to_numeric(split.test[target_return], errors="coerce").to_numpy(dtype=float),
        labels=list(encoder.classes_),
        pruning_report=pruning_report,
    )


def train_candidate_models(prepared: PreparedSplit, horizon: str, min_signal_samples: int) -> dict:
    classification = {}
    for name, model, sample_weight in classification_candidates(prepared):
        started = time.perf_counter()
        fit_kwargs = {}
        if sample_weight is not None:
            fit_kwargs["sample_weight"] = sample_weight
        if name.startswith("xgboost"):
            fit_kwargs["eval_set"] = [(prepared.X_validation, prepared.y_validation_class)]
            fit_kwargs["verbose"] = False
        try:
            model.fit(prepared.X_train, prepared.y_train_class, **fit_kwargs)
        except TypeError:
            model.fit(prepared.X_train, prepared.y_train_class)
        classification[name] = evaluate_classifier(name, model, prepared, horizon, time.perf_counter() - started, min_signal_samples)

    regression = {}
    for name, model in regression_candidates():
        started = time.perf_counter()
        if name == "xgboost":
            try:
                model.fit(prepared.X_train, prepared.y_train_return, eval_set=[(prepared.X_validation, prepared.y_validation_return)], verbose=False)
            except TypeError:
                model.fit(prepared.X_train, prepared.y_train_return)
        else:
            model.fit(prepared.X_train, prepared.y_train_return)
        regression[name] = evaluate_regressor(name, model, prepared, time.perf_counter() - started)

    return {"classification": classification, "regression": regression}


def classification_candidates(prepared: PreparedSplit):
    yield "dummy", DummyClassifier(strategy="most_frequent"), None
    yield "logistic", LogisticRegression(max_iter=1000, random_state=42), None
    yield "logistic_balanced", LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42), None
    for n_estimators in (100, 250):
        for max_depth in (6, 10):
            yield (
                f"random_forest_{n_estimators}_d{max_depth}_leaf5",
                RandomForestClassifier(
                    n_estimators=n_estimators,
                    max_depth=max_depth,
                    min_samples_leaf=5,
                    max_features="sqrt",
                    class_weight="balanced",
                    random_state=42,
                    n_jobs=-1,
                ),
                None,
            )
    if XGBClassifier is not None:
        weights = compute_sample_weight("balanced", prepared.y_train_class)
        for max_depth, learning_rate in ((3, 0.05), (4, 0.07)):
            yield (
                f"xgboost_d{max_depth}_lr{learning_rate}",
                XGBClassifier(
                    objective="multi:softprob",
                    eval_metric="mlogloss",
                    n_estimators=220,
                    max_depth=max_depth,
                    learning_rate=learning_rate,
                    subsample=0.85,
                    colsample_bytree=0.85,
                    tree_method="hist",
                    random_state=42,
                    n_jobs=2,
                    early_stopping_rounds=25,
                ),
                weights,
            )


def regression_candidates():
    yield "dummy", DummyRegressor(strategy="mean")
    yield "ridge", Ridge(alpha=1.0, random_state=42)
    yield "random_forest", RandomForestRegressor(n_estimators=100, max_depth=8, min_samples_leaf=5, max_features="sqrt", random_state=42, n_jobs=-1)
    if XGBRegressor is not None:
        yield "xgboost", XGBRegressor(
            objective="reg:squarederror",
            n_estimators=220,
            max_depth=3,
            learning_rate=0.05,
            subsample=0.85,
            colsample_bytree=0.85,
            tree_method="hist",
            random_state=42,
            n_jobs=2,
            early_stopping_rounds=25,
        )


def evaluate_classifier(name: str, model: Any, prepared: PreparedSplit, horizon: str, fit_seconds: float, min_signal_samples: int) -> dict:
    validation_proba = _predict_proba(model, prepared.X_validation, len(prepared.labels))
    test_proba = _predict_proba(model, prepared.X_test, len(prepared.labels))
    validation_pred = validation_proba.argmax(axis=1)
    test_pred = test_proba.argmax(axis=1)
    validation_backtest = _backtest_frame(prepared.validation, horizon, validation_pred, validation_proba, np.zeros(len(validation_pred)), prepared.labels)
    test_backtest = _backtest_frame(prepared.test, horizon, test_pred, test_proba, np.zeros(len(test_pred)), prepared.labels)
    threshold_selection = select_signal_threshold(validation_backtest, min_samples=min_signal_samples)
    selected_threshold = threshold_selection["threshold"]
    return {
        "fit_seconds": fit_seconds,
        "best_iteration": getattr(model, "best_iteration", None),
        "validation": classification_metrics(_decode(prepared.y_validation_class, prepared.labels), _decode(validation_pred, prepared.labels), validation_proba, labels=prepared.labels),
        "test": classification_metrics(_decode(prepared.y_test_class, prepared.labels), _decode(test_pred, prepared.labels), test_proba, labels=prepared.labels),
        "selected_threshold": threshold_selection,
        "test_threshold_table": threshold_table(test_backtest),
        "test_selected_threshold": threshold_table(test_backtest).get(f"{selected_threshold:.2f}", {}),
        "focus_stock_metrics": focus_signal_metrics(test_backtest, selected_threshold, min_signal_samples),
        "temporal_stability": temporal_stability(test_backtest, selected_threshold),
    }


def evaluate_regressor(name: str, model: Any, prepared: PreparedSplit, fit_seconds: float) -> dict:
    validation_pred = np.asarray(model.predict(prepared.X_validation), dtype=float)
    test_pred = np.asarray(model.predict(prepared.X_test), dtype=float)
    metrics = regression_metrics(prepared.y_test_return, test_pred)
    metrics["correlation"] = _correlation(prepared.y_test_return, test_pred)
    return {
        "fit_seconds": fit_seconds,
        "best_iteration": getattr(model, "best_iteration", None),
        "validation": {**regression_metrics(prepared.y_validation_return, validation_pred), "correlation": _correlation(prepared.y_validation_return, validation_pred)},
        "test": metrics,
        "uncertainty": residual_uncertainty(prepared.y_validation_return, validation_pred),
    }


def build_champion_report(horizon: str, feature_set: str, model_name: str, experiment: dict, min_signal_samples: int) -> dict:
    model_report = experiment["models"]["classification"][model_name]
    regressors = experiment["models"]["regression"]
    best_regressor = min(regressors.items(), key=lambda item: item[1]["validation"]["mae"])
    threshold = model_report["selected_threshold"]["threshold"]
    return {
        "horizon": horizon,
        "feature_set": feature_set,
        "model_family": model_name,
        "regressor_family": best_regressor[0],
        "target_method": "fixed_3pct",
        "confidence_threshold": threshold,
        "min_signal_samples": min_signal_samples,
        "validation_metrics": model_report["validation"],
        "test_metrics": model_report["test"],
        "test_signal_metrics": model_report["test_selected_threshold"],
        "focus_stock_metrics": model_report["focus_stock_metrics"],
        "regression_test_metrics": best_regressor[1]["test"],
        "uncertainty": best_regressor[1]["uncertainty"],
        "temporal_stability": model_report["temporal_stability"],
        "training_universe": [ticker for ticker in REFERENCE_UNIVERSE if ticker not in REFERENCE_ASSETS],
        "feature_count": experiment["pruning"]["kept_feature_count"],
        "training_date": datetime.now(timezone.utc).isoformat(),
        "version": f"{model_name}_{horizon}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
    }


def save_signal_research_report(report: dict, root: Path | None = None) -> Path:
    root = root or PROJECT_ROOT / "artifacts" / "benchmarks"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"signal_research_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    write_json_file(path, report, indent=2, sort_keys=True)
    return path


def save_champion_metadata(report: dict, root: Path | None = None) -> Path:
    root = root or PROJECT_ROOT / "artifacts" / "champions"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"champions_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    write_json_file(path, report["champions"], indent=2, sort_keys=True)
    return path


def _training_rows(dataset: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    return dataset[dataset["ticker"].isin(tickers)].sort_values(["ticker", "date"]).reset_index(drop=True)


def _pruning_report_dict(report: Any) -> dict:
    data = dict(report.__dict__)
    data["removed_feature_count"] = report.removed_feature_count
    return data


def _clean(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)


def _predict_proba(model: Any, X: pd.DataFrame, total_classes: int) -> np.ndarray:
    probabilities = model.predict_proba(X)
    classes = getattr(model, "classes_", np.arange(probabilities.shape[1])).astype(int)
    aligned = np.zeros((len(probabilities), total_classes))
    for source_index, class_index in enumerate(classes):
        aligned[:, int(class_index)] = probabilities[:, source_index]
    row_sums = aligned.sum(axis=1, keepdims=True)
    return np.divide(aligned, row_sums, out=np.zeros_like(aligned), where=row_sums != 0)


def _decode(values: np.ndarray, labels: list[str]) -> np.ndarray:
    labels_array = np.asarray(labels)
    return labels_array[np.asarray(values, dtype=int)]


def _backtest_frame(frame: pd.DataFrame, horizon: str, encoded_pred: np.ndarray, probabilities: np.ndarray, predicted_return: np.ndarray, labels: list[str]) -> pd.DataFrame:
    predicted_class = _decode(encoded_pred, labels)
    return pd.DataFrame(
        {
            "ticker": frame["ticker"].to_numpy(),
            "prediction_date": pd.to_datetime(frame["date"]).to_numpy(),
            "predicted_class": predicted_class,
            "actual_class": frame[f"target_class_{horizon}"].to_numpy(),
            "predicted_probability": probabilities.max(axis=1),
            "actual_return": pd.to_numeric(frame[f"target_return_{horizon}"], errors="coerce").to_numpy(dtype=float),
            "predicted_return": predicted_return,
        }
    )


def focus_signal_metrics(backtest: pd.DataFrame, threshold: float, min_samples: int) -> dict[str, dict]:
    output = {}
    signals = backtest[backtest["predicted_probability"] >= threshold]
    for ticker in FOCUS_STOCKS:
        rows = signals[signals["ticker"] == ticker]
        if len(rows) < min_samples or rows["actual_class"].nunique() < 2:
            output[ticker] = {"status": "INSUFFICIENT_SAMPLE", "sample_count": int(len(rows))}
            continue
        output[ticker] = {
            "status": "OK",
            "sample_count": int(len(rows)),
            "accuracy": float(accuracy_score(rows["actual_class"], rows["predicted_class"])),
            "balanced_accuracy": float(balanced_accuracy_score(rows["actual_class"], rows["predicted_class"])),
        }
    return output


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
                "signal_accuracy": float(accuracy_score(signals["actual_class"], signals["predicted_class"])) if len(signals) else float("nan"),
                "signal_count": int(len(signals)),
            }
        )
    return rows


def assess_report(champions: dict[str, dict]) -> str:
    scores = []
    for champion in champions.values():
        metrics = champion.get("test_signal_metrics", {})
        if metrics.get("sample_count", 0) >= champion.get("min_signal_samples", 30):
            scores.append(metrics.get("accuracy", 0.0))
    if not scores:
        return "WEAK"
    average = sum(scores) / len(scores)
    if average >= 0.58:
        return "PROMISING"
    if average >= 0.52:
        return "MIXED"
    return "WEAK"


def _split_summary(prepared: PreparedSplit) -> dict:
    def one(frame: pd.DataFrame) -> dict:
        dates = pd.to_datetime(frame["date"])
        return {"rows": int(len(frame)), "start": dates.min().date().isoformat(), "end": dates.max().date().isoformat()}

    return {"train": one(prepared.train), "validation": one(prepared.validation), "test": one(prepared.test)}


def _correlation(actual: np.ndarray, predicted: np.ndarray) -> float:
    if len(actual) < 2 or np.std(actual) == 0 or np.std(predicted) == 0:
        return float("nan")
    return float(np.corrcoef(actual, predicted)[0, 1])
