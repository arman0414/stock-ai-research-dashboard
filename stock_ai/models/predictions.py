from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Index, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from stock_ai.db.session import Base


class PredictionRecord(Base):
    """One stored absolute-prediction snapshot for live forward evaluation.

    Fairness rule: once created, the prediction fields below (current_price
    through calibration_method) are FROZEN and never modified -- see
    stock_ai.services.prediction_history.record_prediction(). Only the
    outcome fields (outcome_status onward) are ever filled in later, once
    resolved by backfill_outcomes(), and only once.

    Uniqueness is (ticker, horizon, prediction_date, model_version) so that
    repeated refreshes on the same market date against the same champion
    models never create duplicate evaluation rows, and so that a future
    model retrain produces a distinguishable new version rather than
    silently overwriting or blending with old results.
    """

    __tablename__ = "prediction_records"
    __table_args__ = (
        UniqueConstraint("ticker", "horizon", "prediction_date", "model_version", name="uq_prediction_ticker_horizon_date_model"),
        Index("ix_prediction_records_ticker_horizon", "ticker", "horizon"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    horizon: Mapped[str] = mapped_column(String(8), nullable=False)
    prediction_date: Mapped[date] = mapped_column(Date, nullable=False)  # market as_of date
    model_version: Mapped[str] = mapped_column(String(256), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # LIVE_DAILY (scheduled job) | MANUAL_LIVE (dashboard-triggered) | BACKFILLED_REPLAY
    # (explicitly excluded from live performance -- see prediction_performance.py).
    prediction_source: Mapped[str] = mapped_column(String(20), nullable=False, default="MANUAL_LIVE")

    # --- Frozen prediction snapshot ---
    current_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    predicted_class: Mapped[str] = mapped_column(String(16), nullable=False)
    raw_probability: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    calibrated_probability: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    signal_status: Mapped[str] = mapped_column(String(24), nullable=False)
    confidence: Mapped[str] = mapped_column(String(24), nullable=False)
    predicted_return: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    model_target_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    uncertainty_low: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    uncertainty_high: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    classification_version: Mapped[str] = mapped_column(String(128), nullable=False)
    regression_version: Mapped[str] = mapped_column(String(128), nullable=False)
    calibration_method: Mapped[str] = mapped_column(String(16), nullable=False)

    # --- Outcome, filled once by backfill_outcomes() ---
    outcome_status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")  # PENDING | RESOLVED
    actual_future_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    actual_return: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    signed_price_error: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)  # predicted - actual (Phase 9 convention, kept as-is)
    absolute_price_error: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    absolute_percentage_error: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)  # fraction, e.g. 0.0171 = 1.71% (Phase 9 convention, kept as-is)
    regression_direction_match: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    signal_outcome: Mapped[str | None] = mapped_column(String(16), nullable=True)  # CORRECT | INCORRECT | NOT_APPLICABLE
    outcome_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- Phase 10: signed, human-facing difference fields ---
    # NOTE the deliberately different convention from the Phase 9 fields above:
    # sign is actual-minus-predicted (not predicted-minus-actual), and the
    # percentage fields store an actual percentage NUMBER (1.50 = 1.50%), not
    # a fraction. Added rather than redefining the existing fields, per the
    # "do not silently redefine an existing field" rule.
    signed_price_difference: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)  # actual - predicted
    signed_prediction_difference_pct: Mapped[Decimal | None] = mapped_column(Numeric(9, 4), nullable=True)  # (actual-predicted)/predicted * 100
    absolute_prediction_difference_pct: Mapped[Decimal | None] = mapped_column(Numeric(9, 4), nullable=True)  # abs() of the above

    # The calendar date of the EXACT PriceBar row used to resolve this
    # prediction -- i.e. the Nth future trading session, never
    # prediction_date + N calendar days. Set once, at the same time as
    # actual_future_price, by backfill_outcomes(). Displayed as "Final Day
    # Date" in the UI (actual_future_price is displayed as "Final Day Price").
    final_day_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # --- Entry Setup snapshot (stock_ai.services.entry_setup) ---
    # A research interpretation of this SAME frozen snapshot (using
    # current_price above as "current," since that's what existed at
    # creation time) -- GOOD_SETUP | WATCH | WAIT | INSUFFICIENT_DATA. Set
    # once at creation, alongside the rest of this frozen snapshot, and
    # NEVER touched by backfill_outcomes() -- this is what lets a future
    # analysis ask "when we said GOOD SETUP, how did it do?" without the
    # answer having been silently rewritten after the fact. entry_setup_version
    # records exactly which heuristic rules produced it, so a future rule
    # change (entry-v2) never silently blends with old results.
    entry_setup_state: Mapped[str | None] = mapped_column(String(24), nullable=True)
    entry_setup_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    entry_setup_reasons_json: Mapped[str | None] = mapped_column(Text, nullable=True)
