from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from stock_ai.models.market_data import PriceBar
from stock_ai.models.predictions import PredictionRecord
from stock_ai.services.prediction_history import backfill_outcomes, compute_model_version, record_prediction


def _signal(
    ticker="NVDA",
    horizon="5d",
    as_of="2026-01-05",
    direction="UP",
    current_price=100.0,
    predicted_return=0.05,
    signal_status=None,
    classification_version="random_forest_5d_seed42",
) -> dict:
    return {
        "ticker": ticker,
        "as_of": as_of,
        "horizon": horizon,
        "current_price": current_price,
        "classification": {
            "direction": direction,
            "raw_probability": 0.80,
            "calibrated_probability": 0.65,
            "signal_status": signal_status or ("BULLISH" if direction == "UP" else "NO_STRONG_SIGNAL"),
            "confidence": "MEDIUM",
        },
        "regression": {
            "predicted_return": predicted_return,
            "model_target_price": current_price * (1 + predicted_return),
            "uncertainty_low": current_price * 0.95,
            "uncertainty_high": current_price * 1.15,
        },
        "model": {
            "classification_version": classification_version,
            "regression_version": "random_forest_raw_5d",
            "calibration_method": "sigmoid",
        },
    }


def _add_future_bars(db_session, ticker: str, start: date, closes: list[float], step_days: int = 1) -> None:
    """Adds one PriceBar per close, `step_days` calendar days apart -- pass a
    non-1 step to simulate weekends/holidays sitting between trading rows,
    proving the resolver counts SESSIONS (rows), never calendar days."""
    current = start
    for close in closes:
        current = date.fromordinal(current.toordinal() + step_days)
        db_session.add(PriceBar(ticker=ticker, date=current, open=close, high=close, low=close, close=close, adjusted_close=close, volume=1000, source="test"))
    db_session.commit()


def test_record_prediction_inserts_a_row(db_session) -> None:
    record = record_prediction(db_session, _signal())
    assert record.id is not None
    assert record.ticker == "NVDA"
    assert record.horizon == "5d"
    assert record.predicted_class == "UP"
    assert record.outcome_status == "PENDING"
    assert record.actual_future_price is None
    assert record.signal_outcome is None
    assert record.model_version == compute_model_version(_signal()["model"])


def test_duplicate_snapshot_same_ticker_horizon_date_model_is_not_created(db_session) -> None:
    """Pressing Refresh five times on the same market date against the same
    champion models must not create five rows."""
    first = record_prediction(db_session, _signal(predicted_return=0.05))
    second = record_prediction(db_session, _signal(predicted_return=0.05))
    third = record_prediction(db_session, _signal(predicted_return=0.05))

    assert first.id == second.id == third.id
    rows = list(db_session.scalars(select(PredictionRecord)))
    assert len(rows) == 1


def test_snapshot_is_immutable_even_if_the_incoming_signal_differs(db_session) -> None:
    """Fairness rule: once created, a snapshot's predicted values are frozen.
    Calling record_prediction again for the same (ticker, horizon, date,
    model_version) with DIFFERENT numbers must not change the stored row --
    this simulates a hypothetical re-run producing slightly different output
    and proves the original snapshot survives untouched."""
    first = record_prediction(db_session, _signal(predicted_return=0.05, current_price=100.0))
    original_target = first.model_target_price
    original_current_price = first.current_price

    mutated_signal = _signal(predicted_return=0.50, current_price=999.0)  # same key, wildly different values
    second = record_prediction(db_session, mutated_signal)

    assert second.id == first.id
    assert second.model_target_price == original_target
    assert second.current_price == original_current_price
    assert second.predicted_return == pytest.approx(Decimal("0.05"))


def test_different_model_version_creates_a_separate_row(db_session) -> None:
    """A future retrain must produce a distinguishable new snapshot rather
    than overwrite or blend with the old model's prediction."""
    v1 = record_prediction(db_session, _signal(classification_version="random_forest_5d_seed42"))
    v2 = record_prediction(db_session, _signal(classification_version="random_forest_5d_seed43"))

    assert v1.id != v2.id
    assert v1.model_version != v2.model_version
    rows = list(db_session.scalars(select(PredictionRecord)))
    assert len(rows) == 2


def test_backfill_outcomes_skips_predictions_not_yet_due(db_session) -> None:
    record_prediction(db_session, _signal(as_of="2026-01-05", horizon="5d"))
    result = backfill_outcomes(db_session)
    assert result["updated"] == 0
    assert result["skipped_not_due"] == 1
    row = db_session.scalar(select(PredictionRecord))
    assert row.outcome_status == "PENDING"
    # Missing sessions are never approximated with a guessed date.
    assert row.final_day_date is None


def test_5d_resolution_uses_exactly_the_fifth_future_trading_row_ignoring_weekends(db_session) -> None:
    record_prediction(db_session, _signal(ticker="NVDA", horizon="5d", as_of="2026-01-05", direction="UP", current_price=100.0, predicted_return=0.05))
    # 5 trading rows spaced with weekend-like gaps (2-day steps) -- the
    # resolver must use the 5th ROW, not "5 calendar days after as_of".
    _add_future_bars(db_session, "NVDA", date(2026, 1, 5), closes=[101, 103, 107, 109, 110.0], step_days=2)

    result = backfill_outcomes(db_session, ticker="NVDA")
    assert result["updated"] == 1

    row = db_session.scalar(select(PredictionRecord).where(PredictionRecord.ticker == "NVDA"))
    assert row.outcome_status == "RESOLVED"
    assert row.actual_future_price == pytest.approx(Decimal("110"))
    assert row.actual_return == pytest.approx(Decimal("0.1"), abs=1e-6)
    # final_day_date is the exact 5th future ROW's date (Jan 5 + 2*5 = Jan 15
    # calendar days later, because of the 2-day weekend-like gaps) -- never
    # prediction_date + 5 calendar days (which would be Jan 10).
    assert row.final_day_date == date(2026, 1, 15)


def test_10d_resolution_requires_exactly_ten_future_rows(db_session) -> None:
    record_prediction(db_session, _signal(ticker="NVDA", horizon="10d", as_of="2026-01-05", current_price=100.0, predicted_return=0.05))
    _add_future_bars(db_session, "NVDA", date(2026, 1, 5), closes=[100 + i for i in range(1, 10)])  # only 9 rows -- not due yet

    result = backfill_outcomes(db_session, ticker="NVDA")
    assert result["updated"] == 0
    assert result["skipped_not_due"] == 1

    db_session.add(PriceBar(ticker="NVDA", date=date(2026, 1, 20), open=115, high=115, low=115, close=115, adjusted_close=115, volume=1000, source="test"))
    db_session.commit()

    result = backfill_outcomes(db_session, ticker="NVDA")
    assert result["updated"] == 1
    row = db_session.scalar(select(PredictionRecord).where(PredictionRecord.ticker == "NVDA", PredictionRecord.horizon == "10d"))
    assert row.actual_future_price == pytest.approx(Decimal("115"))
    assert row.final_day_date == date(2026, 1, 20)  # the exact 10th future row's date, not a calendar-arithmetic guess


def test_15d_resolution_requires_exactly_fifteen_future_rows(db_session) -> None:
    record_prediction(db_session, _signal(ticker="NVDA", horizon="15d", as_of="2026-01-05", current_price=100.0, predicted_return=0.05))
    _add_future_bars(db_session, "NVDA", date(2026, 1, 5), closes=[100 + i for i in range(1, 15)])  # 14 rows -- not due yet
    assert backfill_outcomes(db_session, ticker="NVDA")["updated"] == 0

    db_session.add(PriceBar(ticker="NVDA", date=date(2026, 2, 5), open=120, high=120, low=120, close=120, adjusted_close=120, volume=1000, source="test"))
    db_session.commit()
    result = backfill_outcomes(db_session, ticker="NVDA")
    assert result["updated"] == 1
    row = db_session.scalar(select(PredictionRecord).where(PredictionRecord.ticker == "NVDA", PredictionRecord.horizon == "15d"))
    assert row.actual_future_price == pytest.approx(Decimal("120"))
    assert row.final_day_date == date(2026, 2, 5)  # the exact 15th future row's date, not a calendar-arithmetic guess


def test_outcome_calculation_signed_absolute_and_percentage_error(db_session) -> None:
    record_prediction(db_session, _signal(ticker="NVDA", horizon="5d", as_of="2026-01-05", current_price=100.0, predicted_return=0.05))  # predicted price 105
    _add_future_bars(db_session, "NVDA", date(2026, 1, 5), closes=[101, 102, 103, 104, 110.0])

    backfill_outcomes(db_session, ticker="NVDA")
    row = db_session.scalar(select(PredictionRecord).where(PredictionRecord.ticker == "NVDA"))

    # predicted 105, actual 110 -> signed = 105 - 110 = -5
    assert row.signed_price_error == pytest.approx(Decimal("-5"))
    assert row.absolute_price_error == pytest.approx(Decimal("5"))
    # abs(predicted - actual) / actual = 5 / 110
    assert row.absolute_percentage_error == pytest.approx(Decimal(str(5 / 110)), abs=1e-6)


def test_regression_direction_match_true_when_signs_agree(db_session) -> None:
    record_prediction(db_session, _signal(ticker="NVDA", horizon="5d", as_of="2026-01-05", current_price=100.0, predicted_return=0.05))
    _add_future_bars(db_session, "NVDA", date(2026, 1, 5), closes=[101, 102, 103, 104, 110.0])  # actual return positive, like predicted
    backfill_outcomes(db_session, ticker="NVDA")
    row = db_session.scalar(select(PredictionRecord).where(PredictionRecord.ticker == "NVDA"))
    assert row.regression_direction_match is True


def test_regression_direction_match_false_when_signs_disagree(db_session) -> None:
    record_prediction(db_session, _signal(ticker="AMD", horizon="5d", as_of="2026-01-05", current_price=100.0, predicted_return=0.05))
    _add_future_bars(db_session, "AMD", date(2026, 1, 5), closes=[99, 97, 95, 92, 90.0])  # actual return negative, predicted positive
    backfill_outcomes(db_session, ticker="AMD")
    row = db_session.scalar(select(PredictionRecord).where(PredictionRecord.ticker == "AMD"))
    assert row.regression_direction_match is False


def test_bullish_signal_outcome_correct_when_actual_return_exceeds_threshold(db_session) -> None:
    record_prediction(db_session, _signal(ticker="NVDA", horizon="5d", as_of="2026-01-05", direction="UP", signal_status="BULLISH", current_price=100.0, predicted_return=0.05))
    _add_future_bars(db_session, "NVDA", date(2026, 1, 5), closes=[101, 103, 107, 109, 110.0])  # +10% actual
    backfill_outcomes(db_session, ticker="NVDA")
    row = db_session.scalar(select(PredictionRecord).where(PredictionRecord.ticker == "NVDA"))
    assert row.signal_outcome == "CORRECT"


def test_bullish_signal_outcome_incorrect_when_actual_return_falls(db_session) -> None:
    record_prediction(db_session, _signal(ticker="AMD", horizon="5d", as_of="2026-01-05", direction="UP", signal_status="BULLISH", current_price=100.0, predicted_return=0.05))
    _add_future_bars(db_session, "AMD", date(2026, 1, 5), closes=[99, 97, 95, 92, 90.0])
    backfill_outcomes(db_session, ticker="AMD")
    row = db_session.scalar(select(PredictionRecord).where(PredictionRecord.ticker == "AMD"))
    assert row.signal_outcome == "INCORRECT"


def test_no_strong_signal_outcome_is_not_applicable_never_scored(db_session) -> None:
    """This is the key anti-inflation guard: an abstention must never be
    counted as correct or incorrect, no matter which way the market moved."""
    record_prediction(db_session, _signal(ticker="MU", horizon="5d", as_of="2026-01-05", direction="UP", signal_status="NO_STRONG_SIGNAL", current_price=100.0, predicted_return=0.05))
    _add_future_bars(db_session, "MU", date(2026, 1, 5), closes=[101, 103, 107, 109, 110.0])  # market moved up a lot -- still must not count as "correct"
    backfill_outcomes(db_session, ticker="MU")
    row = db_session.scalar(select(PredictionRecord).where(PredictionRecord.ticker == "MU"))
    assert row.signal_outcome == "NOT_APPLICABLE"


def test_bearish_signal_outcome_evaluated_against_its_own_threshold(db_session) -> None:
    record_prediction(db_session, _signal(ticker="SMCI", horizon="5d", as_of="2026-01-05", direction="DOWN", signal_status="BEARISH", current_price=100.0, predicted_return=-0.05))
    _add_future_bars(db_session, "SMCI", date(2026, 1, 5), closes=[99, 97, 95, 92, 90.0])  # -10% actual
    backfill_outcomes(db_session, ticker="SMCI")
    row = db_session.scalar(select(PredictionRecord).where(PredictionRecord.ticker == "SMCI"))
    assert row.signal_outcome == "CORRECT"


def test_backfill_outcomes_is_idempotent(db_session) -> None:
    record_prediction(db_session, _signal(ticker="MU", horizon="5d", as_of="2026-01-05", current_price=100.0))
    _add_future_bars(db_session, "MU", date(2026, 1, 5), closes=[100, 100, 100, 100, 105])

    first = backfill_outcomes(db_session, ticker="MU")
    row_after_first = db_session.scalar(select(PredictionRecord).where(PredictionRecord.ticker == "MU"))
    first_evaluated_at = row_after_first.outcome_evaluated_at
    first_error = row_after_first.absolute_price_error

    second = backfill_outcomes(db_session, ticker="MU")
    row_after_second = db_session.scalar(select(PredictionRecord).where(PredictionRecord.ticker == "MU"))

    assert first["updated"] == 1
    assert second["updated"] == 0
    assert second["total_pending"] == 0
    # Running it twice must not touch an already-resolved row again.
    assert row_after_second.outcome_evaluated_at == first_evaluated_at
    assert row_after_second.absolute_price_error == first_error


def test_pending_predictions_are_excluded_from_a_naive_resolved_scan(db_session) -> None:
    record_prediction(db_session, _signal(ticker="RDDT", horizon="5d", as_of="2026-01-05", current_price=100.0))
    backfill_outcomes(db_session, ticker="RDDT")  # not due -- stays pending
    resolved = list(db_session.scalars(select(PredictionRecord).where(PredictionRecord.outcome_status == "RESOLVED")))
    assert resolved == []
