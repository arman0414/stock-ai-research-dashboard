"""Live forward-evaluation snapshot storage and outcome resolution.

Fairness rule (critical): record_prediction() NEVER modifies an existing
snapshot's predicted values. Uniqueness is (ticker, horizon, prediction_date,
model_version) -- pressing Refresh repeatedly on the same market date against
the same champion models returns the existing frozen row untouched. Only
backfill_outcomes() ever writes to a row afterward, and only its outcome
fields, exactly once (it only considers rows still PENDING).

Storing a prediction and training a model are separate operations -- this
module only ever reads already-generated signal objects and already-cached
PriceBar rows. Nothing here retrains anything or runs on a schedule.
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


# Matches the fixed_3pct target definition the champion classifiers were
# trained against (see stock_ai/ml/champion.py) -- used only to judge whether
# a validated BULLISH/BEARISH call was directionally correct, never to alter
# any prediction value itself.
SIGNAL_DIRECTION_THRESHOLD = 0.03

PREDICTION_SOURCES = ("LIVE_DAILY", "MANUAL_LIVE", "BACKFILLED_REPLAY")


def compute_model_version(model: dict) -> str:
    """A stable, deterministic identifier for "which exact champion models
    produced this prediction" -- unchanged across repeated calls as long as
    the champion artifacts on disk are unchanged. Used both for the
    uniqueness constraint and later for grouping live-performance results by
    model version so a future retrain never silently blends with old results.
    """
    return f"{model['classification_version']}__{model['regression_version']}__{model['calibration_method']}"


def record_prediction(db: Session, signal: dict, prediction_source: str = "MANUAL_LIVE") -> PredictionRecord:
    """Backward-compatible wrapper -- see record_prediction_with_status()."""
    record, _created = record_prediction_with_status(db, signal, prediction_source=prediction_source)
    return record


def record_prediction_with_status(db: Session, signal: dict, prediction_source: str = "MANUAL_LIVE") -> tuple[PredictionRecord, bool]:
    """Creates the one official snapshot for (ticker, horizon, market as_of
    date, model_version) -- or returns the existing one untouched if it
    already exists, regardless of which prediction_source is requested this
    time. This is what makes "one official prediction per day" work: the
    scheduled LIVE_DAILY run and a MANUAL_LIVE dashboard click on the same
    market date can never both create a row. Returns (record, created) so
    callers (e.g. the daily cycle) can report accurate saved-vs-duplicate
    counts without re-querying."""
    if prediction_source not in PREDICTION_SOURCES:
        raise ValueError(f"Unknown prediction_source: {prediction_source}")

    ticker = normalize_ticker(signal["ticker"])
    horizon = signal["horizon"]
    prediction_date = pd.to_datetime(signal["as_of"]).date()
    model = signal["model"]
    model_version = compute_model_version(model)

    existing = db.scalar(
        select(PredictionRecord).where(
            PredictionRecord.ticker == ticker,
            PredictionRecord.horizon == horizon,
            PredictionRecord.prediction_date == prediction_date,
            PredictionRecord.model_version == model_version,
        )
    )
    if existing is not None:
        # Fairness rule: never touch a prediction snapshot's original values.
        return existing, False

    classification = signal["classification"]
    regression = signal["regression"]
    record = PredictionRecord(
        ticker=ticker,
        horizon=horizon,
        prediction_date=prediction_date,
        model_version=model_version,
        prediction_source=prediction_source,
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
        outcome_status="PENDING",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record, True


def backfill_outcomes(db: Session, ticker: str | None = None) -> dict:
    """Fills in actual outcomes for predictions old enough that exactly
    `horizon` future trading SESSIONS (rows in price_bars, never calendar
    days) now exist. Safe to call repeatedly and in any order -- only rows
    still PENDING are considered, and each is resolved at most once."""
    query = select(PredictionRecord).where(PredictionRecord.outcome_status == "PENDING")
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
        predicted_price = float(record.model_target_price)
        predicted_return = float(record.predicted_return)
        actual_return = actual_future_price / current_price - 1 if current_price else 0.0

        signed_price_error = predicted_price - actual_future_price
        absolute_price_error = abs(signed_price_error)
        absolute_percentage_error = absolute_price_error / actual_future_price if actual_future_price else None

        # Phase 10 fields: opposite sign convention (actual - predicted) and
        # percentage stored as an actual number (1.50 = 1.50%), not a fraction.
        signed_price_difference = actual_future_price - predicted_price
        signed_prediction_difference_pct = (signed_price_difference / predicted_price * 100) if predicted_price else None
        absolute_prediction_difference_pct = abs(signed_prediction_difference_pct) if signed_prediction_difference_pct is not None else None

        record.actual_future_price = Decimal(str(actual_future_price))
        record.actual_return = Decimal(str(actual_return))
        record.signed_price_error = Decimal(str(signed_price_error))
        record.absolute_price_error = Decimal(str(absolute_price_error))
        record.absolute_percentage_error = None if absolute_percentage_error is None else Decimal(str(absolute_percentage_error))
        record.regression_direction_match = _sign(predicted_return) == _sign(actual_return)
        record.signal_outcome = _signal_outcome(record.signal_status, actual_return)
        record.signed_price_difference = Decimal(str(signed_price_difference))
        record.signed_prediction_difference_pct = None if signed_prediction_difference_pct is None else Decimal(str(round(signed_prediction_difference_pct, 6)))
        record.absolute_prediction_difference_pct = None if absolute_prediction_difference_pct is None else Decimal(str(round(absolute_prediction_difference_pct, 6)))
        record.outcome_status = "RESOLVED"
        record.outcome_evaluated_at = datetime.now(timezone.utc)
        updated += 1

    db.commit()
    return {"updated": updated, "skipped_not_due": skipped_not_due, "total_pending": len(pending)}


def _signal_outcome(signal_status: str, actual_return: float) -> str:
    """Only a VALIDATED signal (BULLISH/BEARISH) can be judged correct or
    incorrect. An abstention (NO_STRONG_SIGNAL) is never scored either way --
    scoring it would artificially inflate apparent signal accuracy by
    counting "no bet" as a win whenever the market happened to sit still."""
    if signal_status == "BULLISH":
        return "CORRECT" if actual_return > SIGNAL_DIRECTION_THRESHOLD else "INCORRECT"
    if signal_status == "BEARISH":
        return "CORRECT" if actual_return < -SIGNAL_DIRECTION_THRESHOLD else "INCORRECT"
    return "NOT_APPLICABLE"


def _sign(value: float) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def list_prediction_history(db: Session, ticker: str, horizon: str | None = None, limit: int = 50) -> list[PredictionRecord]:
    query = select(PredictionRecord).where(PredictionRecord.ticker == normalize_ticker(ticker))
    if horizon:
        query = query.where(PredictionRecord.horizon == horizon)
    query = query.order_by(PredictionRecord.prediction_date.desc()).limit(limit)
    return list(db.scalars(query))


def prediction_record_to_dict(record: PredictionRecord) -> dict:
    return {
        "id": record.id,
        "ticker": record.ticker,
        "horizon": record.horizon,
        "prediction_date": record.prediction_date.isoformat(),
        "generated_at": record.generated_at.isoformat() if record.generated_at else None,
        "model_version": record.model_version,
        "prediction_source": record.prediction_source,
        "current_price": float(record.current_price),
        "predicted_class": record.predicted_class,
        "raw_probability": float(record.raw_probability),
        "calibrated_probability": float(record.calibrated_probability),
        "signal_status": record.signal_status,
        "confidence": record.confidence,
        "predicted_return": float(record.predicted_return),
        "model_target_price": float(record.model_target_price),
        "uncertainty_low": float(record.uncertainty_low),
        "uncertainty_high": float(record.uncertainty_high),
        "classification_version": record.classification_version,
        "regression_version": record.regression_version,
        "calibration_method": record.calibration_method,
        "outcome_status": record.outcome_status,
        "actual_future_price": _maybe_float(record.actual_future_price),
        "actual_return": _maybe_float(record.actual_return),
        "signed_price_error": _maybe_float(record.signed_price_error),
        "absolute_price_error": _maybe_float(record.absolute_price_error),
        "absolute_percentage_error": _maybe_float(record.absolute_percentage_error),
        "regression_direction_match": record.regression_direction_match,
        "signal_outcome": record.signal_outcome,
        "outcome_evaluated_at": record.outcome_evaluated_at.isoformat() if record.outcome_evaluated_at else None,
        "signed_price_difference": _maybe_float(record.signed_price_difference),
        "signed_prediction_difference_pct": _maybe_float(record.signed_prediction_difference_pct),
        "absolute_prediction_difference_pct": _maybe_float(record.absolute_prediction_difference_pct),
    }


def _maybe_float(value: Decimal | None) -> float | None:
    return None if value is None else float(value)
