from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from stock_ai.models.market_data import PriceBar
from stock_ai.models.positions import Position
from stock_ai.schemas.positions import PositionCreate, PositionUpdate
from stock_ai.schemas.stocks import normalize_ticker


def list_positions(db: Session) -> list[Position]:
    return list(db.scalars(select(Position).order_by(Position.ticker)))


def get_position(db: Session, position_id: int) -> Position | None:
    return db.get(Position, position_id)


def create_position(db: Session, payload: PositionCreate) -> Position:
    position = Position(
        ticker=payload.normalized_ticker(),
        shares=payload.shares,
        purchase_price=payload.purchase_price,
        purchase_date=payload.purchase_date,
        my_target_price=payload.my_target_price,
        stop_loss_price=payload.stop_loss_price,
        notes=payload.notes,
    )
    db.add(position)
    db.commit()
    db.refresh(position)
    return position


def update_position(db: Session, position_id: int, payload: PositionUpdate) -> Position | None:
    position = get_position(db, position_id)
    if not position:
        return None
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(position, field, value)
    db.commit()
    db.refresh(position)
    return position


def delete_position(db: Session, position_id: int) -> bool:
    position = get_position(db, position_id)
    if not position:
        return False
    db.delete(position)
    db.commit()
    return True


def latest_price_for(db: Session, ticker: str) -> Decimal | None:
    bar = db.scalar(select(PriceBar).where(PriceBar.ticker == normalize_ticker(ticker)).order_by(PriceBar.date.desc()).limit(1))
    return bar.close if bar else None
