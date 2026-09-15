from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from stock_ai.db.session import Base


ALERT_TYPES = (
    "MY_TARGET_PRICE",
    "MY_STOP_LOSS",
    "MODEL_SIGNAL_CHANGED",
    "BULLISH_SIGNAL_APPEARED",
    "MAJOR_POSITIVE_NEWS",
    "MAJOR_NEGATIVE_NEWS",
    "UNUSUAL_VOLUME",
    "SUPPORT_BREAK",
    "RESISTANCE_BREAKOUT",
)


class AlertRule(Base):
    """A user-configured watch condition, evaluated on demand (see
    stock_ai/services/alerts.py) rather than by a background scheduler.
    In-app only for this phase -- no email/SMS delivery is wired up yet."""

    __tablename__ = "alert_rules"
    __table_args__ = (Index("ix_alert_rules_ticker", "ticker"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    alert_type: Mapped[str] = mapped_column(String(32), nullable=False)
    threshold_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_triggered_message: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
