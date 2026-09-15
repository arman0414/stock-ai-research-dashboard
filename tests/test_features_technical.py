from __future__ import annotations

import numpy as np
import pandas as pd

from stock_ai.features.technical import add_technical_features


def synthetic_prices(rows: int = 320, ticker: str = "AAPL") -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-02", periods=rows)
    close = pd.Series(np.arange(100.0, 100.0 + rows), index=dates)
    return pd.DataFrame(
        {
            "date": dates,
            "ticker": ticker,
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "adjusted_close": close,
            "volume": np.arange(1_000_000, 1_000_000 + rows),
        }
    ).reset_index(drop=True)


def test_return_sma_ema_and_volume_calculations() -> None:
    prices = synthetic_prices()

    features = add_technical_features(prices)
    row = features.iloc[20]

    assert row["return_1d"] == prices["close"].iloc[20] / prices["close"].iloc[19] - 1
    assert row["return_5d"] == prices["close"].iloc[20] / prices["close"].iloc[15] - 1
    assert row["sma_5"] == prices["close"].iloc[16:21].mean()
    assert row["sma_20"] == prices["close"].iloc[1:21].mean()

    expected_ema_12 = prices["close"].ewm(span=12, adjust=False, min_periods=12).mean().iloc[20]
    assert row["ema_12"] == expected_ema_12

    assert row["volume_sma_20"] == prices["volume"].iloc[1:21].mean()
    assert row["relative_volume"] == prices["volume"].iloc[20] / prices["volume"].iloc[1:21].mean()


def test_rsi_macd_atr_bollinger_and_position_features_are_sane() -> None:
    prices = synthetic_prices()

    features = add_technical_features(prices)
    row = features.iloc[260]

    assert row["rsi_14"] == 100
    assert row["macd"] > 0
    assert pd.notna(row["macd_signal"])
    assert row["macd_histogram"] == row["macd"] - row["macd_signal"]
    assert row["atr_14"] > 0
    assert row["bollinger_upper"] > row["bollinger_lower"]
    assert row["bollinger_width"] > 0

    assert row["distance_from_sma20"] == row["close"] / row["sma_20"] - 1
    assert row["distance_from_sma50"] == row["close"] / row["sma_50"] - 1
    assert row["distance_from_sma200"] == row["close"] / row["sma_200"] - 1
    assert row["distance_from_52w_high"] == 0
    assert row["distance_from_52w_low"] > 0

    assert row["price_above_sma20"] == 1
    assert row["price_above_sma50"] == 1
    assert row["price_above_sma200"] == 1
    assert row["sma20_above_sma50"] == 1
    assert row["sma50_above_sma200"] == 1


def test_technical_features_do_not_change_when_future_prices_change() -> None:
    prices = synthetic_prices()
    modified = prices.copy()
    modified.loc[280:, "close"] = modified.loc[280:, "close"] * 10
    modified.loc[280:, "high"] = modified.loc[280:, "high"] * 10
    modified.loc[280:, "low"] = modified.loc[280:, "low"] * 10

    original_features = add_technical_features(prices)
    modified_features = add_technical_features(modified)

    feature_columns = [column for column in original_features.columns if column not in {"date", "ticker"}]
    pd.testing.assert_frame_equal(
        original_features.loc[:250, feature_columns],
        modified_features.loc[:250, feature_columns],
    )
