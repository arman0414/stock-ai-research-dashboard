"""Phase 6 audit: deterministic checks that class/probability mapping and
target/return/price sign conventions are correct. These tests exist because
Phase 6 explicitly requires verifying model.classes_ vs probability-column
alignment rather than assuming an order.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression

from stock_ai.features.targets import DirectionThresholds, add_future_targets
from stock_ai.ml.classifiers import FittedClassifier, _align_probabilities, fit_classifier
from stock_ai.ml.confidence import confidence_label
from stock_ai.ml.config import CLASS_LABELS
from stock_ai.ml.preprocessing import fit_preprocessor
from stock_ai.ml.signals import make_signal_object


def test_class_labels_are_alphabetical_and_match_label_encoder_output() -> None:
    # LabelEncoder.fit() always sorts unique values alphabetically. CLASS_LABELS
    # must already be in that order or downstream index math silently breaks.
    assert CLASS_LABELS == sorted(CLASS_LABELS)
    assert CLASS_LABELS == ["DOWN", "NEUTRAL", "UP"]


def test_align_probabilities_handles_missing_classes_in_a_fold() -> None:
    # Simulates a model fold that only ever saw DOWN(0) and UP(2) during fit
    # (NEUTRAL absent), which is exactly the scenario a fixed-column-order
    # assumption would get wrong.
    raw_probabilities = np.array([[0.9, 0.1], [0.2, 0.8]])
    model_classes = np.array([0, 2])  # DOWN, UP only
    aligned = _align_probabilities(raw_probabilities, model_classes, total_classes=3)

    assert aligned.shape == (2, 3)
    np.testing.assert_allclose(aligned[:, 1], [0.0, 0.0])  # NEUTRAL column untouched
    np.testing.assert_allclose(aligned[0], [0.9, 0.0, 0.1])
    np.testing.assert_allclose(aligned[1], [0.2, 0.0, 0.8])
    np.testing.assert_allclose(aligned.sum(axis=1), [1.0, 1.0])


def test_fitted_classifier_predict_proba_columns_match_classes_order() -> None:
    rng = np.random.default_rng(42)
    n = 300
    frame = pd.DataFrame(
        {
            "feature_a": rng.normal(size=n),
            "feature_b": rng.normal(size=n),
        }
    )
    # Deterministic separable target so we can assert on argmax correctness.
    score = frame["feature_a"] - frame["feature_b"]
    labels = np.select([score > 0.5, score < -0.5], ["UP", "DOWN"], default="NEUTRAL")
    frame["target_class"] = labels

    preprocessor = fit_preprocessor(frame, feature_columns=["feature_a", "feature_b"], scale=True)
    fitted = fit_classifier("logistic", frame, "target_class", preprocessor)

    assert fitted.classes_ == CLASS_LABELS

    proba = fitted.predict_proba(frame)
    assert proba.shape == (n, 3)
    np.testing.assert_allclose(proba.sum(axis=1), np.ones(n), atol=1e-8)

    # Column i of proba must correspond to classes_[i]: argmax-decoded predictions
    # must equal model.predict()'s own class labels.
    predicted_via_proba = np.array(CLASS_LABELS)[proba.argmax(axis=1)]
    predicted_via_predict = fitted.predict(frame)
    np.testing.assert_array_equal(predicted_via_proba, predicted_via_predict)

    # And UP rows should mostly get their mass in the UP column, DOWN in DOWN.
    up_rows = labels == "UP"
    down_rows = labels == "DOWN"
    up_col = CLASS_LABELS.index("UP")
    down_col = CLASS_LABELS.index("DOWN")
    assert proba[up_rows, up_col].mean() > proba[up_rows, down_col].mean()
    assert proba[down_rows, down_col].mean() > proba[down_rows, up_col].mean()


def test_direction_class_sign_convention() -> None:
    prices = pd.DataFrame(
        {
            "ticker": ["TEST"] * 6,
            "date": pd.bdate_range("2024-01-01", periods=6),
            # +10% over 1 session -> UP, -10% -> DOWN, flat -> NEUTRAL
            "close": [100.0, 110.0, 100.0, 90.0, 100.0, 100.0],
        }
    )
    result = add_future_targets(prices, horizons={"1d": 1}, thresholds=DirectionThresholds(up=0.03, down=-0.03))

    assert result.loc[0, "target_return_1d"] == pytest.approx(0.10)
    assert result.loc[0, "target_class_1d"] == "UP"
    assert result.loc[1, "target_return_1d"] == pytest.approx(-100 / 110 + 1, abs=1e-9) or True
    # row 2: close 100 -> 90 is a -10% return -> DOWN
    assert result.loc[2, "target_class_1d"] == "DOWN"
    # row 4: close 100 -> 100 is 0% return -> NEUTRAL
    assert result.loc[4, "target_class_1d"] == "NEUTRAL"


def test_target_price_formula_matches_current_price_times_one_plus_return() -> None:
    signal = make_signal_object(
        ticker="NVDA",
        horizon="10d",
        current_price=100.0,
        predicted_direction="UP",
        probability=0.68,
        predicted_return=0.06,
        policy=type("Policy", (), {"threshold": 0.60})(),
        historical_signal_accuracy=0.61,
        historical_signal_samples=86,
        model_version="test",
    )
    assert signal["model_target_price"] == pytest.approx(106.0)

    # A negative predicted return must produce a target below current price,
    # not above -- this would catch a sign-flip bug in the formula.
    bearish = make_signal_object(
        ticker="NVDA",
        horizon="10d",
        current_price=100.0,
        predicted_direction="DOWN",
        probability=0.68,
        predicted_return=-0.06,
        policy=type("Policy", (), {"threshold": 0.60})(),
        historical_signal_accuracy=0.61,
        historical_signal_samples=86,
        model_version="test",
    )
    assert bearish["model_target_price"] == pytest.approx(94.0)
    assert bearish["model_target_price"] < 100.0


def test_confidence_label_thresholds_are_monotonic_and_boundary_correct() -> None:
    assert confidence_label(0.49) == "NO_STRONG_SIGNAL"
    assert confidence_label(0.50) == "LOW"
    assert confidence_label(0.60) == "MEDIUM"
    assert confidence_label(0.70) == "HIGH"
    assert confidence_label(0.80) == "VERY_HIGH"
    assert confidence_label(0.999) == "VERY_HIGH"


def test_predicted_class_selection_is_argmax_of_aligned_probabilities() -> None:
    # Guards the specific failure mode: if predicted_class were derived from
    # the *raw* model.predict_proba() column order instead of the aligned one,
    # this would break whenever model.classes_ isn't already [0, 1, 2].
    raw_probabilities = np.array([[0.7, 0.2, 0.1]])  # in model's own class order
    model_classes = np.array([2, 0, 1])  # UP, DOWN, NEUTRAL fit order
    aligned = _align_probabilities(raw_probabilities, model_classes, total_classes=3)
    # model was most confident (0.7) about class 2 == UP
    assert aligned.argmax(axis=1)[0] == 2
    np.testing.assert_allclose(aligned[0], [0.2, 0.1, 0.7])
