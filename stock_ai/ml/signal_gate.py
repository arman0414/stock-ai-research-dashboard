"""Phase 7: signal gating from CALIBRATED probabilities only.

NO_STRONG_SIGNAL is the safe default. A directional call requires the
predicted class, a validated per-class calibrated-probability threshold,
sufficient historical evidence for that threshold, and (optionally) an
acceptable setup-quality reading. Raw/uncalibrated probabilities are never
read by this module -- callers must calibrate first.
"""
from __future__ import annotations

from dataclasses import dataclass


NO_STRONG_SIGNAL = "NO_STRONG_SIGNAL"
BULLISH = "BULLISH"
BEARISH = "BEARISH"

CONFIDENCE_BOUNDARIES = ((0.50, "LOW"), (0.60, "MEDIUM"), (0.70, "HIGH"), (0.80, "VERY_HIGH"))


@dataclass(frozen=True)
class ThresholdPolicy:
    """A validated, per-class, per-horizon decision rule. Never built from raw probabilities."""

    class_label: str
    threshold: float
    status: str  # "VALIDATED" | "INSUFFICIENT_EVIDENCE" | "NOT_APPLICABLE"
    min_evidence: int = 50

    @property
    def is_usable(self) -> bool:
        return self.status == "VALIDATED" and self.threshold <= 1.0


def confidence_label(calibrated_probability: float) -> str:
    """Coarse display label. Empirically, calibrated probabilities for this
    system rarely exceed ~0.70 (see reliability tables) -- this label is a
    convenience bucket, not a claim that e.g. 0.80 means an 80% historical hit
    rate. Use historical_signal_accuracy for the honest number."""
    label = NO_STRONG_SIGNAL
    for boundary, name in CONFIDENCE_BOUNDARIES:
        if calibrated_probability >= boundary:
            label = name
    return label


def decide_signal(
    predicted_class: str,
    calibrated_up_probability: float,
    calibrated_down_probability: float,
    bullish_policy: ThresholdPolicy,
    bearish_policy: ThresholdPolicy,
    setup_quality: str | None = None,
    require_setup_quality: bool = False,
    unsupported_regime: bool = False,
) -> dict:
    """Returns {"signal_status", "confidence", "gating_reason"}.

    Gating reads ONLY calibrated_up_probability / calibrated_down_probability --
    never a raw model probability. Every rejection path is explicit so the
    reason a signal was withheld is inspectable, not silently defaulted.
    """
    if unsupported_regime:
        return {"signal_status": NO_STRONG_SIGNAL, "confidence": NO_STRONG_SIGNAL, "gating_reason": "UNSUPPORTED_REGIME"}

    if require_setup_quality and setup_quality not in ("MODERATE", "STRONG"):
        return {"signal_status": NO_STRONG_SIGNAL, "confidence": NO_STRONG_SIGNAL, "gating_reason": "SETUP_QUALITY_TOO_WEAK"}

    if predicted_class == "UP":
        if not bullish_policy.is_usable:
            return {"signal_status": NO_STRONG_SIGNAL, "confidence": NO_STRONG_SIGNAL, "gating_reason": "BULLISH_THRESHOLD_NOT_VALIDATED"}
        if calibrated_up_probability < bullish_policy.threshold:
            return {"signal_status": NO_STRONG_SIGNAL, "confidence": confidence_label(calibrated_up_probability), "gating_reason": "BELOW_BULLISH_THRESHOLD"}
        return {"signal_status": BULLISH, "confidence": confidence_label(calibrated_up_probability), "gating_reason": "VALIDATED_BULLISH"}

    if predicted_class == "DOWN":
        if not bearish_policy.is_usable:
            return {"signal_status": NO_STRONG_SIGNAL, "confidence": NO_STRONG_SIGNAL, "gating_reason": "BEARISH_THRESHOLD_NOT_VALIDATED"}
        if calibrated_down_probability < bearish_policy.threshold:
            return {"signal_status": NO_STRONG_SIGNAL, "confidence": confidence_label(calibrated_down_probability), "gating_reason": "BELOW_BEARISH_THRESHOLD"}
        return {"signal_status": BEARISH, "confidence": confidence_label(calibrated_down_probability), "gating_reason": "VALIDATED_BEARISH"}

    return {"signal_status": NO_STRONG_SIGNAL, "confidence": NO_STRONG_SIGNAL, "gating_reason": "PREDICTED_NEUTRAL"}


_VALID_STATUSES = ("VALIDATED", "INSUFFICIENT_EVIDENCE", "NOT_APPLICABLE")


def threshold_policy_from_metadata(threshold_metadata: dict, min_evidence: int = 50) -> ThresholdPolicy:
    status = threshold_metadata["status"] if threshold_metadata["status"] in _VALID_STATUSES else "NOT_APPLICABLE"
    return ThresholdPolicy(
        class_label=threshold_metadata["class_label"],
        threshold=float(threshold_metadata["threshold"]),
        status=status,
        min_evidence=min_evidence,
    )
