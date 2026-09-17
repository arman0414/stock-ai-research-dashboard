from __future__ import annotations

import json
import math
import warnings

import numpy as np
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stock_ai.features.price_action import add_price_action_features
from stock_ai.main import SafeJSONResponse
from stock_ai.ml.signals import SignalPolicy, make_signal_object
from stock_ai.utils.json_safe import dumps_json, sanitize_json


def test_json_sanitizer_converts_non_finite_numbers_to_null() -> None:
    payload = {
        "nan": float("nan"),
        "pos_inf": float("inf"),
        "neg_inf": float("-inf"),
        "valid": 1.25,
        "nested": [np.float64("nan"), {"value": pd.NA, "ok": np.float64(2.5)}],
    }

    sanitized = sanitize_json(payload)

    assert sanitized == {
        "nan": None,
        "pos_inf": None,
        "neg_inf": None,
        "valid": 1.25,
        "nested": [None, {"value": None, "ok": 2.5}],
    }
    assert json.loads(dumps_json(sanitized, allow_nan=False)) == sanitized


def test_api_json_response_replaces_non_finite_values_with_null() -> None:
    app = FastAPI(default_response_class=SafeJSONResponse)

    @app.get("/metrics")
    def metrics() -> dict:
        return {"macro_f1": float("nan"), "nested": {"coverage": float("inf")}}

    response = TestClient(app).get("/metrics")

    assert response.status_code == 200
    assert response.json() == {"macro_f1": None, "nested": {"coverage": None}}
    json.dumps(response.json(), allow_nan=False)


def test_price_action_pct_change_has_no_future_warning() -> None:
    dates = pd.bdate_range("2025-01-02", periods=80)
    close = pd.Series(np.linspace(100, 130, len(dates)))
    prices = pd.DataFrame(
        {
            "date": dates,
            "ticker": "NVDA",
            "open": close - 0.5,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "adjusted_close": close,
            "volume": 1_000_000 + np.arange(len(dates)),
            "bollinger_width": [np.nan] * 20 + list(np.linspace(0.05, 0.10, len(dates) - 20)),
        }
    )

    with warnings.catch_warnings():
        warnings.simplefilter("error", FutureWarning)
        result = add_price_action_features(prices)

    assert "bb_width_change" in result.columns


def test_signal_object_output_is_unchanged_by_json_sanitization() -> None:
    signal = make_signal_object(
        ticker="NVDA",
        horizon="5d",
        current_price=100.0,
        predicted_direction="UP",
        probability=0.72,
        predicted_return=0.05,
        policy=SignalPolicy(threshold=0.60),
        historical_signal_accuracy=0.64,
        historical_signal_samples=84,
        model_version="demo",
        typical_abs_error=0.04,
    )

    sanitized = sanitize_json(signal)

    assert sanitized["predicted_return"] == pytest.approx(0.05)
    assert sanitized["model_target_price"] == pytest.approx(105.0)
    assert sanitized["probability"] == pytest.approx(0.72)
    assert sanitized["signal_status"] == "STRONG_SIGNAL"

