from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from stock_ai.schemas.stocks import normalize_ticker


class PositionCreate(BaseModel):
    ticker: str = Field(..., examples=["NVDA"])
    shares: Decimal = Field(..., gt=0)
    purchase_price: Decimal = Field(..., gt=0)
    purchase_date: date
    my_target_price: Decimal | None = Field(default=None, gt=0)
    stop_loss_price: Decimal | None = Field(default=None, gt=0)
    notes: str | None = None

    def normalized_ticker(self) -> str:
        return normalize_ticker(self.ticker)


class PositionUpdate(BaseModel):
    shares: Decimal | None = Field(default=None, gt=0)
    purchase_price: Decimal | None = Field(default=None, gt=0)
    purchase_date: date | None = None
    my_target_price: Decimal | None = Field(default=None, gt=0)
    stop_loss_price: Decimal | None = Field(default=None, gt=0)
    notes: str | None = None


class PositionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    shares: Decimal
    purchase_price: Decimal
    purchase_date: date
    my_target_price: Decimal | None
    stop_loss_price: Decimal | None
    notes: str | None
    created_at: datetime | None
    updated_at: datetime | None
