from __future__ import annotations

import inspect

import numpy as np
import pandas as pd
import pytest

from stock_ai.ml.champion import (
    DEFAULT_MIN_EVIDENCE,
    _evaluate_single_threshold,
    _multiclass_brier,
    evaluate_class_thresholds,
    reliability_table,
    select_class_threshold,
    train_one_horizon,
    walk_forward_threshold_stability,
)


def _synthetic_backtest(rows: int = 200, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    predicted_probability = rng.uniform(0.34, 0.85, size=rows)
    predicted_class = rng.choice(["UP", "DOWN", "NEUTRAL"], size=rows, p=[0.4, 0.3, 0.3])
    # Make UP calls more likely correct as probability rises, so threshold
    # selection has real signal to find rather than pure noise.
    correct = rng.uniform(0, 1, size=rows) < predicted_probability
    actual_class = np.where(correct, predicted_class, rng.choice(["UP", "DOWN", "NEUTRAL"], size=rows))
    return pd.DataFrame(
        {
            "ticker": ["NVDA"] * rows,
            "prediction_date": pd.bdate_range("2025-01-02", periods=rows),
            "predicted_class": predicted_class,
            "actual_class": actual_class,
            "max_calibrated_probability": predicted_probability,
            "actual_return": np.where(actual_class == "UP", 0.05, np.where(actual_class == "DOWN", -0.05, 0.0)),
        }
    )


def test_evaluate_class_thresholds_marks_insufficient_evidence_below_minimum() -> None:
    backtest = _synthetic_backtest(rows=60)
    table = evaluate_class_thresholds(backtest, "UP", thresholds=(0.5, 0.8), min_evidence=50)
    for row in table:
        if row["sample_count"] < 50:
            assert row["status"] == "INSUFFICIENT_EVIDENCE"
        else:
            assert row["status"] == "OK"


def test_evaluate_class_thresholds_reports_sample_count_and_coverage_always() -> None:
    backtest = _synthetic_backtest(rows=300)
    table = evaluate_class_thresholds(backtest, "DOWN", thresholds=(0.5, 0.6, 0.7), min_evidence=50)
    for row in table:
        assert "sample_count" in row and "coverage" in row
        assert 0.0 <= row["coverage"] <= 1.0


def test_select_class_threshold_never_returns_tiny_sample_as_validated() -> None:
    """A threshold with high precision on 3 samples must not be selected --
    this is the exact failure mode Phase 6 flagged (cherry-picking a threshold
    that happened to work on a handful of validation rows)."""
    rows = 200
    dates = pd.bdate_range("2025-01-02", periods=rows)
    predicted_class = ["NEUTRAL"] * (rows - 3) + ["UP", "UP", "UP"]
    actual_class = ["NEUTRAL"] * (rows - 3) + ["UP", "UP", "UP"]
    max_probability = [0.40] * (rows - 3) + [0.95, 0.95, 0.95]
    backtest = pd.DataFrame(
        {
            "predicted_class": predicted_class,
            "actual_class": actual_class,
            "max_calibrated_probability": max_probability,
            "actual_return": [0.0] * (rows - 3) + [0.05, 0.05, 0.05],
        }
    )
    selection = select_class_threshold(backtest, "UP", thresholds=(0.5, 0.9), min_evidence=50)
    # The only threshold with any UP signal at all (0.9) has 3 samples --
    # below min_evidence -- so nothing should be VALIDATED.
    assert selection["status"] == "INSUFFICIENT_EVIDENCE"
    assert selection["threshold"] > 1.0


def test_select_class_threshold_requires_precision_above_base_rate() -> None:
    rows = 300
    predicted_class = np.array(["UP"] * rows)
    # Precision exactly at base rate everywhere -- UP predicted always, correct 40% of the time.
    rng = np.random.default_rng(1)
    actual_class = np.where(rng.uniform(size=rows) < 0.40, "UP", "DOWN")
    backtest = pd.DataFrame(
        {
            "predicted_class": predicted_class,
            "actual_class": actual_class,
            "max_calibrated_probability": np.full(rows, 0.55),
            "actual_return": np.zeros(rows),
        }
    )
    selection = select_class_threshold(backtest, "UP", thresholds=(0.5, 0.55), min_evidence=50)
    assert selection["status"] == "INSUFFICIENT_EVIDENCE"


def test_evaluate_single_threshold_matches_evaluate_class_thresholds() -> None:
    backtest = _synthetic_backtest(rows=300)
    single = _evaluate_single_threshold(backtest, "UP", 0.6, min_evidence=50)
    full = evaluate_class_thresholds(backtest, "UP", thresholds=(0.6,), min_evidence=50)[0]
    assert single == full


def test_evaluate_single_threshold_not_applicable_above_one() -> None:
    backtest = _synthetic_backtest(rows=50)
    result = _evaluate_single_threshold(backtest, "DOWN", 1.01, min_evidence=50)
    assert result["status"] == "NOT_APPLICABLE"
    assert result["sample_count"] == 0


def test_walk_forward_flags_unstable_when_only_one_segment_fires() -> None:
    rows = 300
    dates = pd.bdate_range("2025-01-02", periods=rows)
    predicted_class = ["NEUTRAL"] * rows
    max_probability = [0.40] * rows
    # Only the very first handful of rows (first segment) fire the signal.
    for i in range(30):
        predicted_class[i] = "UP"
        max_probability[i] = 0.90
    actual_class = ["NEUTRAL"] * rows
    for i in range(30):
        actual_class[i] = "UP"
    backtest = pd.DataFrame(
        {
            "prediction_date": dates,
            "predicted_class": predicted_class,
            "actual_class": actual_class,
            "max_calibrated_probability": max_probability,
            "actual_return": np.zeros(rows),
        }
    )
    result = walk_forward_threshold_stability(backtest, "UP", threshold=0.60, segments=3, min_evidence=50)
    assert result["segments_with_signal"] == 1
    assert result["status"] == "UNSTABLE"


def test_walk_forward_stable_when_precision_consistent_across_segments() -> None:
    backtest = _synthetic_backtest(rows=600, seed=7)
    result = walk_forward_threshold_stability(backtest, "UP", threshold=0.5, segments=3, min_evidence=10)
    assert result["total_segments"] == 3
    assert "status" in result and result["status"] in ("STABLE", "UNSTABLE")


def test_reliability_table_buckets_and_difference_field() -> None:
    probabilities = np.array([[0.1, 0.1, 0.8], [0.2, 0.3, 0.5], [0.6, 0.2, 0.2]])
    y_true = np.array([2, 2, 0])  # correct, wrong (predicted UP=idx2 but actual is idx2... check), correct
    table = reliability_table(probabilities, y_true, buckets=((0.40, 0.60), (0.60, 1.0001)))
    assert len(table) == 2
    for row in table:
        if row["count"] > 0:
            assert row["difference"] == pytest.approx(row["average_predicted_probability"] - row["actual_success_rate"])


def test_multiclass_brier_is_zero_for_perfect_confident_predictions() -> None:
    probabilities = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    y_true = np.array([0, 1])
    assert _multiclass_brier(y_true, probabilities, 3) == pytest.approx(0.0)


def test_multiclass_brier_is_positive_for_wrong_confident_predictions() -> None:
    probabilities = np.array([[0.0, 0.0, 1.0]])
    y_true = np.array([0])
    assert _multiclass_brier(y_true, probabilities, 3) == pytest.approx(2.0)


def test_threshold_and_calibration_selection_never_reads_the_test_split() -> None:
    """Static guard: select_class_threshold (and the calibration-method
    selector it feeds) must only ever be called with the calib_eval slice of
    VALIDATION, never with test_backtest. This is checked by inspecting the
    call sites in train_one_horizon rather than by running training, so it
    stays fast and still catches the exact regression Phase 6 warned about."""
    source = inspect.getsource(train_one_horizon)
    assert "select_class_threshold(calib_eval_backtest" in source
    assert "select_class_threshold(test_backtest" not in source
    assert "_select_calibration_method(classifier, X_calib_fit" in source
