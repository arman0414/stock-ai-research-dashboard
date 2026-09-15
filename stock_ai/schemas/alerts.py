from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from stock_ai.models.alerts import ALERT_TYPES
from stock_ai.schemas.stocks import normalize_ticker


class AlertRuleCreate(BaseModel):
    ticker: str = Field(..., examples=["NVDA"])
    alert_type: str = Field(..., examples=["MY_TARGET_PRICE"])
    threshold_price: Decimal | None = Field(default=None, gt=0)

    @field_validator("ticker")
    @classmethod
    def validate_ticker(cls, value: str) -> str:
        return normalize_ticker(value)

    @field_validator("alert_type")
    @classmethod
    def validate_alert_type(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in ALERT_TYPES:
            raise ValueError(f"Unsupported alert_type. Must be one of: {', '.join(ALERT_TYPES)}")
        return normalized


class AlertRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    alert_type: str
    threshold_price: Decimal | None
    is_active: bool
    last_triggered_at: datetime | None
    last_triggered_message: str | None
    created_at: datetime | None


class AlertStatus(BaseModel):
    rule: AlertRuleRead
    is_triggered: bool
    message: str | None
    current_price: Decimal | None
    model_5d_signal: str | None
