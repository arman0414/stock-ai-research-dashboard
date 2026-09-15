from __future__ import annotations

import numpy as np
import pandas as pd


RETURN_WINDOWS = (1, 5, 10, 20, 50)
SMA_WINDOWS = (5, 10, 20, 50, 100, 200)
VOLATILITY_WINDOWS = (5, 20, 50)
VOLUME_SMA_WINDOWS = (5, 20)

TECHNICAL_FEATURE_COLUMNS = [
    "return_1d",
    "return_5d",
    "return_10d",
    "return_20d",
    "return_50d",
    "sma_5",
    "sma_10",
    "sma_20",
    "sma_50",
    "sma_100",
    "sma_200",
    "ema_12",
    "ema_26",
    "rsi_14",
    "macd",
    "macd_signal",
    "macd_histogram",
    "volatility_5d",
    "volatility_20d",
    "volatility_50d",
    "volume_sma_5",
    "volume_sma_20",
    "relative_volume",
    "distance_from_sma20",
    "distance_from_sma50",
    "distance_from_sma200",
    "distance_from_52w_high",
    "distance_from_52w_low",
    "price_above_sma20",
    "price_above_sma50",
    "price_above_sma200",
    "sma20_above_sma50",
    "sma50_above_sma200",
    "atr_14",
    "bollinger_upper",
    "bollinger_lower",
    "bollinger_width",
]


REQUIRED_PRICE_COLUMNS = {"ticker", "date", "open", "high", "low", "close", "volume"}


def add_technical_features(price_data: pd.DataFrame) -> pd.DataFrame:
    """Add backward-looking technical features to OHLCV rows.

    The output is sorted by ticker/date. All rolling calculations use current
    and previous rows only; this function never backfills missing values.
    """
    missing = REQUIRED_PRICE_COLUMNS - set(price_data.columns)
    if missing:
        raise ValueError(f"Missing required price columns: {sorted(missing)}")

    frames = []
    normalized = price_data.copy()
    normalized["date"] = pd.to_datetime(normalized["date"])
    numeric_columns = ["open", "high", "low", "close", "volume"]
    for column in numeric_columns:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

    normalized = normalized.sort_values(["ticker", "date"]).reset_index(drop=True)
    for _, group in normalized.groupby("ticker", sort=False):
        frames.append(_add_features_for_ticker(group.copy()))

    return pd.concat(frames, ignore_index=True).sort_values(["ticker", "date"]).reset_index(drop=True)


def _add_features_for_ticker(df: pd.DataFrame) -> pd.DataFrame:
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]
    previous_close = close.shift(1)

    for window in RETURN_WINDOWS:
        df[f"return_{window}d"] = close.pct_change(periods=window)

    for window in SMA_WINDOWS:
        df[f"sma_{window}"] = close.rolling(window=window, min_periods=window).mean()

    df["ema_12"] = close.ewm(span=12, adjust=False, min_periods=12).mean()
    df["ema_26"] = close.ewm(span=26, adjust=False, min_periods=26).mean()

    delta = close.diff()
    average_gain = delta.clip(lower=0).rolling(window=14, min_periods=14).mean()
    average_loss = (-delta.clip(upper=0)).rolling(window=14, min_periods=14).mean()
    relative_strength = average_gain / average_loss.replace(0, np.nan)
    df["rsi_14"] = 100 - (100 / (1 + relative_strength))
    df.loc[(average_loss == 0) & average_gain.notna(), "rsi_14"] = 100

    df["macd"] = df["ema_12"] - df["ema_26"]
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False, min_periods=9).mean()
    df["macd_histogram"] = df["macd"] - df["macd_signal"]

    daily_return = close.pct_change()
    for window in VOLATILITY_WINDOWS:
        df[f"volatility_{window}d"] = daily_return.rolling(window=window, min_periods=window).std()

    for window in VOLUME_SMA_WINDOWS:
        df[f"volume_sma_{window}"] = volume.rolling(window=window, min_periods=window).mean()
    df["relative_volume"] = volume / df["volume_sma_20"]

    df["distance_from_sma20"] = close / df["sma_20"] - 1
    df["distance_from_sma50"] = close / df["sma_50"] - 1
    df["distance_from_sma200"] = close / df["sma_200"] - 1

    rolling_high_52w = close.rolling(window=252, min_periods=252).max()
    rolling_low_52w = close.rolling(window=252, min_periods=252).min()
    df["distance_from_52w_high"] = close / rolling_high_52w - 1
    df["distance_from_52w_low"] = close / rolling_low_52w - 1

    df["price_above_sma20"] = _boolean_feature(close > df["sma_20"], df["sma_20"].notna())
    df["price_above_sma50"] = _boolean_feature(close > df["sma_50"], df["sma_50"].notna())
    df["price_above_sma200"] = _boolean_feature(close > df["sma_200"], df["sma_200"].notna())
    df["sma20_above_sma50"] = _boolean_feature(df["sma_20"] > df["sma_50"], df["sma_20"].notna() & df["sma_50"].notna())
    df["sma50_above_sma200"] = _boolean_feature(
        df["sma_50"] > df["sma_200"],
        df["sma_50"].notna() & df["sma_200"].notna(),
    )

    true_range = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df["atr_14"] = true_range.rolling(window=14, min_periods=14).mean()

    bollinger_std = close.rolling(window=20, min_periods=20).std()
    df["bollinger_upper"] = df["sma_20"] + (2 * bollinger_std)
    df["bollinger_lower"] = df["sma_20"] - (2 * bollinger_std)
    df["bollinger_width"] = (df["bollinger_upper"] - df["bollinger_lower"]) / df["sma_20"]

    return df


def _boolean_feature(condition: pd.Series, valid: pd.Series) -> pd.Series:
    return pd.Series(np.where(valid, condition.astype(int), np.nan), index=condition.index)

