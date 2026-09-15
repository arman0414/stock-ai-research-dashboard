from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from stock_ai.config import Settings
from stock_ai.data.providers.errors import ProviderError, ProviderQuotaError
from stock_ai.data.providers.market.factory import get_market_data_provider
from stock_ai.data.providers.market.twelve_data import parse_twelve_data_response
from stock_ai.data.providers.news.alpha_vantage import parse_alpha_vantage_news
from stock_ai.data.providers.news.factory import get_news_provider
from stock_ai.data.providers.market.base import DailyPrice
from stock_ai.schemas.stocks import StockCreate
from stock_ai.services.price_history import refresh_history
from stock_ai.services.watchlist import create_stock


def test_twelve_data_response_parsing_and_sorting() -> None:
    payload = {
        "values": [
            {"datetime": "2024-01-03", "open": "101", "high": "103", "low": "100", "close": "102", "volume": "1200"},
            {"datetime": "2024-01-02", "open": "100", "high": "102", "low": "99", "close": "101", "volume": "1000"},
        ]
    }

    bars = parse_twelve_data_response(payload, "AAPL", date(2024, 1, 1), date(2024, 1, 4))

    assert [bar.date for bar in bars] == [date(2024, 1, 2), date(2024, 1, 3)]
    assert bars[0].adjusted_close == bars[0].close
    assert bars[0].volume == 1000


def test_twelve_data_rejects_malformed_error_and_rate_limit_payloads() -> None:
    with pytest.raises(ProviderError):
        parse_twelve_data_response({"status": "error", "message": "bad symbol"}, "AAPL", date(2024, 1, 1), date(2024, 1, 4))
    with pytest.raises(ProviderQuotaError):
        parse_twelve_data_response({"message": "API quota exhausted"}, "AAPL", date(2024, 1, 1), date(2024, 1, 4))
    with pytest.raises(ProviderError):
        parse_twelve_data_response({"values": [{"datetime": "2024-01-02", "open": "10", "high": "9", "low": "8", "close": "10", "volume": "1"}]}, "AAPL", date(2024, 1, 1), date(2024, 1, 4))


def test_alpha_vantage_article_parsing_and_filtering() -> None:
    payload = {
        "feed": [
            {
                "title": "Apple launches new product",
                "summary": "summary",
                "url": "https://example.com/a",
                "source": "Example",
                "time_published": "20240105T143000",
                "ticker_sentiment": [{"ticker": "AAPL"}],
            },
            {
                "title": "Other",
                "url": "https://example.com/b",
                "time_published": "20240105T143000",
                "ticker_sentiment": [{"ticker": "MSFT"}],
            },
        ]
    }

    articles = parse_alpha_vantage_news(
        payload,
        ticker="AAPL",
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2024, 1, 31, tzinfo=timezone.utc),
    )

    assert len(articles) == 1
    assert articles[0].provider == "alpha_vantage"
    assert articles[0].headline == "Apple launches new product"


def test_alpha_vantage_quota_response() -> None:
    with pytest.raises(ProviderQuotaError):
        parse_alpha_vantage_news(
            {"Note": "Thank you for using Alpha Vantage! Our standard API call frequency is 5 calls per minute."},
            ticker="AAPL",
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 1, 31, tzinfo=timezone.utc),
        )


def test_provider_selection_and_secret_not_in_repr(test_settings: Settings) -> None:
    settings = Settings(
        **{
            **test_settings.__dict__,
            "market_data_provider": "twelve_data",
            "twelve_data_api_key": "secret-twelve",
            "historical_news_provider": "alpha_vantage",
            "alpha_vantage_api_key": "secret-alpha",
        }
    )

    market_provider = get_market_data_provider(settings)
    news_provider = get_news_provider(settings, historical=True)

    assert market_provider.name == "twelve_data"
    assert news_provider.name == "alpha_vantage"
    assert "secret-twelve" not in repr(market_provider)
    assert "secret-alpha" not in repr(news_provider)


class RecordingProvider:
    name = "recording"

    def __init__(self) -> None:
        self.calls: list[tuple[date, date]] = []

    def fetch_daily_history(self, ticker: str, start_date: date, end_date: date) -> list[DailyPrice]:
        self.calls.append((start_date, end_date))
        return [
            DailyPrice(date=start_date, open=10, high=11, low=9, close=10, adjusted_close=10, volume=100),
            DailyPrice(date=end_date, open=10, high=12, low=9, close=11, adjusted_close=11, volume=200),
        ]


def test_incremental_refresh_uses_local_cache_overlap(db_session) -> None:
    create_stock(db_session, StockCreate(ticker="AAPL"))
    provider = RecordingProvider()

    refresh_history(db_session, provider, "AAPL", years=1, end_date=date(2024, 12, 31))
    refresh_history(db_session, provider, "AAPL", years=1, end_date=date(2025, 1, 10))

    assert provider.calls[1][0] == date(2024, 12, 24)

