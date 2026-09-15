from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConfidenceThresholds:
    low: float = 0.50
    medium: float = 0.60
    high: float = 0.70
    very_high: float = 0.80


def confidence_label(max_probability: float, thresholds: ConfidenceThresholds | None = None) -> str:
    thresholds = thresholds or ConfidenceThresholds()
    if max_probability < thresholds.low:
        return "NO_STRONG_SIGNAL"
    if max_probability < thresholds.medium:
        return "LOW"
    if max_probability < thresholds.high:
        return "MEDIUM"
    if max_probability < thresholds.very_high:
        return "HIGH"
    return "VERY_HIGH"

