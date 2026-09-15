from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from stock_ai.config import Settings
from stock_ai.models.market_data import PriceBar
from stock_ai.models.predictions import PredictionRecord
from stock_ai.services.prediction_history import backfill_outcomes, record_prediction


def _signal(ticker="NVDA", horizon="5d", as_of="2026-01-05", direction="UP", current_price=100.0, predicted_return=0.05) -> dict:
    return {
        "ticker": ticker,
        "as_of": as_of,
        "horizon": horizon,
        "current_price": current_price,
        "classification": {
            "direction": direction,
            "raw_probability": 0.80,
            "calibrated_probability": 0.65,
            "signal_status": "BULLISH" if direction == "UP" else "NO_STRONG_SIGNAL",
            "confidence": "MEDIUM",
        },
        "regression": {
            "predicted_return": predicted_return,
            "model_target_price": current_price * (1 + predicted_return),
            "uncertainty_low": current_price * 0.95,
            "uncertainty_high": current_price * 1.15,
        },
        "model": {
            "classification_version": "random_forest_5d_seed42",
            "regression_version": "random_forest_raw_5d",
            "calibration_method": "sigmoid",
        },
    }


def test_record_prediction_inserts_a_row(db_session) -> None:
    record = record_prediction(db_session, _signal())
    assert record.id is not None
    assert record.ticker == "NVDA"
    assert record.horizon == "5d"
    assert record.predicted_class == "UP"
    assert record.actual_future_price is None
    assert record.classification_correct is None


def test_record_prediction_upserts_same_ticker_horizon_date(db_session) -> None:
    first = record_prediction(db_session, _signal(predicted_return=0.05))
    second = record_prediction(db_session, _signal(predicted_return=0.09))

    assert first.id == second.id
    rows = list(db_session.scalars(select(PredictionRecord)))
    assert len(rows) == 1
    assert rows[0].predicted_return == pytest.approx(Decimal("0.09"))


def test_backfill_outcomes_skips_predictions_not_yet_due(db_session) -> None:
    record_prediction(db_session, _signal(as_of="2026-01-05", horizon="5d"))
    # No future PriceBar rows exist at all.
    result = backfill_outcomes(db_session)
    assert result["updated"] == 0
    assert result["skipped_not_due"] == 1


def test_backfill_outcomes_fills_actual_price_and_correctness(db_session) -> None:
    record_prediction(db_session, _signal(ticker="NVDA", horizon="5d", as_of="2026-01-05", direction="UP", current_price=100.0, predicted_return=0.05))

    prediction_day = date(2026, 1, 5)
    for offset in range(1, 6):
        db_session.add(
            PriceBar(
                ticker="NVDA",
                date=date(2026, 1, 5 + offset),
                open=100 + offset,
                high=100 + offset,
                low=100 + offset,
                close=110.0 if offset == 5 else 100 + offset,
                adjusted_close=110.0 if offset == 5 else 100 + offset,
                volume=1000,
                source="test",
            )
        )
    db_session.commit()

    result = backfill_outcomes(db_session, ticker="NVDA")
    assert result["updated"] == 1

    row = db_session.scalar(select(PredictionRecord).where(PredictionRecord.ticker == "NVDA"))
    assert row.actual_future_price == pytest.approx(Decimal("110"))
    assert row.actual_return == pytest.approx(Decimal("0.1"), abs=1e-6)
    assert row.classification_correct is True  # UP predicted, +10% actual > 3% threshold
    assert row.target_price_abs_error == pytest.approx(Decimal("5"))  # target 105 vs actual 110
    assert row.outcome_evaluated_at is not None


def test_backfill_outcomes_marks_wrong_direction_incorrect(db_session) -> None:
    record_prediction(db_session, _signal(ticker="AMD", horizon="5d", as_of="2026-01-05", direction="UP", current_price=100.0, predicted_return=0.05))

    for offset in range(1, 6):
        db_session.add(
            PriceBar(
                ticker="AMD",
                date=date(2026, 1, 5 + offset),
                open=100 - offset,
                high=100 - offset,
                low=100 - offset,
                close=90.0 if offset == 5 else 100 - offset,
                adjusted_close=90.0 if offset == 5 else 100 - offset,
                volume=1000,
                source="test",
            )
        )
    db_session.commit()

    backfill_outcomes(db_session, ticker="AMD")
    row = db_session.scalar(select(PredictionRecord).where(PredictionRecord.ticker == "AMD"))
    assert row.classification_correct is False


def test_backfill_outcomes_is_idempotent(db_session) -> None:
    record_prediction(db_session, _signal(ticker="MU", horizon="5d", as_of="2026-01-05", current_price=100.0))
    for offset in range(1, 6):
        db_session.add(
            PriceBar(ticker="MU", date=date(2026, 1, 5 + offset), open=100, high=100, low=100, close=105, adjusted_close=105, volume=500, source="test")
        )
    db_session.commit()

    first = backfill_outcomes(db_session, ticker="MU")
    second = backfill_outcomes(db_session, ticker="MU")
    assert first["updated"] == 1
    assert second["updated"] == 0
    assert second["total_pending"] == 0
