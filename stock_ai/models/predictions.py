from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Index, Numeric, String, UniqueConstraint, func
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
    signed_price_error: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)  # predicted - actual
    absolute_price_error: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    absolute_percentage_error: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)  # fraction, e.g. 0.0171 = 1.71%
    regression_direction_match: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    signal_outcome: Mapped[str | None] = mapped_column(String(16), nullable=True)  # CORRECT | INCORRECT | NOT_APPLICABLE
    outcome_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
