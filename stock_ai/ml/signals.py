from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, balanced_accuracy_score, precision_score


SIGNAL_THRESHOLDS = (0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80)


@dataclass(frozen=True)
class SignalPolicy:
    threshold: float
    min_samples: int = 30


def confidence_label(probability: float) -> str:
    if probability >= 0.80:
        return "VERY_HIGH"
    if probability >= 0.70:
        return "HIGH"
    if probability >= 0.60:
        return "MEDIUM"
    if probability >= 0.50:
        return "LOW"
    return "NO_STRONG_SIGNAL"


def signal_from_prediction(predicted_direction: str, probability: float, threshold: float) -> tuple[str, str]:
    if probability < threshold:
        return "NO_STRONG_SIGNAL", "NO_STRONG_SIGNAL"
    if predicted_direction == "UP":
        return "BULLISH", confidence_label(probability)
    if predicted_direction == "DOWN":
        return "BEARISH", confidence_label(probability)
    return "NO_STRONG_SIGNAL", confidence_label(probability)


def threshold_table(backtest: pd.DataFrame, thresholds: tuple[float, ...] = SIGNAL_THRESHOLDS) -> dict[str, dict]:
    rows = {}
    total = len(backtest)
    for threshold in thresholds:
        subset = backtest[backtest["predicted_probability"] >= threshold].copy()
        key = f"{threshold:.2f}"
        if subset.empty:
            rows[key] = _empty_threshold_row(total)
            continue
        rows[key] = {
            "sample_count": int(len(subset)),
            "coverage": float(len(subset) / total) if total else 0.0,
            "accuracy": float(accuracy_score(subset["actual_class"], subset["predicted_class"])),
            "balanced_accuracy": _safe_balanced_accuracy(subset),
            "up_precision": _precision(subset, "UP"),
            "down_precision": _precision(subset, "DOWN"),
            "average_actual_return_after_bullish": _mean_return(subset, "UP"),
            "average_actual_return_after_bearish": _mean_return(subset, "DOWN"),
        }
    return rows


def select_signal_threshold(
    validation_backtest: pd.DataFrame,
    thresholds: tuple[float, ...] = SIGNAL_THRESHOLDS,
    min_samples: int = 30,
) -> dict:
    table = threshold_table(validation_backtest, thresholds=thresholds)
    candidates = [
        (float(threshold), metrics)
        for threshold, metrics in table.items()
        if metrics["sample_count"] >= min_samples and metrics["accuracy"] == metrics["accuracy"]
    ]
    if not candidates:
        return {"threshold": 1.0, "reason": "no_threshold_met_min_samples", "table": table}
    selected_threshold, metrics = max(candidates, key=lambda item: (item[1]["accuracy"], item[1]["sample_count"]))
    return {"threshold": selected_threshold, "reason": "max_validation_accuracy_with_min_samples", "metrics": metrics, "table": table}


def make_signal_object(
    ticker: str,
    horizon: str,
    current_price: float,
    predicted_direction: str,
    probability: float,
    predicted_return: float,
    policy: SignalPolicy,
    historical_signal_accuracy: float | None,
    historical_signal_samples: int,
    model_version: str,
    typical_abs_error: float | None = None,
) -> dict:
    signal, confidence = signal_from_prediction(predicted_direction, probability, policy.threshold)
    target_price = current_price * (1 + predicted_return)
    return {
        "ticker": ticker,
        "horizon": horizon,
        "current_price": float(current_price),
        "predicted_direction": predicted_direction,
        "signal": signal,
        "probability": float(probability),
        "confidence": confidence,
        "predicted_return": float(predicted_return),
        "model_target_price": float(target_price),
        "typical_abs_error": None if typical_abs_error is None else float(typical_abs_error),
        "historical_signal_accuracy": historical_signal_accuracy,
        "historical_signal_samples": int(historical_signal_samples),
        "signal_status": "STRONG_SIGNAL" if signal in {"BULLISH", "BEARISH"} else "NO_STRONG_SIGNAL",
        "model_version": model_version,
    }


def residual_uncertainty(validation_actual: pd.Series | np.ndarray, validation_predicted: pd.Series | np.ndarray) -> dict:
    residuals = np.asarray(validation_predicted, dtype=float) - np.asarray(validation_actual, dtype=float)
    abs_residuals = np.abs(residuals[~np.isnan(residuals)])
    if len(abs_residuals) == 0:
        return {"median_abs_error": None, "p80_abs_error": None, "p90_abs_error": None}
    return {
        "median_abs_error": float(np.quantile(abs_residuals, 0.50)),
        "p80_abs_error": float(np.quantile(abs_residuals, 0.80)),
        "p90_abs_error": float(np.quantile(abs_residuals, 0.90)),
    }


def _empty_threshold_row(total: int) -> dict:
    return {
        "sample_count": 0,
        "coverage": 0.0 if total else 0.0,
        "accuracy": float("nan"),
        "balanced_accuracy": float("nan"),
        "up_precision": float("nan"),
        "down_precision": float("nan"),
        "average_actual_return_after_bullish": float("nan"),
        "average_actual_return_after_bearish": float("nan"),
    }


def _safe_balanced_accuracy(frame: pd.DataFrame) -> float:
    if frame["actual_class"].nunique() < 2:
        return float("nan")
    return float(balanced_accuracy_score(frame["actual_class"], frame["predicted_class"]))


def _precision(frame: pd.DataFrame, label: str) -> float:
    return float(precision_score(frame["actual_class"], frame["predicted_class"], labels=[label], average="micro", zero_division=0))


def _mean_return(frame: pd.DataFrame, predicted_class: str) -> float:
    subset = frame[frame["predicted_class"] == predicted_class]
    return float(subset["actual_return"].mean()) if len(subset) else float("nan")

