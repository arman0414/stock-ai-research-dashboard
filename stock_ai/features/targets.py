from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


DEFAULT_HORIZONS = {
    "5d": 5,
    "10d": 10,
    "15d": 15,
    "21d": 21,
    "63d": 63,
}


@dataclass(frozen=True)
class DirectionThresholds:
    up: float = 0.03
    down: float = -0.03

    def __post_init__(self) -> None:
        if self.down >= self.up:
            raise ValueError("Down threshold must be lower than up threshold")


def add_future_targets(
    feature_data: pd.DataFrame,
    horizons: dict[str, int] | None = None,
    thresholds: DirectionThresholds | None = None,
) -> pd.DataFrame:
    """Add forward-looking supervised targets without changing feature values."""
    horizons = horizons or DEFAULT_HORIZONS
    thresholds = thresholds or DirectionThresholds()

    required = {"ticker", "date", "close"}
    missing = required - set(feature_data.columns)
    if missing:
        raise ValueError(f"Missing required target columns: {sorted(missing)}")

    frames = []
    sorted_data = feature_data.copy()
    sorted_data["date"] = pd.to_datetime(sorted_data["date"])
    sorted_data = sorted_data.sort_values(["ticker", "date"]).reset_index(drop=True)

    for _, group in sorted_data.groupby("ticker", sort=False):
        frames.append(_add_targets_for_ticker(group.copy(), horizons, thresholds))

    return pd.concat(frames, ignore_index=True).sort_values(["ticker", "date"]).reset_index(drop=True)


def target_columns(horizons: dict[str, int] | None = None) -> list[str]:
    horizons = horizons or DEFAULT_HORIZONS
    columns: list[str] = []
    for label in horizons:
        columns.extend(
            [
                f"target_close_{label}",
                f"target_return_{label}",
                f"target_class_{label}",
            ]
        )
    return columns


def _add_targets_for_ticker(df: pd.DataFrame, horizons: dict[str, int], thresholds: DirectionThresholds) -> pd.DataFrame:
    close = pd.to_numeric(df["close"], errors="coerce")

    for label, sessions in horizons.items():
        future_close = close.shift(-sessions)
        future_return = future_close / close - 1
        df[f"target_close_{label}"] = future_close
        df[f"target_return_{label}"] = future_return
        df[f"target_class_{label}"] = _direction_class(future_return, thresholds)

    return df


def _direction_class(future_return: pd.Series, thresholds: DirectionThresholds) -> pd.Series:
    classes = np.select(
        [
            future_return > thresholds.up,
            future_return < thresholds.down,
            future_return.notna(),
        ],
        ["UP", "DOWN", "NEUTRAL"],
        default=pd.NA,
    )
    return pd.Series(classes, index=future_return.index, dtype="string")

