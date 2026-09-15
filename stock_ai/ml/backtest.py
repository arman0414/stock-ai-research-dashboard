from __future__ import annotations

import numpy as np
import pandas as pd

from stock_ai.ml.confidence import confidence_label


def build_prediction_backtest(
    test_dataset: pd.DataFrame,
    horizon: str,
    predicted_class: np.ndarray,
    predicted_probabilities: np.ndarray,
    predicted_return: np.ndarray,
) -> pd.DataFrame:
    max_probabilities = predicted_probabilities.max(axis=1)
    actual_return = pd.to_numeric(test_dataset[f"target_return_{horizon}"], errors="coerce").to_numpy(dtype=float)
    current_price = pd.to_numeric(test_dataset["close"], errors="coerce").to_numpy(dtype=float)
    predicted_return = np.asarray(predicted_return, dtype=float)

    return pd.DataFrame(
        {
            "ticker": test_dataset["ticker"].to_numpy(),
            "prediction_date": pd.to_datetime(test_dataset["date"]).to_numpy(),
            "horizon": horizon,
            "current_price": current_price,
            "predicted_class": predicted_class,
            "actual_class": test_dataset[f"target_class_{horizon}"].to_numpy(),
            "predicted_probability": max_probabilities,
            "confidence": [confidence_label(probability) for probability in max_probabilities],
            "predicted_return": predicted_return,
            "actual_return": actual_return,
            "predicted_target_price": current_price * (1 + predicted_return),
            "actual_future_price": pd.to_numeric(test_dataset[f"target_close_{horizon}"], errors="coerce").to_numpy(dtype=float),
            "classification_correct": predicted_class == test_dataset[f"target_class_{horizon}"].to_numpy(),
            "regression_error": predicted_return - actual_return,
        }
    ).sort_values(["ticker", "prediction_date"]).reset_index(drop=True)


def evaluate_signal_strategy(
    backtest: pd.DataFrame,
    probability_threshold: float = 0.60,
    non_overlapping: bool = False,
    horizon_sessions: int = 1,
) -> dict[str, float | int]:
    signals = backtest[backtest["predicted_probability"] >= probability_threshold].copy()
    if non_overlapping:
        signals = _non_overlapping_signals(signals, horizon_sessions=horizon_sessions)

    up_signals = signals[signals["predicted_class"] == "UP"]
    down_signals = signals[signals["predicted_class"] == "DOWN"]
    return {
        "number_of_signals": int(len(signals)),
        "up_signals": int(len(up_signals)),
        "down_signals": int(len(down_signals)),
        "average_return_after_up_signals": _safe_mean(up_signals["actual_return"]),
        "median_return_after_up_signals": _safe_median(up_signals["actual_return"]),
        "positive_outcome_rate_after_up_signals": _safe_rate(up_signals["actual_return"] > 0),
        "average_return_after_down_signals": _safe_mean(down_signals["actual_return"]),
        "median_return_after_down_signals": _safe_median(down_signals["actual_return"]),
        "negative_outcome_rate_after_down_signals": _safe_rate(down_signals["actual_return"] < 0),
        "signal_hit_rate": _safe_rate(
            ((signals["predicted_class"] == "UP") & (signals["actual_return"] > 0))
            | ((signals["predicted_class"] == "DOWN") & (signals["actual_return"] < 0))
        ),
        "non_overlapping": bool(non_overlapping),
    }


def _non_overlapping_signals(signals: pd.DataFrame, horizon_sessions: int) -> pd.DataFrame:
    kept_frames = []
    for _, group in signals.sort_values(["ticker", "prediction_date"]).groupby("ticker", sort=False):
        kept_indices: list[int] = []
        last_kept_position = -horizon_sessions - 1
        for position, index in enumerate(group.index):
            if position - last_kept_position >= horizon_sessions:
                kept_indices.append(index)
                last_kept_position = position
        kept_frames.append(group.loc[kept_indices])

    if not kept_frames:
        return signals.iloc[0:0]
    return pd.concat(kept_frames).sort_values(["ticker", "prediction_date"]).reset_index(drop=True)


def _safe_mean(values: pd.Series) -> float:
    return float(values.mean()) if len(values) else float("nan")


def _safe_median(values: pd.Series) -> float:
    return float(values.median()) if len(values) else float("nan")


def _safe_rate(mask: pd.Series) -> float:
    return float(mask.mean()) if len(mask) else float("nan")

