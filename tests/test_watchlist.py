from __future__ import annotations

import pytest

from stock_ai.schemas.stocks import StockCreate
from stock_ai.services import watchlist


def test_create_list_and_get_stock_normalizes_ticker(db_session) -> None:
    created = watchlist.create_stock(
        db_session,
        StockCreate(ticker=" aapl ", company_name="Apple Inc."),
    )

    assert created.ticker == "AAPL"
    assert created.company_name == "Apple Inc."

    stocks = watchlist.list_stocks(db_session)
    assert [stock.ticker for stock in stocks] == ["AAPL"]

    detail = watchlist.get_stock_detail(db_session, "aapl")
    assert detail is not None
    assert detail.ticker == "AAPL"
    assert detail.latest_price is None
    assert detail.price_history_count == 0


def test_create_stock_rejects_duplicates(db_session) -> None:
    watchlist.create_stock(db_session, StockCreate(ticker="MSFT"))

    with pytest.raises(ValueError, match="already in the watchlist"):
        watchlist.create_stock(db_session, StockCreate(ticker="msft"))


def test_delete_stock(db_session) -> None:
    watchlist.create_stock(db_session, StockCreate(ticker="NVDA"))

    assert watchlist.delete_stock(db_session, "nvda") is True
    assert watchlist.delete_stock(db_session, "nvda") is False

