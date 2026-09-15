from __future__ import annotations

from stock_ai.config import Settings, get_settings
from stock_ai.data.providers.news.alpha_vantage import AlphaVantageNewsProvider
from stock_ai.data.providers.news.base import NewsProvider
from stock_ai.data.providers.news.yahoo_rss import YahooRssNewsProvider


def get_news_provider(settings: Settings | None = None, historical: bool = False) -> NewsProvider:
    settings = settings or get_settings()
    provider_name = settings.historical_news_provider if historical else settings.news_provider
    if provider_name == "yahoo_rss":
        return YahooRssNewsProvider()
    if provider_name == "alpha_vantage":
        return AlphaVantageNewsProvider(settings.alpha_vantage_api_key or settings.news_api_key)
    raise ValueError(f"Unsupported news provider: {provider_name}")
