from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Index, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from stock_ai.db.session import Base


class Position(Base):
    """A manually-entered holding for Phase 8's My Positions page.

    No brokerage integration -- shares/prices/dates are user-entered and
    editable. `my_target_price`/`stop_loss_price` are the user's own targets
    and must never be confused with the model's predicted target price,
    which is computed fresh from the prediction service, not stored here."""

    __tablename__ = "positions"
    __table_args__ = (Index("ix_positions_ticker", "ticker"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    shares: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    purchase_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    purchase_date: Mapped[date] = mapped_column(Date, nullable=False)
    my_target_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    stop_loss_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
