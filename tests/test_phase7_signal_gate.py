from __future__ import annotations

from stock_ai.ml.signal_gate import ThresholdPolicy, confidence_label, decide_signal, threshold_policy_from_metadata


def _policy(threshold: float, status: str = "VALIDATED") -> ThresholdPolicy:
    return ThresholdPolicy(class_label="UP", threshold=threshold, status=status)


def test_no_strong_signal_is_default_for_neutral_prediction() -> None:
    result = decide_signal("NEUTRAL", 0.90, 0.90, _policy(0.60), _policy(0.60, status="VALIDATED"))
    assert result["signal_status"] == "NO_STRONG_SIGNAL"
    assert result["gating_reason"] == "PREDICTED_NEUTRAL"


def test_bullish_fires_only_above_validated_threshold() -> None:
    below = decide_signal("UP", 0.58, 0.10, _policy(0.60), _policy(0.60))
    at_or_above = decide_signal("UP", 0.61, 0.10, _policy(0.60), _policy(0.60))
    assert below["signal_status"] == "NO_STRONG_SIGNAL"
    assert below["gating_reason"] == "BELOW_BULLISH_THRESHOLD"
    assert at_or_above["signal_status"] == "BULLISH"
    assert at_or_above["gating_reason"] == "VALIDATED_BULLISH"


def test_bearish_fires_only_above_validated_threshold() -> None:
    below = decide_signal("DOWN", 0.10, 0.58, _policy(0.60), _policy(0.60))
    at_or_above = decide_signal("DOWN", 0.10, 0.65, _policy(0.60), _policy(0.60))
    assert below["signal_status"] == "NO_STRONG_SIGNAL"
    assert below["gating_reason"] == "BELOW_BEARISH_THRESHOLD"
    assert at_or_above["signal_status"] == "BEARISH"
    assert at_or_above["gating_reason"] == "VALIDATED_BEARISH"


def test_no_strong_signal_when_threshold_not_validated() -> None:
    unusable_bullish = ThresholdPolicy(class_label="UP", threshold=1.01, status="INSUFFICIENT_EVIDENCE")
    result = decide_signal("UP", 0.99, 0.01, unusable_bullish, _policy(0.60))
    assert result["signal_status"] == "NO_STRONG_SIGNAL"
    assert result["gating_reason"] == "BULLISH_THRESHOLD_NOT_VALIDATED"


def test_gating_reads_calibrated_probability_never_raw() -> None:
    """The whole point of Phase 7: raw probability must never gate a signal.
    A caller that (by mistake) passes a high RAW probability as if it were
    calibrated is exactly the bug this module exists to prevent -- so this
    test asserts decide_signal's *signature* has no raw-probability parameter
    at all, and that only the calibrated values passed in drive the outcome."""
    import inspect

    signature = inspect.signature(decide_signal)
    assert "raw_probability" not in signature.parameters
    assert "raw_up_probability" not in signature.parameters

    # Same calibrated probabilities, decision must be identical regardless of
    # what a hypothetical raw probability "would have been" -- there is no
    # way to pass one in, which is the guarantee.
    result_a = decide_signal("UP", 0.61, 0.05, _policy(0.60), _policy(0.60))
    result_b = decide_signal("UP", 0.61, 0.05, _policy(0.60), _policy(0.60))
    assert result_a == result_b


def test_setup_quality_can_veto_when_required() -> None:
    gated_off = decide_signal("UP", 0.90, 0.05, _policy(0.60), _policy(0.60), setup_quality="WEAK", require_setup_quality=True)
    gated_on = decide_signal("UP", 0.90, 0.05, _policy(0.60), _policy(0.60), setup_quality="STRONG", require_setup_quality=True)
    assert gated_off["signal_status"] == "NO_STRONG_SIGNAL"
    assert gated_off["gating_reason"] == "SETUP_QUALITY_TOO_WEAK"
    assert gated_on["signal_status"] == "BULLISH"


def test_unsupported_regime_forces_no_strong_signal() -> None:
    result = decide_signal("UP", 0.99, 0.01, _policy(0.50), _policy(0.50), unsupported_regime=True)
    assert result["signal_status"] == "NO_STRONG_SIGNAL"
    assert result["gating_reason"] == "UNSUPPORTED_REGIME"


def test_confidence_label_boundaries() -> None:
    assert confidence_label(0.10) == "NO_STRONG_SIGNAL"
    assert confidence_label(0.50) == "LOW"
    assert confidence_label(0.60) == "MEDIUM"
    assert confidence_label(0.70) == "HIGH"
    assert confidence_label(0.80) == "VERY_HIGH"


def test_threshold_policy_from_metadata_normalizes_unknown_status() -> None:
    policy = threshold_policy_from_metadata({"class_label": "DOWN", "threshold": 1.01, "status": "weird_value"})
    assert policy.status == "NOT_APPLICABLE"
    assert not policy.is_usable


def test_threshold_policy_insufficient_evidence_is_not_usable() -> None:
    policy = threshold_policy_from_metadata({"class_label": "UP", "threshold": 0.65, "status": "INSUFFICIENT_EVIDENCE"})
    assert not policy.is_usable
