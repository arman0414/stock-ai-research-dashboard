from __future__ import annotations

from datetime import date
from decimal import Decimal

from stock_ai.data.providers.market.stooq import StooqMarketDataProvider


def test_stooq_csv_parser_filters_dates_and_uses_close_as_adjusted_close() -> None:
    payload = """Date,Open,High,Low,Close,Volume
2026-01-02,100,102,99,101,1000000
2026-01-03,101,103,100,102,1200000
"""
    provider = StooqMarketDataProvider()

    bars = provider._parse_csv(payload, ticker="AAPL", start_date=date(2026, 1, 3), end_date=date(2026, 1, 3))

    assert len(bars) == 1
    assert bars[0].date == date(2026, 1, 3)
    assert bars[0].close == Decimal("102")
    assert bars[0].adjusted_close == Decimal("102")
    assert bars[0].volume == 1_200_000

