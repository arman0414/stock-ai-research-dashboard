from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Index, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from stock_ai.db.session import Base


class PredictionRecord(Base):
    """One stored absolute-prediction snapshot. Outcome fields stay NULL until
    enough trading sessions pass for stock_ai.services.prediction_history to
    backfill them (see design in section 25 of Phase 7)."""

    __tablename__ = "prediction_records"
    __table_args__ = (
        UniqueConstraint("ticker", "horizon", "prediction_date", name="uq_prediction_ticker_horizon_date"),
        Index("ix_prediction_records_ticker_horizon", "ticker", "horizon"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    horizon: Mapped[str] = mapped_column(String(8), nullable=False)
    prediction_date: Mapped[date] = mapped_column(Date, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

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

    actual_future_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    actual_return: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    classification_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    target_price_abs_error: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    target_price_pct_error: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    outcome_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
