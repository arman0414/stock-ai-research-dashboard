from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from pandas.errors import PerformanceWarning


PRESSURE_WINDOWS = (3, 5, 10, 20)
STRUCTURE_WINDOWS = (5, 10, 20)

PRICE_ACTION_FEATURE_COLUMNS = [
    "candle_body",
    "candle_range",
    "upper_wick",
    "lower_wick",
    "body_to_range_ratio",
    "upper_wick_ratio",
    "lower_wick_ratio",
    "close_location",
    "gap_from_previous_close",
    "bullish_rejection_strength",
    "bearish_rejection_strength",
    "lower_wick_strength",
    "upper_wick_strength",
    "price_up_volume_increasing",
    "price_up_volume_decreasing",
    "price_down_volume_increasing",
    "price_down_volume_decreasing",
    "obv",
    "obv_change_5d",
    "obv_change_20d",
    "obv_slope_5d",
    "obv_slope_20d",
    "adl",
    "adl_change_5d",
    "adl_change_20d",
    "adl_slope",
    "cmf_20",
    "mfi_14",
    "adx_14",
    "plus_di_14",
    "minus_di_14",
    "trend_structure_score",
    "nearest_support",
    "nearest_resistance",
    "distance_to_support_pct",
    "distance_to_resistance_pct",
    "support_touch_count",
    "resistance_touch_count",
    "support_strength",
    "resistance_strength",
    "support_rejection_strength",
    "support_volume_confirmation",
    "buyers_defending_support",
    "resistance_rejection_strength",
    "resistance_volume_confirmation",
    "sellers_defending_resistance",
    "breakout_20d",
    "breakout_50d",
    "breakout_strength",
    "breakout_volume_ratio",
    "distance_above_breakout_pct",
    "failed_breakout",
    "failed_breakout_strength",
    "upper_rejection_at_resistance",
    "breakdown",
    "breakdown_strength",
    "breakdown_volume_ratio",
    "distance_below_support_pct",
    "atr_ratio_5d_20d",
    "range_compression_10d",
    "bb_width_change",
    "volume_compression_10d",
    "consolidation_score",
    "price_obv_divergence",
    "price_cmf_divergence",
    "buyer_pressure_score",
    "seller_pressure_score",
]

for window in PRESSURE_WINDOWS:
    PRICE_ACTION_FEATURE_COLUMNS.extend(
        [
            f"bullish_candle_ratio_{window}d",
            f"bearish_candle_ratio_{window}d",
            f"average_close_location_{window}d",
            f"average_body_strength_{window}d",
            f"average_lower_wick_strength_{window}d",
            f"average_upper_wick_strength_{window}d",
            f"up_volume_{window}d",
            f"down_volume_{window}d",
            f"up_down_volume_ratio_{window}d",
            f"buyer_pressure_{window}d",
            f"seller_pressure_{window}d",
        ]
    )

for window in STRUCTURE_WINDOWS:
    PRICE_ACTION_FEATURE_COLUMNS.extend(
        [
            f"higher_high_ratio_{window}d",
            f"higher_low_ratio_{window}d",
            f"lower_high_ratio_{window}d",
            f"lower_low_ratio_{window}d",
        ]
    )


def add_price_action_features(feature_data: pd.DataFrame) -> pd.DataFrame:
    required = {"ticker", "date", "open", "high", "low", "close", "volume"}
    missing = required - set(feature_data.columns)
    if missing:
        raise ValueError(f"Missing required price-action columns: {sorted(missing)}")

    frames = []
    data = feature_data.copy()
    data["date"] = pd.to_datetime(data["date"])
    for column in ["open", "high", "low", "close", "volume"]:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data = data.sort_values(["ticker", "date"]).reset_index(drop=True)

    for _, group in data.groupby("ticker", sort=False):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", PerformanceWarning)
            frames.append(_add_price_action_for_ticker(group.copy()).copy())

    return pd.concat(frames, ignore_index=True).sort_values(["ticker", "date"]).reset_index(drop=True)


def summarize_latest_structure(dataset: pd.DataFrame) -> dict | None:
    if dataset.empty:
        return None
    ready = dataset.dropna(subset=["buyer_pressure_score", "seller_pressure_score", "nearest_support", "nearest_resistance"], how="any")
    if ready.empty:
        return None
    row = ready.iloc[-1]
    market_structure = "BULLISH" if row["trend_structure_score"] > 0.15 else "BEARISH" if row["trend_structure_score"] < -0.15 else "NEUTRAL"
    breakout_status = _breakout_status(row)
    observations = _observations(row)
    return {
        "ticker": row["ticker"],
        "date": row["date"].date().isoformat() if hasattr(row["date"], "date") else str(row["date"]),
        "current_price": float(row["close"]),
        "market_structure": market_structure,
        "buyer_pressure": _strength_label(row["buyer_pressure_score"]),
        "seller_pressure": _strength_label(row["seller_pressure_score"]),
        "nearest_support": _maybe_float(row["nearest_support"]),
        "nearest_resistance": _maybe_float(row["nearest_resistance"]),
        "distance_to_support": _maybe_float(row["distance_to_support_pct"]),
        "distance_to_resistance": _maybe_float(row["distance_to_resistance_pct"]),
        "support_strength": _strength_label(row["support_strength"]),
        "resistance_strength": _strength_label(row["resistance_strength"]),
        "breakout_status": breakout_status,
        "important_observations": observations,
    }


def _add_price_action_for_ticker(df: pd.DataFrame) -> pd.DataFrame:
    open_ = df["open"]
    high = df["high"]
    low = df["low"]
    close = df["close"]
    volume = df["volume"]
    previous_close = close.shift(1)
    candle_range = high - low

    df["candle_body"] = (close - open_).abs()
    df["candle_range"] = candle_range
    df["upper_wick"] = high - pd.concat([open_, close], axis=1).max(axis=1)
    df["lower_wick"] = pd.concat([open_, close], axis=1).min(axis=1) - low
    df["body_to_range_ratio"] = _safe_divide(df["candle_body"], candle_range)
    df["upper_wick_ratio"] = _safe_divide(df["upper_wick"], candle_range)
    df["lower_wick_ratio"] = _safe_divide(df["lower_wick"], candle_range)
    df["close_location"] = _safe_divide(close - low, candle_range)
    df["gap_from_previous_close"] = _safe_divide(open_ - previous_close, previous_close)

    relative_volume = df.get("relative_volume", volume / volume.rolling(20, min_periods=20).mean())
    relative_volume_clipped = relative_volume.clip(lower=0, upper=3).fillna(1)
    df["lower_wick_strength"] = df["lower_wick_ratio"] * df["close_location"] * relative_volume_clipped
    df["upper_wick_strength"] = df["upper_wick_ratio"] * (1 - df["close_location"]) * relative_volume_clipped
    df["bullish_rejection_strength"] = df["lower_wick_strength"]
    df["bearish_rejection_strength"] = df["upper_wick_strength"]

    is_up = close > previous_close
    is_down = close < previous_close
    volume_increasing = volume > volume.shift(1)
    df["price_up_volume_increasing"] = (is_up & volume_increasing).astype(int)
    df["price_up_volume_decreasing"] = (is_up & ~volume_increasing).astype(int)
    df["price_down_volume_increasing"] = (is_down & volume_increasing).astype(int)
    df["price_down_volume_decreasing"] = (is_down & ~volume_increasing).astype(int)

    df["obv"] = (np.sign(close.diff()).fillna(0) * volume).cumsum()
    df["obv_change_5d"] = df["obv"].diff(5)
    df["obv_change_20d"] = df["obv"].diff(20)
    df["obv_slope_5d"] = df["obv_change_5d"] / 5
    df["obv_slope_20d"] = df["obv_change_20d"] / 20

    money_flow_multiplier = _safe_divide((close - low) - (high - close), candle_range)
    money_flow_volume = money_flow_multiplier * volume
    df["adl"] = money_flow_volume.fillna(0).cumsum()
    df["adl_change_5d"] = df["adl"].diff(5)
    df["adl_change_20d"] = df["adl"].diff(20)
    df["adl_slope"] = df["adl_change_20d"] / 20
    df["cmf_20"] = _safe_divide(money_flow_volume.rolling(20, min_periods=20).sum(), volume.rolling(20, min_periods=20).sum())

    typical_price = (high + low + close) / 3
    raw_money_flow = typical_price * volume
    positive_flow = raw_money_flow.where(typical_price > typical_price.shift(1), 0)
    negative_flow = raw_money_flow.where(typical_price < typical_price.shift(1), 0)
    money_ratio = _safe_divide(positive_flow.rolling(14, min_periods=14).sum(), negative_flow.rolling(14, min_periods=14).sum())
    df["mfi_14"] = 100 - (100 / (1 + money_ratio))

    _add_adx(df)
    _add_pressure_windows(df, is_up, is_down)
    _add_structure(df)
    _add_support_resistance(df)
    _add_breakouts(df, relative_volume)
    _add_compression_and_divergence(df)
    _add_composites(df)
    return df


def _add_pressure_windows(df: pd.DataFrame, is_up: pd.Series, is_down: pd.Series) -> None:
    volume = df["volume"]
    for window in PRESSURE_WINDOWS:
        df[f"bullish_candle_ratio_{window}d"] = (df["close"] > df["open"]).rolling(window, min_periods=window).mean()
        df[f"bearish_candle_ratio_{window}d"] = (df["close"] < df["open"]).rolling(window, min_periods=window).mean()
        df[f"average_close_location_{window}d"] = df["close_location"].rolling(window, min_periods=window).mean()
        df[f"average_body_strength_{window}d"] = df["body_to_range_ratio"].rolling(window, min_periods=window).mean()
        df[f"average_lower_wick_strength_{window}d"] = df["lower_wick_strength"].rolling(window, min_periods=window).mean()
        df[f"average_upper_wick_strength_{window}d"] = df["upper_wick_strength"].rolling(window, min_periods=window).mean()
        df[f"up_volume_{window}d"] = volume.where(is_up, 0).rolling(window, min_periods=window).sum()
        df[f"down_volume_{window}d"] = volume.where(is_down, 0).rolling(window, min_periods=window).sum()
        df[f"up_down_volume_ratio_{window}d"] = _safe_divide(df[f"up_volume_{window}d"], df[f"down_volume_{window}d"])
        df[f"buyer_pressure_{window}d"] = (
            df[f"average_close_location_{window}d"] * 0.35
            + df[f"average_lower_wick_strength_{window}d"] * 0.35
            + _bounded_ratio(df[f"up_down_volume_ratio_{window}d"]) * 0.30
        )
        df[f"seller_pressure_{window}d"] = (
            (1 - df[f"average_close_location_{window}d"]) * 0.35
            + df[f"average_upper_wick_strength_{window}d"] * 0.35
            + (1 - _bounded_ratio(df[f"up_down_volume_ratio_{window}d"])) * 0.30
        )


def _add_adx(df: pd.DataFrame) -> None:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    previous_close = close.shift(1)
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0), index=df.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0), index=df.index)
    true_range = pd.concat([(high - low), (high - previous_close).abs(), (low - previous_close).abs()], axis=1).max(axis=1)
    atr = true_range.rolling(14, min_periods=14).mean()
    df["plus_di_14"] = 100 * _safe_divide(plus_dm.rolling(14, min_periods=14).sum(), atr)
    df["minus_di_14"] = 100 * _safe_divide(minus_dm.rolling(14, min_periods=14).sum(), atr)
    dx = 100 * _safe_divide((df["plus_di_14"] - df["minus_di_14"]).abs(), df["plus_di_14"] + df["minus_di_14"])
    df["adx_14"] = dx.rolling(14, min_periods=14).mean()


def _add_structure(df: pd.DataFrame) -> None:
    higher_high = df["high"] > df["high"].shift(1)
    higher_low = df["low"] > df["low"].shift(1)
    lower_high = df["high"] < df["high"].shift(1)
    lower_low = df["low"] < df["low"].shift(1)
    for window in STRUCTURE_WINDOWS:
        df[f"higher_high_ratio_{window}d"] = higher_high.rolling(window, min_periods=window).mean()
        df[f"higher_low_ratio_{window}d"] = higher_low.rolling(window, min_periods=window).mean()
        df[f"lower_high_ratio_{window}d"] = lower_high.rolling(window, min_periods=window).mean()
        df[f"lower_low_ratio_{window}d"] = lower_low.rolling(window, min_periods=window).mean()
    df["trend_structure_score"] = (
        df["higher_high_ratio_10d"]
        + df["higher_low_ratio_10d"]
        - df["lower_high_ratio_10d"]
        - df["lower_low_ratio_10d"]
    ) / 2


def _add_support_resistance(df: pd.DataFrame) -> None:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    atr = df.get("atr_14", (high - low).rolling(14, min_periods=14).mean())
    prior_support = low.shift(1).rolling(20, min_periods=5).min()
    prior_resistance = high.shift(1).rolling(20, min_periods=5).max()
    tolerance = (atr * 0.5).fillna(close * 0.01)
    df["nearest_support"] = prior_support
    df["nearest_resistance"] = prior_resistance
    df["distance_to_support_pct"] = _safe_divide(close - prior_support, close)
    df["distance_to_resistance_pct"] = _safe_divide(prior_resistance - close, close)
    df["support_touch_count"] = [
        _touch_count(low.iloc[: index], prior_support.iloc[index], tolerance.iloc[index])
        for index in range(len(df))
    ]
    df["resistance_touch_count"] = [
        _touch_count(high.iloc[: index], prior_resistance.iloc[index], tolerance.iloc[index])
        for index in range(len(df))
    ]
    df["support_strength"] = _bounded_ratio(df["support_touch_count"] / 3)
    df["resistance_strength"] = _bounded_ratio(df["resistance_touch_count"] / 3)
    near_support = (low <= prior_support + tolerance) & prior_support.notna()
    near_resistance = (high >= prior_resistance - tolerance) & prior_resistance.notna()
    rel_vol = df.get("relative_volume", df["volume"] / df["volume"].rolling(20, min_periods=20).mean()).fillna(1)
    df["support_rejection_strength"] = np.where(near_support, df["lower_wick_strength"] * df["close_location"], 0)
    df["support_volume_confirmation"] = np.where(near_support, rel_vol, 0)
    df["buyers_defending_support"] = df["support_rejection_strength"] * _bounded_ratio(df["support_volume_confirmation"])
    df["resistance_rejection_strength"] = np.where(near_resistance, df["upper_wick_strength"] * (1 - df["close_location"]), 0)
    df["resistance_volume_confirmation"] = np.where(near_resistance, rel_vol, 0)
    df["sellers_defending_resistance"] = df["resistance_rejection_strength"] * _bounded_ratio(df["resistance_volume_confirmation"])


def _add_breakouts(df: pd.DataFrame, relative_volume: pd.Series) -> None:
    close = df["close"]
    high = df["high"]
    low = df["low"]
    prior_resistance_20 = high.shift(1).rolling(20, min_periods=20).max()
    prior_resistance_50 = high.shift(1).rolling(50, min_periods=50).max()
    prior_support_20 = low.shift(1).rolling(20, min_periods=20).min()
    df["breakout_20d"] = (close > prior_resistance_20).astype(int)
    df["breakout_50d"] = (close > prior_resistance_50).astype(int)
    df["breakout_strength"] = np.where(df["breakout_20d"] == 1, _safe_divide(close - prior_resistance_20, prior_resistance_20), 0)
    df["breakout_volume_ratio"] = np.where(df["breakout_20d"] == 1, relative_volume, 0)
    df["distance_above_breakout_pct"] = np.where(df["breakout_20d"] == 1, _safe_divide(close - prior_resistance_20, close), 0)
    df["failed_breakout"] = ((high > prior_resistance_20) & (close <= prior_resistance_20)).astype(int)
    df["failed_breakout_strength"] = np.where(df["failed_breakout"] == 1, _safe_divide(high - close, high - df["low"]), 0)
    df["upper_rejection_at_resistance"] = df["failed_breakout"] * df["upper_wick_strength"]
    df["breakdown"] = (close < prior_support_20).astype(int)
    df["breakdown_strength"] = np.where(df["breakdown"] == 1, _safe_divide(prior_support_20 - close, prior_support_20), 0)
    df["breakdown_volume_ratio"] = np.where(df["breakdown"] == 1, relative_volume, 0)
    df["distance_below_support_pct"] = np.where(df["breakdown"] == 1, _safe_divide(prior_support_20 - close, close), 0)


def _add_compression_and_divergence(df: pd.DataFrame) -> None:
    range_10 = (df["high"].rolling(10, min_periods=10).max() - df["low"].rolling(10, min_periods=10).min()) / df["close"]
    range_50 = (df["high"].rolling(50, min_periods=50).max() - df["low"].rolling(50, min_periods=50).min()) / df["close"]
    atr_5 = df["candle_range"].rolling(5, min_periods=5).mean()
    atr_20 = df["candle_range"].rolling(20, min_periods=20).mean()
    bb_width = df.get("bollinger_width", range_10)
    df["atr_ratio_5d_20d"] = _safe_divide(atr_5, atr_20)
    df["range_compression_10d"] = 1 - _bounded_ratio(_safe_divide(range_10, range_50))
    df["bb_width_change"] = bb_width.pct_change(10, fill_method=None)
    df["volume_compression_10d"] = 1 - _bounded_ratio(_safe_divide(df["volume"].rolling(10, min_periods=10).mean(), df["volume"].rolling(50, min_periods=50).mean()))
    df["consolidation_score"] = (df["range_compression_10d"].fillna(0) + df["volume_compression_10d"].fillna(0) + (1 - _bounded_ratio(df["atr_ratio_5d_20d"])).fillna(0)) / 3
    price_slope_20 = df["close"].diff(20)
    df["price_obv_divergence"] = np.where((price_slope_20 > 0) & (df["obv_change_20d"] < 0), -1, np.where((price_slope_20 < 0) & (df["obv_change_20d"] > 0), 1, 0))
    cmf_change_20 = df["cmf_20"].diff(20)
    df["price_cmf_divergence"] = np.where((price_slope_20 > 0) & (cmf_change_20 < 0), -1, np.where((price_slope_20 < 0) & (cmf_change_20 > 0), 1, 0))


def _add_composites(df: pd.DataFrame) -> None:
    cmf_component = ((df["cmf_20"] + 1) / 2).clip(0, 1)
    mfi_component = (df["mfi_14"] / 100).clip(0, 1)
    obv_component = (df["obv_slope_20d"] > 0).astype(float)
    adl_component = (df["adl_slope"] > 0).astype(float)
    df["buyer_pressure_score"] = (
        df["buyer_pressure_10d"].fillna(0) * 0.30
        + cmf_component.fillna(0.5) * 0.20
        + mfi_component.fillna(0.5) * 0.15
        + obv_component * 0.10
        + adl_component * 0.10
        + df["buyers_defending_support"].fillna(0).clip(0, 1) * 0.15
    )
    df["seller_pressure_score"] = (
        df["seller_pressure_10d"].fillna(0) * 0.30
        + (1 - cmf_component.fillna(0.5)) * 0.20
        + (1 - mfi_component.fillna(0.5)) * 0.15
        + (df["obv_slope_20d"] < 0).astype(float) * 0.10
        + (df["adl_slope"] < 0).astype(float) * 0.10
        + df["sellers_defending_resistance"].fillna(0).clip(0, 1) * 0.15
    )


def _touch_count(series: pd.Series, level: float, tolerance: float) -> int:
    if pd.isna(level) or pd.isna(tolerance):
        return 0
    recent = series.tail(20)
    return int(((recent - level).abs() <= tolerance).sum())


def _safe_divide(numerator: pd.Series | float, denominator: pd.Series | float) -> pd.Series:
    result = numerator / denominator
    return result.replace([np.inf, -np.inf], np.nan).fillna(0)


def _bounded_ratio(value: pd.Series) -> pd.Series:
    return (value / (1 + value.abs())).clip(0, 1)


def _strength_label(value: float) -> str:
    if pd.isna(value):
        return "UNKNOWN"
    if value >= 0.70:
        return "STRONG"
    if value >= 0.40:
        return "MODERATE"
    return "WEAK"


def _breakout_status(row: pd.Series) -> str:
    if row.get("breakout_20d", 0) == 1:
        return "BREAKOUT"
    if row.get("failed_breakout", 0) == 1:
        return "FAILED_BREAKOUT"
    if row.get("breakdown", 0) == 1:
        return "BREAKDOWN"
    if pd.notna(row.get("distance_to_resistance_pct")) and row["distance_to_resistance_pct"] < 0.03:
        return "APPROACHING_RESISTANCE"
    if pd.notna(row.get("distance_to_support_pct")) and row["distance_to_support_pct"] < 0.03:
        return "NEAR_SUPPORT"
    return "RANGE_BOUND"


def _observations(row: pd.Series) -> list[str]:
    observations = []
    if row.get("buyers_defending_support", 0) > 0.25:
        observations.append("Price/volume behavior suggests buyers recently defended the support area.")
    if row.get("sellers_defending_resistance", 0) > 0.25:
        observations.append("Price/volume behavior suggests sellers recently rejected the resistance area.")
    if row.get("up_down_volume_ratio_5d", 0) > 1.5:
        observations.append("Up-day volume is above down-day volume over the recent window.")
    if row.get("trend_structure_score", 0) > 0.15:
        observations.append("Price is making more higher highs and higher lows than lower structures.")
    if row.get("consolidation_score", 0) > 0.6:
        observations.append("Price appears compressed relative to recent range and volume.")
    return observations


def _maybe_float(value: float) -> float | None:
    return None if pd.isna(value) else float(value)
