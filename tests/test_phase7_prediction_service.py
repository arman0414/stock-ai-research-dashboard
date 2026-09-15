from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stock_ai.services import prediction as prediction_service


class StubModel:
    def __init__(self, classes: list[int], probabilities: list[float]) -> None:
        self.classes_ = np.array(classes)
        self._probabilities = np.array(probabilities, dtype=float)

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        return np.tile(self._probabilities, (len(X), 1))


class StubRegressor:
    def __init__(self, value: float) -> None:
        self.value = value

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return np.full(len(X), self.value)


def _bundle(raw_probabilities: list[float], calibrated_probabilities: list[float], bullish_threshold: float = 0.60, bearish_threshold: float = 0.60) -> prediction_service.ChampionBundle:
    metadata = {
        "labels": ["DOWN", "NEUTRAL", "UP"],
        "feature_columns": ["f1", "f2"],
        "classifier_random_state": 42,
        "calibration_method": "sigmoid",
        "is_primary_research_horizon": True,
        "thresholds": {
            "bullish": {"class_label": "UP", "threshold": bullish_threshold, "status": "VALIDATED"},
            "bearish": {"class_label": "DOWN", "threshold": bearish_threshold, "status": "VALIDATED"},
        },
        "test_evaluation": {
            "bullish": {"precision": 0.61, "sample_count": 143},
            "bearish": {"precision": 0.55, "sample_count": 80},
        },
        "regression": {"uncertainty": {"residual_p10": -0.05, "residual_p90": 0.10, "p50_abs_error": 0.03}},
        "setup_quality": {
            "stats": {"adx_14": [20.0, 5.0], "trend_clarity": [10.0, 4.0], "pressure_imbalance": [0.1, 0.05], "relative_volume": [1.0, 0.3]},
            "low_cut": -0.3,
            "high_cut": 0.3,
            "pressure_stats": {"buyer_pressure_score": [0.5, 0.1], "seller_pressure_score": [0.5, 0.1]},
        },
    }
    return prediction_service.ChampionBundle(
        horizon="5d",
        classifier=StubModel([0, 1, 2], raw_probabilities),
        calibrated_model=StubModel([0, 1, 2], calibrated_probabilities),
        regressor=StubRegressor(0.05),
        metadata=metadata,
    )


def _feature_row(**overrides) -> pd.Series:
    base = {
        "f1": 1.0,
        "f2": 2.0,
        "close": 100.0,
        "date": pd.Timestamp("2026-09-10"),
        "buyer_pressure_score": 0.9,
        "seller_pressure_score": 0.1,
        "nearest_support": 95.0,
        "nearest_resistance": 110.0,
        "adx_14": 30.0,
        "trend_structure_score": 15.0,
        "relative_volume": 1.5,
    }
    base.update(overrides)
    return pd.Series(base)


def test_bullish_signal_uses_calibrated_not_raw_probability() -> None:
    # Raw probability screams UP (0.95) but calibrated probability is well
    # below the validated bullish threshold -- must NOT fire bullish.
    bundle = _bundle(raw_probabilities=[0.02, 0.03, 0.95], calibrated_probabilities=[0.30, 0.30, 0.40])
    signal = prediction_service.build_signal_from_bundle(bundle, _feature_row(), current_price=100.0, ticker="NVDA", as_of="2026-09-10")
    assert signal["classification"]["direction"] == "UP"
    assert signal["classification"]["raw_probability"] == pytest.approx(0.95)
    assert signal["classification"]["calibrated_probability"] == pytest.approx(0.40)
    assert signal["classification"]["signal_status"] == "NO_STRONG_SIGNAL"


def test_bullish_signal_fires_when_calibrated_probability_above_threshold() -> None:
    bundle = _bundle(raw_probabilities=[0.10, 0.10, 0.80], calibrated_probabilities=[0.10, 0.20, 0.70])
    signal = prediction_service.build_signal_from_bundle(bundle, _feature_row(), current_price=100.0, ticker="NVDA", as_of="2026-09-10")
    assert signal["classification"]["signal_status"] == "BULLISH"
    assert signal["classification"]["historical_signal_accuracy"] == pytest.approx(0.61)
    assert signal["classification"]["historical_signal_samples"] == 143


def test_no_strong_signal_has_null_historical_reliability() -> None:
    bundle = _bundle(raw_probabilities=[0.34, 0.33, 0.33], calibrated_probabilities=[0.34, 0.33, 0.33])
    signal = prediction_service.build_signal_from_bundle(bundle, _feature_row(), current_price=100.0, ticker="NVDA", as_of="2026-09-10")
    assert signal["classification"]["signal_status"] == "NO_STRONG_SIGNAL"
    assert signal["classification"]["historical_signal_accuracy"] is None
    assert signal["classification"]["historical_signal_samples"] is None


def test_regression_target_price_and_uncertainty_range() -> None:
    bundle = _bundle(raw_probabilities=[0.34, 0.33, 0.33], calibrated_probabilities=[0.34, 0.33, 0.33])
    signal = prediction_service.build_signal_from_bundle(bundle, _feature_row(), current_price=100.0, ticker="NVDA", as_of="2026-09-10")
    regression = signal["regression"]
    assert regression["predicted_return"] == pytest.approx(0.05)
    assert regression["model_target_price"] == pytest.approx(105.0)
    # residual_p10=-0.05 -> low bound at (1+0.05-0.05)=1.00x current price
    assert regression["uncertainty_low"] == pytest.approx(100.0)
    # residual_p90=0.10 -> high bound at (1+0.05+0.10)=1.15x current price
    assert regression["uncertainty_high"] == pytest.approx(115.0)
    assert regression["uncertainty_low"] < regression["model_target_price"] < regression["uncertainty_high"]


def test_setup_quality_strong_bucket_from_favorable_features() -> None:
    bundle = _bundle(raw_probabilities=[0.34, 0.33, 0.33], calibrated_probabilities=[0.34, 0.33, 0.33])
    row = _feature_row(adx_14=40.0, trend_structure_score=25.0, relative_volume=2.0, buyer_pressure_score=0.95, seller_pressure_score=0.05)
    signal = prediction_service.build_signal_from_bundle(bundle, row, current_price=100.0, ticker="NVDA", as_of="2026-09-10")
    assert signal["setup"]["quality"] in ("STRONG", "MODERATE")
    assert signal["setup"]["buyer_pressure"] == "STRONG"
    assert signal["setup"]["support"] == pytest.approx(95.0)
    assert signal["setup"]["resistance"] == pytest.approx(110.0)


def test_multi_horizon_response_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    bundle_5d = _bundle(raw_probabilities=[0.10, 0.10, 0.80], calibrated_probabilities=[0.10, 0.20, 0.70])
    bundle_5d.horizon = "5d"
    bundle_10d = _bundle(raw_probabilities=[0.34, 0.33, 0.33], calibrated_probabilities=[0.34, 0.33, 0.33])
    bundle_10d.horizon = "10d"

    def fake_load_bundle(horizon, artifacts_root=None, force_reload=False):
        if horizon == "5d":
            return bundle_5d
        if horizon == "10d":
            return bundle_10d
        raise FileNotFoundError(horizon)

    monkeypatch.setattr(prediction_service, "load_bundle", fake_load_bundle)
    monkeypatch.setattr(prediction_service, "build_latest_feature_row", lambda db, ticker: _feature_row())
    monkeypatch.setattr(prediction_service, "build_market_context", lambda db, ticker, feature_row: {"spy_trend": "NEUTRAL"})

    result = prediction_service.predict_multi_horizon(db=None, ticker="NVDA", horizons=("5d", "10d", "15d"))

    assert result["ticker"] == "NVDA"
    assert result["primary_research_horizon"] == "5d"
    assert set(result["predictions"].keys()) == {"5d", "10d", "15d"}
    assert result["predictions"]["5d"]["classification"]["signal_status"] == "BULLISH"
    assert result["predictions"]["10d"]["classification"]["signal_status"] == "NO_STRONG_SIGNAL"
    assert result["predictions"]["15d"] is None  # missing champion artifact handled gracefully


def test_multi_horizon_returns_none_when_no_feature_row(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prediction_service, "build_latest_feature_row", lambda db, ticker: None)
    result = prediction_service.predict_multi_horizon(db=None, ticker="UNKNOWN")
    assert result is None
