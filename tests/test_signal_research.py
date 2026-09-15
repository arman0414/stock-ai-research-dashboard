from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stock_ai.ml.feature_pruning import prune_features
from stock_ai.ml.signals import make_signal_object, residual_uncertainty, select_signal_threshold, signal_from_prediction
from stock_ai.ml.signal_research import build_champion_report


def signal_backtest(rows: int = 80) -> pd.DataFrame:
    probabilities = np.linspace(0.45, 0.84, rows)
    predicted = np.where(np.arange(rows) % 2 == 0, "UP", "DOWN")
    actual = predicted.copy()
    actual[:20] = np.where(actual[:20] == "UP", "DOWN", "UP")
    return pd.DataFrame(
        {
            "ticker": ["RDDT"] * rows,
            "prediction_date": pd.bdate_range("2025-01-02", periods=rows),
            "predicted_class": predicted,
            "actual_class": actual,
            "predicted_probability": probabilities,
            "actual_return": np.where(actual == "UP", 0.03, -0.03),
            "predicted_return": np.where(predicted == "UP", 0.02, -0.02),
        }
    )


def test_feature_pruning_removes_constant_duplicate_and_sparse_columns() -> None:
    frame = pd.DataFrame(
        {
            "constant": [1, 1, 1, 1],
            "duplicate_a": [1, 2, 3, 4],
            "duplicate_b": [1, 2, 3, 4],
            "sparse": [np.nan, np.nan, np.nan, 1],
            "useful": [4, 3, 2, 1],
        }
    )
    kept, report = prune_features(frame, list(frame.columns), sparse_threshold=0.70)

    assert "constant" not in kept
    assert "duplicate_b" not in kept
    assert "sparse" not in kept
    assert "useful" in kept
    assert report.removed_feature_count == 3


def test_threshold_selection_enforces_minimum_samples() -> None:
    selected = select_signal_threshold(signal_backtest(), min_samples=30)

    assert selected["threshold"] <= 0.70
    assert selected["metrics"]["sample_count"] >= 30


def test_abstention_logic() -> None:
    assert signal_from_prediction("UP", probability=0.59, threshold=0.60)[0] == "NO_STRONG_SIGNAL"
    assert signal_from_prediction("UP", probability=0.72, threshold=0.60) == ("BULLISH", "HIGH")
    assert signal_from_prediction("DOWN", probability=0.72, threshold=0.60) == ("BEARISH", "HIGH")
    assert signal_from_prediction("NEUTRAL", probability=0.90, threshold=0.60)[0] == "NO_STRONG_SIGNAL"


def test_signal_object_constructs_target_price_and_status() -> None:
    signal = make_signal_object(
        ticker="NVDA",
        horizon="5d",
        current_price=100,
        predicted_direction="UP",
        probability=0.71,
        predicted_return=0.05,
        policy=type("Policy", (), {"threshold": 0.60})(),
        historical_signal_accuracy=0.63,
        historical_signal_samples=84,
        model_version="demo",
        typical_abs_error=0.04,
    )

    assert signal["signal_status"] == "STRONG_SIGNAL"
    assert signal["model_target_price"] == 105
    assert signal["signal"] == "BULLISH"


def test_residual_uncertainty_quantiles() -> None:
    uncertainty = residual_uncertainty(np.array([0.0, 0.1, -0.1]), np.array([0.01, 0.08, -0.05]))

    assert uncertainty["median_abs_error"] == pytest.approx(0.02)
    assert uncertainty["p90_abs_error"] > uncertainty["median_abs_error"]


def test_champion_report_uses_validation_selected_threshold_and_regressor() -> None:
    experiment = {
        "pruning": {"kept_feature_count": 3},
        "models": {
            "classification": {
                "logistic": {
                    "selected_threshold": {"threshold": 0.65},
                    "validation": {"macro_f1": 0.5},
                    "test": {"macro_f1": 0.4},
                    "test_selected_threshold": {"sample_count": 30, "accuracy": 0.6},
                    "focus_stock_metrics": {},
                    "temporal_stability": [],
                }
            },
            "regression": {
                "ridge": {"validation": {"mae": 0.2}, "test": {"mae": 0.25}, "uncertainty": {}},
                "dummy": {"validation": {"mae": 0.3}, "test": {"mae": 0.35}, "uncertainty": {}},
            },
        },
    }

    champion = build_champion_report("5d", "technical", "logistic", experiment, min_signal_samples=30)

    assert champion["confidence_threshold"] == 0.65
    assert champion["regressor_family"] == "ridge"
    assert champion["feature_count"] == 3


def test_rddt_dates_are_chronological_for_sanity_checks() -> None:
    dates = pd.bdate_range("2024-03-22", periods=80)
    train = dates[:50]
    validation = dates[55:65]
    test = dates[70:]

    assert train.max() < validation.min()
    assert validation.max() < test.min()
