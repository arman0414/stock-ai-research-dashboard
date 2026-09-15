from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from stock_ai.models.market_data import PriceBar
from stock_ai.models.predictions import PredictionRecord
from stock_ai.services.prediction_history import backfill_outcomes, record_prediction


def _signal(ticker: str, as_of: str, current_price: float, model_target_price: float, horizon: str = "5d") -> dict:
    return {
        "ticker": ticker,
        "as_of": as_of,
        "horizon": horizon,
        "current_price": current_price,
        "classification": {"direction": "UP", "raw_probability": 0.7, "calibrated_probability": 0.55, "signal_status": "NO_STRONG_SIGNAL", "confidence": "LOW"},
        "regression": {
            "predicted_return": (model_target_price / current_price) - 1,
            "model_target_price": model_target_price,
            "uncertainty_low": current_price * 0.9,
            "uncertainty_high": current_price * 1.15,
        },
        "model": {"classification_version": f"random_forest_{horizon}_seed42", "regression_version": f"random_forest_raw_{horizon}", "calibration_method": "sigmoid"},
    }


def _mature(db_session, ticker: str, start: date, actual_close: float, horizon: str = "5d") -> PredictionRecord:
    sessions = {"5d": 5, "10d": 10, "15d": 15}[horizon]
    for offset in range(1, sessions + 1):
        close = actual_close if offset == sessions else 100.0
        db_session.add(PriceBar(ticker=ticker, date=date.fromordinal(start.toordinal() + offset), open=close, high=close, low=close, close=close, adjusted_close=close, volume=1000, source="test"))
    db_session.commit()
    backfill_outcomes(db_session, ticker=ticker)
    return db_session.scalar(select(PredictionRecord).where(PredictionRecord.ticker == ticker, PredictionRecord.horizon == horizon))


def test_signed_difference_positive_when_actual_finishes_higher(db_session) -> None:
    """Predicted $100, Actual $102 -> signed +$2.00 (+2.00%)."""
    record_prediction(db_session, _signal("NVDA", "2026-01-05", current_price=100.0, model_target_price=100.0))
    row = _mature(db_session, "NVDA", date(2026, 1, 5), actual_close=102.0)

    assert row.signed_price_difference == pytest.approx(2.0)
    assert row.signed_prediction_difference_pct == pytest.approx(2.0)
    assert row.absolute_prediction_difference_pct == pytest.approx(2.0)


def test_signed_difference_negative_when_actual_finishes_lower(db_session) -> None:
    """Predicted $100, Actual $98 -> signed -$2.00 (-2.00%)."""
    record_prediction(db_session, _signal("AMD", "2026-01-05", current_price=100.0, model_target_price=100.0))
    row = _mature(db_session, "AMD", date(2026, 1, 5), actual_close=98.0)

    assert row.signed_price_difference == pytest.approx(-2.0)
    assert row.signed_prediction_difference_pct == pytest.approx(-2.0)
    assert row.absolute_prediction_difference_pct == pytest.approx(2.0)


def test_signed_difference_matches_the_worked_example_from_the_spec(db_session) -> None:
    """Predicted $213.00, Actual $216.20 -> signed +$3.20, ~+1.50%."""
    record_prediction(db_session, _signal("MU", "2026-01-05", current_price=210.0, model_target_price=213.0))
    row = _mature(db_session, "MU", date(2026, 1, 5), actual_close=216.20)

    assert float(row.signed_price_difference) == pytest.approx(3.20, abs=1e-6)
    assert float(row.signed_prediction_difference_pct) == pytest.approx(1.5023, abs=1e-3)
    assert float(row.absolute_prediction_difference_pct) <= 2.0  # falls in the WITHIN ±2% band


def test_old_phase9_fields_are_not_redefined_and_use_their_own_sign_convention(db_session) -> None:
    """signed_price_error (Phase 9) is predicted-minus-actual -- the OPPOSITE
    sign of the new signed_price_difference (actual-minus-predicted). Both
    must coexist untouched."""
    record_prediction(db_session, _signal("SMCI", "2026-01-05", current_price=100.0, model_target_price=100.0))
    row = _mature(db_session, "SMCI", date(2026, 1, 5), actual_close=102.0)

    assert row.signed_price_error == pytest.approx(-2.0)  # predicted(100) - actual(102)
    assert row.signed_price_difference == pytest.approx(2.0)  # actual(102) - predicted(100)
    assert row.signed_price_error == -row.signed_price_difference


@pytest.mark.parametrize(
    "actual_close,expected_abs_pct",
    [
        (102.0, 2.0),
        (105.0, 5.0),
        (110.0, 10.0),
        (98.0, 2.0),
        (95.0, 5.0),
        (90.0, 10.0),
    ],
)
def test_accuracy_band_boundary_values(db_session, actual_close, expected_abs_pct) -> None:
    ticker = f"T{int(actual_close * 100)}"
    record_prediction(db_session, _signal(ticker, "2026-01-05", current_price=100.0, model_target_price=100.0))
    row = _mature(db_session, ticker, date(2026, 1, 5), actual_close=actual_close)
    assert row.absolute_prediction_difference_pct == pytest.approx(expected_abs_pct, abs=1e-6)


def test_prediction_source_validation_rejects_unknown_values(db_session) -> None:
    with pytest.raises(ValueError):
        record_prediction(db_session, _signal("NVDA", "2026-01-05", 100.0, 100.0), prediction_source="NOT_A_REAL_SOURCE")
