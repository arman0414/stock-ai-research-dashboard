from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from stock_ai.db.session import Base


class DailyRunLog(Base):
    """One row per execution of the daily prediction/evaluation cycle
    (scripts/run_daily_cycle.py). Purely observational -- never read by the
    prediction pipeline itself, only by the Settings/Model Performance UI."""

    __tablename__ = "daily_run_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latest_market_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    tickers_processed: Mapped[int] = mapped_column(Integer, default=0)
    tickers_failed: Mapped[int] = mapped_column(Integer, default=0)
    predictions_saved: Mapped[int] = mapped_column(Integer, default=0)
    duplicates_skipped: Mapped[int] = mapped_column(Integer, default=0)
    outcomes_resolved: Mapped[int] = mapped_column(Integer, default=0)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="RUNNING")  # RUNNING | SUCCESS | PARTIAL_FAILURE | FAILURE
    failures_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list of {"ticker": ..., "error": ...}
