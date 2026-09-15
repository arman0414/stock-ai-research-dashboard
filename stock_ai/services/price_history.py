from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from stock_ai.data.providers.market.base import DailyPrice, MarketDataProvider
from stock_ai.models.market_data import PriceBar
from stock_ai.schemas.stocks import RefreshAllResult, RefreshResult, normalize_ticker
from stock_ai.services.watchlist import get_stock, list_stocks


def _default_start_date(end_date: date, years: int) -> date:
    return end_date - timedelta(days=365 * years + 10)


def _incremental_start_date(db: Session, ticker: str, source: str, requested_start: date, overlap_days: int = 7) -> date:
    latest_date = db.scalar(
        select(func.max(PriceBar.date)).where(
            PriceBar.ticker == ticker,
            PriceBar.source == source,
        )
    )
    if latest_date is None:
        return requested_start
    return max(requested_start, latest_date - timedelta(days=overlap_days))


def _upsert_price_bar(db: Session, ticker: str, source: str, bar: DailyPrice) -> bool:
    existing = db.scalar(
        select(PriceBar).where(
            PriceBar.ticker == ticker,
            PriceBar.date == bar.date,
            PriceBar.source == source,
        )
    )

    if existing:
        existing.open = bar.open
        existing.high = bar.high
        existing.low = bar.low
        existing.close = bar.close
        existing.adjusted_close = bar.adjusted_close
        existing.volume = bar.volume
        existing.fetched_at = datetime.now(timezone.utc)
        return False

    db.add(
        PriceBar(
            ticker=ticker,
            date=bar.date,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            adjusted_close=bar.adjusted_close,
            volume=bar.volume,
            source=source,
        )
    )
    return True


def refresh_history(
    db: Session,
    provider: MarketDataProvider,
    ticker: str,
    years: int = 5,
    end_date: date | None = None,
) -> RefreshResult:
    ticker = normalize_ticker(ticker)
    stock = get_stock(db, ticker)
    if not stock:
        raise ValueError(f"{ticker} is not in the watchlist")

    end_date = end_date or date.today()
    requested_start_date = _default_start_date(end_date, years)
    start_date = _incremental_start_date(db, ticker, provider.name, requested_start_date)
    bars = provider.fetch_daily_history(ticker, start_date=start_date, end_date=end_date)

    stored_count = 0
    latest_bar: DailyPrice | None = None
    for bar in bars:
        if bar.date < start_date or bar.date > end_date:
            continue
        created = _upsert_price_bar(db, ticker=ticker, source=provider.name, bar=bar)
        stored_count += 1 if created else 0
        latest_bar = bar if latest_bar is None or bar.date > latest_bar.date else latest_bar

    stock.data_source = provider.name
    stock.last_refreshed_at = datetime.now(timezone.utc)
    db.commit()

    return RefreshResult(
        ticker=ticker,
        source=provider.name,
        start_date=start_date,
        end_date=end_date,
        rows_received=len(bars),
        rows_stored=stored_count,
        latest_price=latest_bar.close if latest_bar else None,
        latest_price_date=latest_bar.date if latest_bar else None,
    )


def refresh_all(db: Session, provider: MarketDataProvider, years: int = 5) -> RefreshAllResult:
    refreshed: list[RefreshResult] = []
    failed: dict[str, str] = {}

    for stock in list_stocks(db):
        try:
            refreshed.append(refresh_history(db, provider=provider, ticker=stock.ticker, years=years))
        except Exception as exc:  # Keep one bad ticker from stopping the full watchlist.
            db.rollback()
            failed[stock.ticker] = str(exc)

    return RefreshAllResult(refreshed=refreshed, failed=failed)
