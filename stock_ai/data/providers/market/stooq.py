from __future__ import annotations

import csv
import io
import ssl
from datetime import date, datetime
from decimal import Decimal
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from stock_ai.data.providers.errors import ProviderError
from stock_ai.data.providers.market.base import DailyPrice, Quote
from stock_ai.schemas.stocks import normalize_ticker


class StooqMarketDataProvider:
    name = "stooq"
    base_url = "https://stooq.com/q/d/l/"

    def fetch_daily_history(self, ticker: str, start_date: date, end_date: date) -> list[DailyPrice]:
        symbol = self._to_stooq_symbol(normalize_ticker(ticker))
        params = urlencode(
            {
                "s": symbol,
                "d1": start_date.strftime("%Y%m%d"),
                "d2": end_date.strftime("%Y%m%d"),
                "i": "d",
            }
        )
        request = Request(
            f"{self.base_url}?{params}",
            headers={"User-Agent": "stock-ai-dashboard/0.1"},
        )

        with _open_url(request) as response:
            payload = response.read().decode("utf-8")

        return self._parse_csv(payload, ticker=normalize_ticker(ticker), start_date=start_date, end_date=end_date)

    def fetch_quotes(self, tickers: list[str]) -> dict[str, Quote]:
        """Stooq's free endpoint has no reliable live-quote/batch API -- the
        quote service falls back to the latest stored PriceBar for every
        ticker when this raises, exactly like any other provider failure."""
        raise ProviderError("stooq does not support live quotes")

    def _parse_csv(self, payload: str, ticker: str, start_date: date, end_date: date) -> list[DailyPrice]:
        reader = csv.DictReader(io.StringIO(payload))
        bars: list[DailyPrice] = []

        for row in reader:
            if not row or row.get("Date") in {None, "No data"}:
                continue

            bar_date = datetime.strptime(row["Date"], "%Y-%m-%d").date()
            if bar_date < start_date or bar_date > end_date:
                continue

            close = Decimal(row["Close"])
            bars.append(
                DailyPrice(
                    date=bar_date,
                    open=Decimal(row["Open"]),
                    high=Decimal(row["High"]),
                    low=Decimal(row["Low"]),
                    close=close,
                    adjusted_close=close,
                    volume=int(row["Volume"]),
                )
            )

        if not bars:
            raise ValueError(f"No historical data returned for {ticker}")

        return sorted(bars, key=lambda bar: bar.date)

    def _to_stooq_symbol(self, ticker: str) -> str:
        normalized = ticker.lower()
        if "." in normalized:
            return normalized
        return f"{normalized}.us"


def _open_url(request: Request):
    try:
        import certifi

        context = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        context = ssl.create_default_context()
    try:
        return urlopen(request, timeout=20, context=context)
    except URLError as exc:
        if "CERTIFICATE_VERIFY_FAILED" not in str(exc):
            raise
        return urlopen(request, timeout=20, context=ssl._create_unverified_context())
