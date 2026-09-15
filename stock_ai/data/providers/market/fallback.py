from __future__ import annotations

from datetime import date

from stock_ai.data.providers.errors import ProviderError
from stock_ai.data.providers.market.base import DailyPrice, MarketDataProvider


class FallbackMarketDataProvider:
    """Try providers in order; one successful provider supplies the whole request."""

    def __init__(self, providers: list[MarketDataProvider]) -> None:
        self.providers = providers
        self._last_provider_name = providers[0].name if providers else "fallback"

    @property
    def name(self) -> str:
        return self._last_provider_name

    def fetch_daily_history(self, ticker: str, start_date: date, end_date: date) -> list[DailyPrice]:
        errors: dict[str, str] = {}
        for provider in self.providers:
            try:
                bars = provider.fetch_daily_history(ticker, start_date, end_date)
                self._last_provider_name = provider.name
                return bars
            except Exception as exc:
                errors[provider.name] = str(exc)
        raise ProviderError(f"All market data providers failed for {ticker}: {errors}")

