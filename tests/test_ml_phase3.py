from __future__ import annotations

import numpy as np
import pandas as pd

from stock_ai.ml.artifacts import load_model_artifact, save_model_artifact
from stock_ai.ml.backtest import build_prediction_backtest, evaluate_signal_strategy
from stock_ai.ml.classifiers import fit_classifier
from stock_ai.ml.config import ModelConfig, XGBoostConfig
from stock_ai.ml.confidence import confidence_label
from stock_ai.ml.evaluation import classification_metrics, regression_metrics, select_best_model
from stock_ai.ml.preprocessing import fit_preprocessor, select_model_feature_columns
from stock_ai.ml.regressors import fit_regressor
from stock_ai.ml.split import chronological_split
from stock_ai.ml.training import train_all_horizons, train_horizon_models


def synthetic_ml_dataset(rows: int = 360) -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-02", periods=rows)
    index = np.arange(rows)
    f1 = np.sin(index / 5)
    f2 = np.cos(index / 7)
    f3 = index / rows
    close = 100 + index * 0.1 + f1
    data = pd.DataFrame(
        {
            "date": dates,
            "ticker": "AAPL",
            "close": close,
            "open": close - 0.1,
            "high": close + 0.5,
            "low": close - 0.5,
            "adjusted_close": close,
            "volume": 1_000_000 + index,
            "feature_momentum": f1,
            "feature_reversal": f2,
            "feature_trend": f3,
        }
    )

    for horizon, sessions in {"5d": 5, "10d": 10, "15d": 15, "21d": 21, "63d": 63}.items():
        future_signal = np.sin((index + sessions) / 5)
        target_return = np.where(future_signal > 0.45, 0.06, np.where(future_signal < -0.45, -0.06, 0.0))
        data[f"target_return_{horizon}"] = target_return
        data[f"target_close_{horizon}"] = data["close"] * (1 + target_return)
        data[f"target_class_{horizon}"] = np.where(target_return > 0.03, "UP", np.where(target_return < -0.03, "DOWN", "NEUTRAL"))

    return data


def tiny_config() -> ModelConfig:
    return ModelConfig(xgboost=XGBoostConfig(n_estimators=5, max_depth=2, learning_rate=0.1, random_state=7, n_jobs=1), random_state=7)


def test_chronological_split_preserves_order_and_purge_gap() -> None:
    dataset = synthetic_ml_dataset()

    split = chronological_split(dataset, train_size=0.6, validation_size=0.2, purge_gap=10)

    assert split.train["date"].is_monotonic_increasing
    assert split.validation["date"].is_monotonic_increasing
    assert split.test["date"].is_monotonic_increasing
    assert split.train["date"].max() < split.validation["date"].min()
    assert split.validation["date"].max() < split.test["date"].min()

    all_dates = pd.Index(sorted(dataset["date"].unique()))
    train_end_position = all_dates.get_loc(split.train["date"].max())
    validation_start_position = all_dates.get_loc(split.validation["date"].min())
    validation_end_position = all_dates.get_loc(split.validation["date"].max())
    test_start_position = all_dates.get_loc(split.test["date"].min())
    assert validation_start_position - train_end_position - 1 == 10
    assert test_start_position - validation_end_position - 1 == 10


def test_preprocessing_fits_training_data_only_and_excludes_targets() -> None:
    dataset = synthetic_ml_dataset()
    split = chronological_split(dataset, train_size=0.6, validation_size=0.2, purge_gap=5)
    validation_with_extreme = split.validation.copy()
    validation_with_extreme["feature_momentum"] = 999_999

    preprocessor = fit_preprocessor(split.train, scale=True)
    transformed = preprocessor.transform(validation_with_extreme)

    assert "target_return_10d" not in select_model_feature_columns(dataset)
    assert "date" not in preprocessor.feature_columns
    assert "ticker" not in preprocessor.feature_columns
    assert "close" not in preprocessor.feature_columns
    assert np.isfinite(transformed.to_numpy()).all()

    imputer = preprocessor.pipeline.named_steps["imputer"]
    feature_index = preprocessor.feature_columns.index("feature_momentum")
    assert imputer.statistics_[feature_index] != 999_999


def test_classifier_regressor_xgboost_and_probability_outputs() -> None:
    dataset = synthetic_ml_dataset()
    split = chronological_split(dataset, train_size=0.6, validation_size=0.2, purge_gap=10)
    preprocessor = fit_preprocessor(split.train, scale=True)

    for model_name in ["dummy", "logistic", "random_forest", "xgboost"]:
        classifier = fit_classifier(model_name, split.train, "target_class_10d", preprocessor, config=tiny_config())
        probabilities = classifier.predict_proba(split.validation)
        predictions = classifier.predict(split.validation)
        assert probabilities.shape == (len(split.validation), 3)
        assert np.allclose(probabilities.sum(axis=1), 1.0)
        assert set(predictions).issubset({"UP", "NEUTRAL", "DOWN"})

    for model_name in ["dummy", "ridge", "random_forest", "xgboost"]:
        regressor = fit_regressor(model_name, split.train, "target_return_10d", preprocessor, config=tiny_config())
        predictions = regressor.predict(split.validation)
        assert len(predictions) == len(split.validation)
        assert np.isfinite(predictions).all()


def test_metrics_confidence_and_model_selection_use_validation_only() -> None:
    y_true = np.array(["UP", "DOWN", "NEUTRAL", "UP"])
    y_pred = np.array(["UP", "DOWN", "UP", "NEUTRAL"])
    probabilities = np.array(
        [
            [0.05, 0.10, 0.85],
            [0.80, 0.10, 0.10],
            [0.10, 0.30, 0.60],
            [0.10, 0.70, 0.20],
        ]
    )

    metrics = classification_metrics(y_true, y_pred, probabilities)
    assert metrics["accuracy"] == 0.5
    assert metrics["macro_f1"] > 0
    assert metrics["confidence"][">=0.80"]["count"] == 2
    assert "brier_score_multiclass" in metrics

    regression = regression_metrics(np.array([0.05, -0.04, 0.01]), np.array([0.03, -0.01, -0.02]))
    assert regression["mae"] > 0
    assert regression["direction_accuracy"] == 2 / 3

    assert confidence_label(0.49) == "NO_STRONG_SIGNAL"
    assert confidence_label(0.55) == "LOW"
    assert confidence_label(0.65) == "MEDIUM"
    assert confidence_label(0.75) == "HIGH"
    assert confidence_label(0.85) == "VERY_HIGH"

    selected = select_best_model({"dummy": {"macro_f1": 0.2}, "logistic": {"macro_f1": 0.4}}, "macro_f1")
    assert selected.best_model_name == "logistic"
    assert selected.used_test_set is False


def test_backtest_calculations_and_non_overlapping_signals() -> None:
    dataset = synthetic_ml_dataset(rows=90).iloc[:20].copy()
    predicted_class = np.array(["UP", "DOWN"] * 10)
    probabilities = np.tile(np.array([[0.05, 0.10, 0.85], [0.75, 0.15, 0.10]]), (10, 1))
    predicted_return = np.array([0.05, -0.04] * 10)

    backtest = build_prediction_backtest(dataset, "10d", predicted_class, probabilities, predicted_return)

    assert backtest.loc[0, "predicted_target_price"] == backtest.loc[0, "current_price"] * 1.05
    assert "classification_correct" in backtest.columns
    assert backtest["prediction_date"].is_monotonic_increasing

    raw = evaluate_signal_strategy(backtest, probability_threshold=0.60, non_overlapping=False, horizon_sessions=10)
    non_overlapping = evaluate_signal_strategy(backtest, probability_threshold=0.60, non_overlapping=True, horizon_sessions=10)
    assert raw["number_of_signals"] == 20
    assert non_overlapping["number_of_signals"] < raw["number_of_signals"]


def test_artifact_save_and_reload(tmp_path) -> None:
    dataset = synthetic_ml_dataset()
    split = chronological_split(dataset, train_size=0.6, validation_size=0.2, purge_gap=10)
    preprocessor = fit_preprocessor(split.train)
    classifier = fit_classifier("dummy", split.train, "target_class_10d", preprocessor)

    artifact_path = save_model_artifact(
        classifier,
        {"model_version": "dummy_classification_10d_test", "task": "classification", "horizon": "10d"},
        tmp_path / "artifact",
    )
    loaded, metadata = load_model_artifact(artifact_path)

    assert metadata["model_version"] == "dummy_classification_10d_test"
    assert len(loaded.predict(split.validation)) == len(split.validation)


def test_train_horizon_models_and_all_horizons_independently() -> None:
    dataset = synthetic_ml_dataset()

    result = train_horizon_models(
        dataset,
        horizon="10d",
        classification_models=["dummy", "logistic", "random_forest", "xgboost"],
        regression_models=["dummy", "ridge", "random_forest", "xgboost"],
        config=tiny_config(),
    )

    assert result.horizon == "10d"
    assert result.best_classifier_name in {"dummy", "logistic", "random_forest", "xgboost"}
    assert result.best_regressor_name in {"dummy", "ridge", "random_forest", "xgboost"}
    assert result.model_selection["test_set_used_for_selection"] is False
    assert not result.backtest.empty
    assert result.split_summary["purge_gap"] == 10

    all_results = train_all_horizons(
        dataset,
        horizons=["5d", "10d"],
        classification_models=["dummy"],
        regression_models=["dummy"],
        config=tiny_config(),
    )
    assert set(all_results) == {"5d", "10d"}
    assert all_results["5d"].horizon == "5d"
    assert all_results["10d"].horizon == "10d"

