from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from stock_ai.data.providers.market.base import DailyPrice
from stock_ai.models.market_data import PriceBar
from stock_ai.schemas.stocks import StockCreate
from stock_ai.services import price_history, watchlist


class FakeMarketDataProvider:
    name = "fake"

    def __init__(self, bars: list[DailyPrice]) -> None:
        self.bars = bars
        self.calls: list[tuple[str, date, date]] = []

    def fetch_daily_history(self, ticker: str, start_date: date, end_date: date) -> list[DailyPrice]:
        self.calls.append((ticker, start_date, end_date))
        return self.bars


def make_bar(day: date, close: str = "101.00") -> DailyPrice:
    return DailyPrice(
        date=day,
        open=Decimal("100.00"),
        high=Decimal("103.00"),
        low=Decimal("99.00"),
        close=Decimal(close),
        adjusted_close=Decimal(close),
        volume=1_000_000,
    )


def test_refresh_history_stores_bars_and_filters_future_dates(db_session) -> None:
    watchlist.create_stock(db_session, StockCreate(ticker="AAPL"))
    provider = FakeMarketDataProvider(
        [
            make_bar(date(2024, 12, 30), "99.00"),
            make_bar(date(2025, 1, 6), "100.00"),
            make_bar(date(2026, 1, 10), "110.00"),
            make_bar(date(2026, 1, 11), "120.00"),
        ]
    )

    result = price_history.refresh_history(
        db_session,
        provider=provider,
        ticker="aapl",
        years=1,
        end_date=date(2026, 1, 10),
    )

    assert result.ticker == "AAPL"
    assert result.rows_received == 4
    assert result.rows_stored == 2
    assert result.latest_price == Decimal("110.00")
    assert result.latest_price_date == date(2026, 1, 10)
    assert provider.calls[0][0] == "AAPL"

    stored_dates = list(db_session.scalars(select(PriceBar.date).order_by(PriceBar.date)))
    assert stored_dates == [date(2025, 1, 6), date(2026, 1, 10)]


def test_refresh_history_upserts_without_duplicates(db_session) -> None:
    watchlist.create_stock(db_session, StockCreate(ticker="MSFT"))
    provider = FakeMarketDataProvider([make_bar(date(2026, 1, 10), "50.00")])

    first = price_history.refresh_history(db_session, provider, ticker="MSFT", end_date=date(2026, 1, 10))
    second = price_history.refresh_history(db_session, provider, ticker="MSFT", end_date=date(2026, 1, 10))

    count = db_session.scalar(select(func.count()).select_from(PriceBar))
    assert first.rows_stored == 1
    assert second.rows_stored == 0
    assert count == 1


def test_refresh_history_requires_watchlist_stock(db_session) -> None:
    provider = FakeMarketDataProvider([make_bar(date(2026, 1, 10))])

    with pytest.raises(ValueError, match="not in the watchlist"):
        price_history.refresh_history(db_session, provider, ticker="TSLA")
