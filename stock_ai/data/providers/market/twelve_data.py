from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from urllib.parse import urlencode
from urllib.request import Request

from stock_ai.data.providers.errors import ProviderConfigurationError, ProviderError, ProviderQuotaError, ProviderRateLimitError
from stock_ai.data.providers.http import detect_quota_message, fetch_json_with_retries
from stock_ai.data.providers.market.base import DailyPrice
from stock_ai.schemas.stocks import normalize_ticker


class TwelveDataMarketDataProvider:
    name = "twelve_data"
    base_url = "https://api.twelvedata.com/time_series"

    def __init__(self, api_key: str | None) -> None:
        if not api_key:
            raise ProviderConfigurationError("TWELVE_DATA_API_KEY is required when MARKET_DATA_PROVIDER=twelve_data")
        self.api_key = api_key

    def fetch_daily_history(self, ticker: str, start_date: date, end_date: date) -> list[DailyPrice]:
        symbol = normalize_ticker(ticker)
        params = urlencode(
            {
                "symbol": symbol,
                "interval": "1day",
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "outputsize": 5000,
                "apikey": self.api_key,
            }
        )
        request = Request(f"{self.base_url}?{params}", headers={"User-Agent": "stock-ai-dashboard/0.1"})
        payload = fetch_json_with_retries(request)
        return parse_twelve_data_response(payload, ticker=symbol, start_date=start_date, end_date=end_date)


def parse_twelve_data_response(payload: dict, ticker: str, start_date: date, end_date: date) -> list[DailyPrice]:
    detect_quota_message(payload)
    status = str(payload.get("status", "")).lower()
    if status == "error":
        message = str(payload.get("message", "Twelve Data error"))
        if "limit" in message.lower() or "quota" in message.lower():
            raise ProviderQuotaError(message)
        raise ProviderError(message)
    values = payload.get("values")
    if not isinstance(values, list) or not values:
        raise ProviderError(f"No historical data returned for {ticker}")

    bars: dict[date, DailyPrice] = {}
    for row in values:
        try:
            bar_date = datetime.strptime(str(row["datetime"])[:10], "%Y-%m-%d").date()
            if bar_date < start_date or bar_date > end_date:
                continue
            open_ = Decimal(str(row["open"]))
            high = Decimal(str(row["high"]))
            low = Decimal(str(row["low"]))
            close = Decimal(str(row["close"]))
            volume = int(Decimal(str(row.get("volume", 0))))
        except (KeyError, ValueError, ArithmeticError) as exc:
            raise ProviderError(f"Malformed Twelve Data OHLCV row for {ticker}") from exc

        _validate_bar(ticker, bar_date, open_, high, low, close, volume)
        bars[bar_date] = DailyPrice(
            date=bar_date,
            open=open_,
            high=high,
            low=low,
            close=close,
            adjusted_close=close,
            volume=volume,
        )

    if not bars:
        raise ProviderError(f"No historical data returned for {ticker}")
    return [bars[day] for day in sorted(bars)]


def _validate_bar(ticker: str, bar_date: date, open_: Decimal, high: Decimal, low: Decimal, close: Decimal, volume: int) -> None:
    if min(open_, high, low, close) <= 0:
        raise ProviderError(f"Non-positive OHLC value for {ticker} on {bar_date}")
    if volume < 0:
        raise ProviderError(f"Negative volume for {ticker} on {bar_date}")
    if high < low or high < open_ or high < close or low > open_ or low > close:
        raise ProviderError(f"Inconsistent OHLC range for {ticker} on {bar_date}")

