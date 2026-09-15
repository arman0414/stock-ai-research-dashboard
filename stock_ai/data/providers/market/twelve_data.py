from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from urllib.parse import urlencode
from urllib.request import Request

from stock_ai.data.providers.errors import ProviderConfigurationError, ProviderError, ProviderQuotaError, ProviderRateLimitError
from stock_ai.data.providers.http import detect_quota_message, fetch_json_with_retries
from stock_ai.data.providers.market.base import DailyPrice, Quote
from stock_ai.schemas.stocks import normalize_ticker


class TwelveDataMarketDataProvider:
    name = "twelve_data"
    base_url = "https://api.twelvedata.com/time_series"
    quote_url = "https://api.twelvedata.com/quote"

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

    def fetch_quotes(self, tickers: list[str]) -> dict[str, Quote]:
        """Twelve Data's /quote endpoint supports a comma-separated `symbol`
        list in ONE request -- this is the batching the daily cycle and the
        dashboard/forecast pages rely on to avoid one provider call per
        ticker. A single-symbol request returns a flat object; multi-symbol
        returns an object keyed by symbol -- both are handled below."""
        symbols = [normalize_ticker(t) for t in tickers]
        if not symbols:
            return {}
        params = urlencode({"symbol": ",".join(symbols), "apikey": self.api_key})
        request = Request(f"{self.quote_url}?{params}", headers={"User-Agent": "stock-ai-dashboard/0.1"})
        payload = fetch_json_with_retries(request)
        return parse_twelve_data_quotes(payload, tickers=symbols)


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


def parse_twelve_data_quotes(payload: dict, tickers: list[str]) -> dict[str, Quote]:
    """Parses either response shape /quote can return. A per-symbol error
    inside a batch (e.g. one bad ticker) is skipped rather than raised, so
    one bad symbol never takes down quotes for the rest of the batch -- the
    quote service falls back to the last stored price for whichever tickers
    are missing from the returned dict. A account-level quota/rate-limit
    message is raised immediately since no symbol in the batch can succeed."""
    detect_quota_message(payload)

    if "symbol" in payload:
        # Single-symbol requests return one flat object, not keyed by symbol.
        entries = {tickers[0]: payload} if tickers else {}
    else:
        entries = payload

    quotes: dict[str, Quote] = {}
    for ticker in tickers:
        entry = entries.get(ticker)
        if not isinstance(entry, dict):
            continue
        if str(entry.get("status", "")).lower() == "error":
            continue
        try:
            price = Decimal(str(entry["close"]))
            timestamp_raw = entry.get("timestamp")
            quote_timestamp = datetime.fromtimestamp(int(timestamp_raw), tz=timezone.utc) if timestamp_raw is not None else datetime.now(timezone.utc)
            is_open = entry.get("is_market_open")
            market_status = "OPEN" if is_open is True else "CLOSED" if is_open is False else "UNKNOWN"
        except (KeyError, ValueError, ArithmeticError, TypeError, OSError):
            continue
        quotes[ticker] = Quote(ticker=ticker, price=price, quote_timestamp=quote_timestamp, market_status=market_status, provider="twelve_data")
    return quotes


def _validate_bar(ticker: str, bar_date: date, open_: Decimal, high: Decimal, low: Decimal, close: Decimal, volume: int) -> None:
    if min(open_, high, low, close) <= 0:
        raise ProviderError(f"Non-positive OHLC value for {ticker} on {bar_date}")
    if volume < 0:
        raise ProviderError(f"Negative volume for {ticker} on {bar_date}")
    if high < low or high < open_ or high < close or low > open_ or low > close:
        raise ProviderError(f"Inconsistent OHLC range for {ticker} on {bar_date}")

