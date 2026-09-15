from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from stock_ai.models.market_data import PriceBar
from stock_ai.models.watchlist import WatchlistStock
from stock_ai.schemas.stocks import StockCreate, StockDetail, normalize_ticker


def list_stocks(db: Session) -> list[WatchlistStock]:
    return list(db.scalars(select(WatchlistStock).order_by(WatchlistStock.ticker)))


def get_stock(db: Session, ticker: str) -> WatchlistStock | None:
    return db.scalar(select(WatchlistStock).where(WatchlistStock.ticker == normalize_ticker(ticker)))


def create_stock(db: Session, payload: StockCreate, data_source: str = "stooq") -> WatchlistStock:
    ticker = normalize_ticker(payload.ticker)
    existing = get_stock(db, ticker)
    if existing:
        raise ValueError(f"{ticker} is already in the watchlist")

    stock = WatchlistStock(
        ticker=ticker,
        company_name=payload.company_name.strip() if payload.company_name else None,
        data_source=data_source,
    )
    db.add(stock)
    db.commit()
    db.refresh(stock)
    return stock


def delete_stock(db: Session, ticker: str) -> bool:
    stock = get_stock(db, ticker)
    if not stock:
        return False

    db.delete(stock)
    db.commit()
    return True


def get_stock_detail(db: Session, ticker: str) -> StockDetail | None:
    stock = get_stock(db, ticker)
    if not stock:
        return None

    latest_bar = db.scalar(
        select(PriceBar)
        .where(PriceBar.ticker == stock.ticker)
        .order_by(PriceBar.date.desc())
        .limit(1)
    )
    history_count = db.scalar(select(func.count()).select_from(PriceBar).where(PriceBar.ticker == stock.ticker)) or 0

    latest_price: Decimal | None = latest_bar.close if latest_bar else None
    latest_price_date = latest_bar.date if latest_bar else None

    return StockDetail(
        id=stock.id,
        ticker=stock.ticker,
        company_name=stock.company_name,
        data_source=stock.data_source,
        created_at=stock.created_at,
        updated_at=stock.updated_at,
        last_refreshed_at=stock.last_refreshed_at,
        latest_price=latest_price,
        latest_price_date=latest_price_date,
        price_history_count=history_count,
    )

