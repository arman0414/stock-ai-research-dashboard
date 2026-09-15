"""Phase 7: prediction snapshot storage and later outcome backfill (sections 24/25).

Storing a prediction and training a model are separate operations -- this
module only ever reads already-generated signal objects and already-cached
PriceBar rows. Nothing here retrains anything or runs on a schedule; a
schedule can be layered on top of backfill_outcomes() later if wanted.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from stock_ai.features.targets import DEFAULT_HORIZONS
from stock_ai.models.market_data import PriceBar
from stock_ai.models.predictions import PredictionRecord
from stock_ai.schemas.stocks import normalize_ticker


FIXED_DIRECTION_THRESHOLD = 0.03


def record_prediction(db: Session, signal: dict) -> PredictionRecord:
    ticker = normalize_ticker(signal["ticker"])
    horizon = signal["horizon"]
    prediction_date = pd.to_datetime(signal["as_of"]).date()
    classification = signal["classification"]
    regression = signal["regression"]
    model = signal["model"]

    values = dict(
        current_price=Decimal(str(signal["current_price"])),
        predicted_class=classification["direction"],
        raw_probability=Decimal(str(classification["raw_probability"])),
        calibrated_probability=Decimal(str(classification["calibrated_probability"])),
        signal_status=classification["signal_status"],
        confidence=classification["confidence"],
        predicted_return=Decimal(str(regression["predicted_return"])),
        model_target_price=Decimal(str(regression["model_target_price"])),
        uncertainty_low=Decimal(str(regression["uncertainty_low"])),
        uncertainty_high=Decimal(str(regression["uncertainty_high"])),
        classification_version=str(model["classification_version"]),
        regression_version=str(model["regression_version"]),
        calibration_method=str(model["calibration_method"]),
    )

    existing = db.scalar(
        select(PredictionRecord).where(
            PredictionRecord.ticker == ticker,
            PredictionRecord.horizon == horizon,
            PredictionRecord.prediction_date == prediction_date,
        )
    )
    if existing:
        for key, value in values.items():
            setattr(existing, key, value)
        db.commit()
        db.refresh(existing)
        return existing

    record = PredictionRecord(ticker=ticker, horizon=horizon, prediction_date=prediction_date, **values)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def backfill_outcomes(db: Session, ticker: str | None = None) -> dict:
    """Fills in actual outcomes for predictions old enough that `horizon`
    trading sessions have since occurred. Safe to call repeatedly -- rows
    already evaluated are skipped, and rows not yet due are left untouched."""
    query = select(PredictionRecord).where(PredictionRecord.actual_future_price.is_(None))
    if ticker:
        query = query.where(PredictionRecord.ticker == normalize_ticker(ticker))
    pending = list(db.scalars(query))

    updated = 0
    skipped_not_due = 0

    for record in pending:
        sessions = DEFAULT_HORIZONS.get(record.horizon)
        if sessions is None:
            continue

        future_bars = list(
            db.scalars(
                select(PriceBar)
                .where(PriceBar.ticker == record.ticker, PriceBar.date > record.prediction_date)
                .order_by(PriceBar.date.asc())
                .limit(sessions)
            )
        )
        if len(future_bars) < sessions:
            skipped_not_due += 1
            continue

        target_bar = future_bars[sessions - 1]
        actual_future_price = float(target_bar.close)
        current_price = float(record.current_price)
        actual_return = actual_future_price / current_price - 1 if current_price else 0.0
        target_price_abs_error = abs(float(record.model_target_price) - actual_future_price)
        target_price_pct_error = abs(float(record.model_target_price) / actual_future_price - 1) if actual_future_price else None

        record.actual_future_price = Decimal(str(actual_future_price))
        record.actual_return = Decimal(str(actual_return))
        record.classification_correct = _classification_correct(record.predicted_class, actual_return)
        record.target_price_abs_error = Decimal(str(target_price_abs_error))
        record.target_price_pct_error = None if target_price_pct_error is None else Decimal(str(target_price_pct_error))
        record.outcome_evaluated_at = datetime.now(timezone.utc)
        updated += 1

    db.commit()
    return {"updated": updated, "skipped_not_due": skipped_not_due, "total_pending": len(pending)}


def _classification_correct(predicted_class: str, actual_return: float) -> bool:
    if predicted_class == "UP":
        return actual_return > FIXED_DIRECTION_THRESHOLD
    if predicted_class == "DOWN":
        return actual_return < -FIXED_DIRECTION_THRESHOLD
    return -FIXED_DIRECTION_THRESHOLD <= actual_return <= FIXED_DIRECTION_THRESHOLD
