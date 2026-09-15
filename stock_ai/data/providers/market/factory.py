from __future__ import annotations

from stock_ai.config import Settings, get_settings
from stock_ai.data.providers.errors import ProviderConfigurationError
from stock_ai.data.providers.market.base import MarketDataProvider
from stock_ai.data.providers.market.fallback import FallbackMarketDataProvider
from stock_ai.data.providers.market.stooq import StooqMarketDataProvider
from stock_ai.data.providers.market.twelve_data import TwelveDataMarketDataProvider


def get_market_data_provider(settings: Settings | None = None) -> MarketDataProvider:
    settings = settings or get_settings()

    if settings.market_data_provider == "stooq":
        return StooqMarketDataProvider()
    if settings.market_data_provider == "twelve_data":
        return TwelveDataMarketDataProvider(settings.twelve_data_api_key or settings.market_data_api_key)
    if settings.market_data_provider == "twelve_data_fallback":
        providers: list[MarketDataProvider] = []
        try:
            providers.append(TwelveDataMarketDataProvider(settings.twelve_data_api_key or settings.market_data_api_key))
        except ProviderConfigurationError:
            pass
        providers.append(StooqMarketDataProvider())
        return FallbackMarketDataProvider(providers)

    raise ValueError(f"Unsupported market data provider: {settings.market_data_provider}")
