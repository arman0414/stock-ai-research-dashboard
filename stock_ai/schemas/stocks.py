from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def normalize_ticker(value: str) -> str:
    ticker = value.strip().upper()
    if not ticker:
        raise ValueError("Ticker is required")
    if len(ticker) > 16:
        raise ValueError("Ticker must be 16 characters or fewer")
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-")
    if any(char not in allowed for char in ticker):
        raise ValueError("Ticker may only contain letters, numbers, dots, or hyphens")
    return ticker


class StockCreate(BaseModel):
    ticker: str = Field(..., examples=["AAPL"])
    company_name: str | None = Field(default=None, examples=["Apple Inc."])

    @field_validator("ticker")
    @classmethod
    def validate_ticker(cls, value: str) -> str:
        return normalize_ticker(value)


class StockRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    company_name: str | None
    data_source: str
    created_at: datetime | None
    updated_at: datetime | None
    last_refreshed_at: datetime | None


class PriceBarRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ticker: str
    date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    adjusted_close: Decimal
    volume: int
    source: str


class StockDetail(StockRead):
    latest_price: Decimal | None = None
    latest_price_date: date | None = None
    price_history_count: int = 0


class RefreshResult(BaseModel):
    ticker: str
    source: str
    start_date: date
    end_date: date
    rows_received: int
    rows_stored: int
    latest_price: Decimal | None = None
    latest_price_date: date | None = None


class RefreshAllResult(BaseModel):
    refreshed: list[RefreshResult]
    failed: dict[str, str]

