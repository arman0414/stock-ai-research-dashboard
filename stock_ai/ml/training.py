from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from stock_ai.features.targets import DEFAULT_HORIZONS
from stock_ai.ml.artifacts import make_model_version, save_model_artifact
from stock_ai.ml.backtest import build_prediction_backtest, evaluate_signal_strategy
from stock_ai.ml.classifiers import FittedClassifier, fit_classifier, top_feature_importance as classifier_importance
from stock_ai.ml.config import DEFAULT_CLASSIFICATION_MODELS, DEFAULT_REGRESSION_MODELS, ModelConfig
from stock_ai.ml.evaluation import (
    class_distribution,
    classification_metrics,
    regression_metrics,
    select_best_model,
)
from stock_ai.ml.preprocessing import fit_preprocessor
from stock_ai.ml.regressors import FittedRegressor, fit_regressor, top_feature_importance as regressor_importance
from stock_ai.ml.split import chronological_split


@dataclass
class HorizonTrainingResult:
    horizon: str
    split_summary: dict
    class_distribution: dict
    classification_validation_metrics: dict[str, dict]
    classification_test_metrics: dict[str, dict]
    regression_validation_metrics: dict[str, dict]
    regression_test_metrics: dict[str, dict]
    best_classifier_name: str
    best_regressor_name: str
    best_classifier: FittedClassifier
    best_regressor: FittedRegressor
    backtest: pd.DataFrame
    strategy_metrics: dict
    feature_importance: dict[str, list[dict]]
    model_selection: dict


def train_horizon_models(
    dataset: pd.DataFrame,
    horizon: str,
    classification_models: list[str] | None = None,
    regression_models: list[str] | None = None,
    config: ModelConfig | None = None,
    save_artifacts_to: str | Path | None = None,
) -> HorizonTrainingResult:
    if horizon not in DEFAULT_HORIZONS:
        raise ValueError(f"Unsupported horizon: {horizon}")

    classification_models = classification_models or DEFAULT_CLASSIFICATION_MODELS
    regression_models = regression_models or DEFAULT_REGRESSION_MODELS
    config = config or ModelConfig()
    target_class = f"target_class_{horizon}"
    target_return = f"target_return_{horizon}"
    target_close = f"target_close_{horizon}"

    required_targets = [target_class, target_return, target_close]
    prepared = dataset.dropna(subset=required_targets).copy()
    prepared = prepared.sort_values(["ticker", "date"] if "ticker" in prepared.columns else ["date"]).reset_index(drop=True)

    split = chronological_split(prepared, purge_gap=DEFAULT_HORIZONS[horizon])
    preprocessor = fit_preprocessor(split.train, scale=True)

    classification_validation_metrics: dict[str, dict] = {}
    classification_test_metrics: dict[str, dict] = {}
    fitted_classifiers: dict[str, FittedClassifier] = {}

    for model_name in classification_models:
        classifier = fit_classifier(model_name, split.train, target_class, preprocessor, config=config)
        fitted_classifiers[model_name] = classifier
        validation_pred = classifier.predict(split.validation)
        validation_proba = classifier.predict_proba(split.validation)
        test_pred = classifier.predict(split.test)
        test_proba = classifier.predict_proba(split.test)
        labels = list(classifier.label_encoder.classes_)
        classification_validation_metrics[model_name] = classification_metrics(split.validation[target_class], validation_pred, validation_proba, labels=labels)
        classification_test_metrics[model_name] = classification_metrics(split.test[target_class], test_pred, test_proba, labels=labels)

    classifier_selection = select_best_model(classification_validation_metrics, "macro_f1", greater_is_better=True)
    best_classifier = fitted_classifiers[classifier_selection.best_model_name]

    regression_validation_metrics: dict[str, dict] = {}
    regression_test_metrics: dict[str, dict] = {}
    fitted_regressors: dict[str, FittedRegressor] = {}
    for model_name in regression_models:
        regressor = fit_regressor(model_name, split.train, target_return, preprocessor, config=config)
        fitted_regressors[model_name] = regressor
        validation_pred = regressor.predict(split.validation)
        test_pred = regressor.predict(split.test)
        regression_validation_metrics[model_name] = regression_metrics(split.validation[target_return], validation_pred)
        regression_test_metrics[model_name] = regression_metrics(split.test[target_return], test_pred)

    regressor_selection = select_best_model(regression_validation_metrics, "mae", greater_is_better=False)
    best_regressor = fitted_regressors[regressor_selection.best_model_name]

    test_class_pred = best_classifier.predict(split.test)
    test_proba = best_classifier.predict_proba(split.test)
    test_return_pred = best_regressor.predict(split.test)
    backtest = build_prediction_backtest(split.test, horizon, test_class_pred, test_proba, test_return_pred)

    result = HorizonTrainingResult(
        horizon=horizon,
        split_summary=_split_summary(split.train, split.validation, split.test, DEFAULT_HORIZONS[horizon]),
        class_distribution=class_distribution(prepared[target_class]),
        classification_validation_metrics=classification_validation_metrics,
        classification_test_metrics=classification_test_metrics,
        regression_validation_metrics=regression_validation_metrics,
        regression_test_metrics=regression_test_metrics,
        best_classifier_name=classifier_selection.best_model_name,
        best_regressor_name=regressor_selection.best_model_name,
        best_classifier=best_classifier,
        best_regressor=best_regressor,
        backtest=backtest,
        strategy_metrics=evaluate_signal_strategy(backtest, probability_threshold=0.60, non_overlapping=True, horizon_sessions=DEFAULT_HORIZONS[horizon]),
        feature_importance={
            "classification": classifier_importance(best_classifier),
            "regression": regressor_importance(best_regressor),
        },
        model_selection={
            "classification": classifier_selection,
            "regression": regressor_selection,
            "test_set_used_for_selection": False,
        },
    )

    if save_artifacts_to:
        save_best_artifacts(result, save_artifacts_to)

    return result


def train_all_horizons(dataset: pd.DataFrame, horizons: list[str] | None = None, **kwargs) -> dict[str, HorizonTrainingResult]:
    selected_horizons = horizons or list(DEFAULT_HORIZONS)
    return {horizon: train_horizon_models(dataset, horizon=horizon, **kwargs) for horizon in selected_horizons}


def save_best_artifacts(result: HorizonTrainingResult, root_dir: str | Path) -> dict[str, Path]:
    root = Path(root_dir)
    timestamp = datetime.now(timezone.utc)
    paths: dict[str, Path] = {}

    classifier_metadata = _metadata(result, task="classification", model_name=result.best_classifier_name, timestamp=timestamp)
    classifier_version = classifier_metadata["model_version"]
    paths["classification"] = save_model_artifact(
        result.best_classifier,
        classifier_metadata,
        root / "classification" / result.horizon / classifier_version,
    )

    regressor_metadata = _metadata(result, task="regression", model_name=result.best_regressor_name, timestamp=timestamp)
    regressor_version = regressor_metadata["model_version"]
    paths["regression"] = save_model_artifact(
        result.best_regressor,
        regressor_metadata,
        root / "regression" / result.horizon / regressor_version,
    )
    return paths


def _metadata(result: HorizonTrainingResult, task: str, model_name: str, timestamp: datetime) -> dict:
    split = result.split_summary
    return {
        "model_version": make_model_version(model_name, task, result.horizon, timestamp=timestamp),
        "task": task,
        "horizon": result.horizon,
        "model_type": model_name,
        "features": result.best_classifier.feature_columns if task == "classification" else result.best_regressor.feature_columns,
        "train_start": split["train"]["start"],
        "train_end": split["train"]["end"],
        "validation_start": split["validation"]["start"],
        "validation_end": split["validation"]["end"],
        "test_start": split["test"]["start"],
        "test_end": split["test"]["end"],
        "metrics": result.classification_test_metrics.get(model_name) if task == "classification" else result.regression_test_metrics.get(model_name),
        "configuration": {"selection_uses_validation_only": True, "purge_gap": split["purge_gap"]},
        "created_at": timestamp,
    }


def _split_summary(train: pd.DataFrame, validation: pd.DataFrame, test: pd.DataFrame, purge_gap: int) -> dict:
    def summary(frame: pd.DataFrame) -> dict:
        dates = pd.to_datetime(frame["date"])
        return {
            "rows": int(len(frame)),
            "start": dates.min().date().isoformat(),
            "end": dates.max().date().isoformat(),
        }

    return {
        "purge_gap": purge_gap,
        "train": summary(train),
        "validation": summary(validation),
        "test": summary(test),
    }

