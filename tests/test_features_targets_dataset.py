from __future__ import annotations

import numpy as np
import pandas as pd

from stock_ai.features.dataset import build_feature_dataset, build_training_data, get_feature_columns
from stock_ai.features.targets import DEFAULT_HORIZONS, DirectionThresholds, add_future_targets


def synthetic_prices(rows: int = 340, ticker: str = "AAPL") -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-02", periods=rows)
    close = pd.Series(np.arange(100.0, 100.0 + rows), index=dates)
    return pd.DataFrame(
        {
            "date": dates,
            "ticker": ticker,
            "open": close - 0.25,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "adjusted_close": close,
            "volume": np.arange(2_000_000, 2_000_000 + rows),
        }
    ).reset_index(drop=True)


def test_future_targets_align_for_all_horizons() -> None:
    prices = synthetic_prices()

    targeted = add_future_targets(prices)
    row_index = 10

    for label, sessions in DEFAULT_HORIZONS.items():
        assert targeted.loc[row_index, f"target_close_{label}"] == prices.loc[row_index + sessions, "close"]
        expected_return = prices.loc[row_index + sessions, "close"] / prices.loc[row_index, "close"] - 1
        assert targeted.loc[row_index, f"target_return_{label}"] == expected_return


def test_direction_class_thresholds() -> None:
    prices = pd.DataFrame(
        {
            "date": pd.bdate_range("2024-01-02", periods=8),
            "ticker": "AAPL",
            "open": [100] * 8,
            "high": [100] * 8,
            "low": [100] * 8,
            "close": [100, 104, 100, 96, 100, 100, 100, 100],
            "adjusted_close": [100] * 8,
            "volume": [1_000_000] * 8,
        }
    )

    targeted = add_future_targets(prices, horizons={"1d": 1}, thresholds=DirectionThresholds(up=0.03, down=-0.03))

    assert targeted.loc[0, "target_class_1d"] == "UP"
    assert targeted.loc[1, "target_class_1d"] == "DOWN"
    assert targeted.loc[2, "target_class_1d"] == "DOWN"
    assert targeted.loc[3, "target_class_1d"] == "UP"
    assert targeted.loc[4, "target_class_1d"] == "NEUTRAL"
    assert pd.isna(targeted.loc[7, "target_class_1d"])


def test_dataset_is_chronological_and_missing_targets_are_handled() -> None:
    prices = pd.concat(
        [
            synthetic_prices(rows=340, ticker="MSFT"),
            synthetic_prices(rows=340, ticker="AAPL"),
        ],
        ignore_index=True,
    ).sample(frac=1, random_state=42)

    dataset = build_feature_dataset(prices)

    sorted_copy = dataset.sort_values(["ticker", "date"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(dataset, sorted_copy)
    assert dataset.groupby("ticker")["target_close_63d"].tail(63).isna().all()

    training_ready = build_feature_dataset(prices, training_ready=True, horizon="63d")
    assert training_ready["target_return_63d"].notna().all()
    assert training_ready["target_class_63d"].notna().all()
    assert training_ready["sma_200"].notna().all()
    assert training_ready["distance_from_52w_high"].notna().all()


def test_build_training_data_excludes_target_and_price_columns_from_X() -> None:
    prices = synthetic_prices()

    training = build_training_data(prices, horizon="10d")

    assert not training.X.empty
    assert len(training.X) == len(training.y_classification) == len(training.y_regression) == len(training.dates)
    assert training.dates.is_monotonic_increasing
    assert all(not column.startswith("target_") for column in training.X.columns)
    assert "future_close_10d" not in training.X.columns
    assert "close" not in training.X.columns
    assert "date" not in training.X.columns
    assert "ticker" not in training.X.columns


def test_get_feature_columns_excludes_every_target_column() -> None:
    prices = synthetic_prices()
    dataset = build_feature_dataset(prices)

    feature_columns = get_feature_columns(dataset)

    assert "target_close_5d" not in feature_columns
    assert "target_return_10d" not in feature_columns
    assert "target_class_63d" not in feature_columns
    assert "rsi_14" in feature_columns


def test_target_calculations_only_change_when_forward_window_changes() -> None:
    prices = synthetic_prices()
    modified = prices.copy()
    modified.loc[15, "close"] = 999.0

    original = add_future_targets(prices, horizons={"5d": 5})
    changed = add_future_targets(modified, horizons={"5d": 5})

    assert original.loc[10, "target_close_5d"] != changed.loc[10, "target_close_5d"]
    assert original.loc[9, "target_close_5d"] == changed.loc[9, "target_close_5d"]
