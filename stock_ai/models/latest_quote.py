from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from stock_ai.db.session import Base


class LatestQuote(Base):
    """The single most recently SUCCEEDED market quote per ticker -- purely
    a presentation/display cache, never touched by ML, never a PriceBar,
    never a PredictionRecord field.

    Exactly one row per ticker (see the unique constraint): a fresh
    successful quote UPSERTs this row rather than appending a new one --
    we deliberately do not keep intraday quote history here (see
    docs/ or the quote_service module docstring for why). A failed
    provider call NEVER writes here; this table only ever holds the last
    value that was genuinely confirmed by the provider.
    """

    __tablename__ = "latest_quotes"
    __table_args__ = (UniqueConstraint("ticker", name="uq_latest_quotes_ticker"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    quote_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    saved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    market_status: Mapped[str] = mapped_column(String(16), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    # Always False when written -- this table never persists a failed/stale
    # fetch (see module docstring). Kept for schema flexibility only.
    is_stale: Mapped[bool] = mapped_column(Boolean, default=False)
