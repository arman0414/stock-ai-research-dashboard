from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from stock_ai.schemas.stocks import normalize_ticker


class PositionCreate(BaseModel):
    ticker: str = Field(..., examples=["NVDA"])
    shares: Decimal = Field(..., gt=0, max_digits=18, decimal_places=6)
    purchase_price: Decimal = Field(..., gt=0, max_digits=18, decimal_places=6)
    purchase_date: date
    my_target_price: Decimal | None = Field(default=None, gt=0)
    stop_loss_price: Decimal | None = Field(default=None, gt=0)
    notes: str | None = None

    def normalized_ticker(self) -> str:
        return normalize_ticker(self.ticker)


class PositionUpdate(BaseModel):
    """The user's own annotations only.

    `shares` / `purchase_price` are intentionally absent: quantity and cost
    basis are derived from the transaction ledger, so changing what you own
    goes through buy/sell and leaves history behind.
    """

    model_config = ConfigDict(extra="forbid")
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


class PositionBuy(BaseModel):
    """Adding to (or opening) a holding. Fees are capitalised into cost basis."""

    quantity: Decimal = Field(..., gt=0, max_digits=18, decimal_places=6)
    price_per_share: Decimal = Field(..., gt=0, max_digits=18, decimal_places=6)
    transaction_date: datetime | None = None
    fees: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=6)
    notes: str | None = None


class PositionSell(BaseModel):
    """Reducing or closing a holding. Fees reduce net proceeds."""

    quantity: Decimal = Field(..., gt=0, max_digits=18, decimal_places=6)
    price_per_share: Decimal = Field(..., gt=0, max_digits=18, decimal_places=6)
    transaction_date: datetime | None = None
    fees: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=6)
    notes: str | None = None


class PositionTransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    transaction_type: str
    quantity: Decimal
    price_per_share: Decimal
    fees: Decimal
    transaction_date: datetime | None
    notes: str | None
    source: str
    cycle_index: int
    cost_basis_per_share: Decimal | None
    cost_basis_total: Decimal | None
    sale_proceeds: Decimal | None
    realized_profit_loss: Decimal | None
    realized_profit_loss_pct: Decimal | None
    created_at: datetime | None
