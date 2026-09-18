from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request

from stock_ai.data.providers.errors import ProviderConfigurationError, ProviderError, ProviderQuotaError
from stock_ai.data.providers.http import fetch_json_with_retries
from stock_ai.data.providers.news.base import NormalizedArticle
from stock_ai.schemas.stocks import normalize_ticker


class FinnhubNewsProvider:
    name = "finnhub"
    supports_historical = False
    base_url = "https://finnhub.io/api/v1/company-news"

    def __init__(self, api_key: str | None) -> None:
        if not api_key:
            raise ProviderConfigurationError("FINNHUB_API_KEY is required to enable Finnhub news")
        self.api_key = api_key

    def fetch_news(self, ticker: str, start_date: datetime, end_date: datetime) -> list[NormalizedArticle]:
        symbol = normalize_ticker(ticker)
        params = urlencode(
            {
                "symbol": symbol,
                "from": start_date.date().isoformat(),
                "to": end_date.date().isoformat(),
                "token": self.api_key,
            }
        )
        request = Request(f"{self.base_url}?{params}", headers={"User-Agent": "stock-ai-dashboard/0.1"})
        payload = fetch_json_with_retries(request, max_retries=1, backoff_seconds=1.0)
        return parse_finnhub_company_news(payload, ticker=symbol, start_date=start_date, end_date=end_date)


def parse_finnhub_company_news(payload: object, ticker: str, start_date: datetime, end_date: datetime) -> list[NormalizedArticle]:
    if isinstance(payload, dict):
        message = str(payload.get("error") or payload.get("msg") or payload.get("message") or payload)
        lower = message.lower()
        if "limit" in lower or "quota" in lower or "too many" in lower:
            raise ProviderQuotaError(message)
        raise ProviderError(message)
    if not isinstance(payload, list):
        raise ProviderError("Finnhub response was not a list")

    articles: list[NormalizedArticle] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        headline = row.get("headline")
        url = row.get("url")
        published_at = _parse_finnhub_time(row.get("datetime"))
        if not headline or not url or published_at is None:
            continue
        if published_at < start_date or published_at > end_date:
            continue

        external_id = str(row.get("id") or "").strip()
        if not external_id:
            external_id = hashlib.sha256(f"{url}|{published_at.isoformat()}".encode("utf-8")).hexdigest()

        articles.append(
            NormalizedArticle(
                ticker=ticker,
                headline=str(headline).strip(),
                summary=(str(row.get("summary") or "").strip() or None),
                source=(str(row.get("source") or "").strip() or None),
                published_at=published_at,
                url=str(url).strip(),
                provider="finnhub",
                external_id=external_id,
                provider_sources=("finnhub",),
            )
        )
    return sorted(articles, key=lambda article: article.published_at)


def _parse_finnhub_time(value: object) -> datetime | None:
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)
