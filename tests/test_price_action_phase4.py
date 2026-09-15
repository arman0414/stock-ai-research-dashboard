from __future__ import annotations

import numpy as np
import pandas as pd

from stock_ai.features.price_action import add_price_action_features, summarize_latest_structure
from stock_ai.features.technical import add_technical_features


def price_action_prices(rows: int = 120) -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-02", periods=rows)
    base = 50 + np.sin(np.arange(rows) / 4) + np.arange(rows) * 0.05
    close = base.copy()
    open_ = close - 0.2
    high = np.maximum(open_, close) + 0.5
    low = np.minimum(open_, close) - 0.5
    volume = 1_000_000 + np.arange(rows) * 1000

    high[75] = high[:75].max() + 3
    close[75] = high[:75].max() + 2
    open_[75] = close[75] - 1
    low[75] = open_[75] - 0.5
    volume[75] = 2_500_000

    high[80] = high[:80].max() + 2
    close[80] = high[:80].max() - 0.2
    open_[80] = close[80] - 0.1
    low[80] = close[80] - 0.3

    return pd.DataFrame(
        {
            "date": dates,
            "ticker": "AAPL",
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "adjusted_close": close,
            "volume": volume,
        }
    )


def featured_prices() -> pd.DataFrame:
    return add_price_action_features(add_technical_features(price_action_prices()))


def test_candle_wicks_close_location_and_rejection_strengths() -> None:
    features = featured_prices()
    row = features.iloc[20]

    assert row["candle_body"] == abs(row["close"] - row["open"])
    assert row["candle_range"] == row["high"] - row["low"]
    assert row["upper_wick"] == row["high"] - max(row["open"], row["close"])
    assert row["lower_wick"] == min(row["open"], row["close"]) - row["low"]
    assert row["close_location"] == (row["close"] - row["low"]) / (row["high"] - row["low"])
    assert row["bullish_rejection_strength"] >= 0
    assert row["bearish_rejection_strength"] >= 0


def test_obv_adl_cmf_mfi_adx_and_pressure_features_are_present() -> None:
    features = featured_prices()
    row = features.iloc[60]

    for column in ["obv", "adl", "cmf_20", "mfi_14", "adx_14", "plus_di_14", "minus_di_14"]:
        assert pd.notna(row[column])
    assert row["buyer_pressure_5d"] >= 0
    assert row["seller_pressure_5d"] >= 0
    assert row["buyer_pressure_score"] >= 0
    assert row["seller_pressure_score"] >= 0


def test_structure_support_resistance_breakout_failed_breakout_and_summary() -> None:
    features = featured_prices()

    assert features.loc[75, "breakout_20d"] == 1
    assert features.loc[80, "failed_breakout"] == 1
    assert pd.notna(features.loc[70, "nearest_support"])
    assert pd.notna(features.loc[70, "nearest_resistance"])
    assert features.loc[70, "support_touch_count"] >= 0
    assert features.loc[70, "resistance_touch_count"] >= 0
    assert features.loc[70, "consolidation_score"] >= 0

    summary = summarize_latest_structure(features)
    assert summary is not None
    assert summary["market_structure"] in {"BULLISH", "NEUTRAL", "BEARISH"}
    assert "important_observations" in summary


def test_price_action_features_do_not_change_when_future_candles_change() -> None:
    original = price_action_prices()
    modified = original.copy()
    modified.loc[90:, ["open", "high", "low", "close"]] = modified.loc[90:, ["open", "high", "low", "close"]] * 10

    original_features = add_price_action_features(add_technical_features(original))
    modified_features = add_price_action_features(add_technical_features(modified))
    columns = [
        "nearest_support",
        "nearest_resistance",
        "trend_structure_score",
        "buyer_pressure_score",
        "seller_pressure_score",
        "breakout_20d",
        "failed_breakout",
        "support_rejection_strength",
        "resistance_rejection_strength",
    ]
    pd.testing.assert_frame_equal(original_features.loc[:80, columns], modified_features.loc[:80, columns])

