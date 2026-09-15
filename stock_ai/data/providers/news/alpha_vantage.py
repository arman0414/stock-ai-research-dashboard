from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request

from stock_ai.data.providers.errors import ProviderConfigurationError, ProviderError, ProviderQuotaError
from stock_ai.data.providers.http import detect_quota_message, fetch_json_with_retries
from stock_ai.data.providers.news.base import NormalizedArticle
from stock_ai.schemas.stocks import normalize_ticker


class AlphaVantageNewsProvider:
    name = "alpha_vantage"
    supports_historical = True
    base_url = "https://www.alphavantage.co/query"

    def __init__(self, api_key: str | None) -> None:
        if not api_key:
            raise ProviderConfigurationError("ALPHA_VANTAGE_API_KEY is required when HISTORICAL_NEWS_PROVIDER=alpha_vantage")
        self.api_key = api_key

    def fetch_news(self, ticker: str, start_date: datetime, end_date: datetime) -> list[NormalizedArticle]:
        symbol = normalize_ticker(ticker)
        params = urlencode(
            {
                "function": "NEWS_SENTIMENT",
                "tickers": symbol,
                "time_from": start_date.strftime("%Y%m%dT%H%M"),
                "time_to": end_date.strftime("%Y%m%dT%H%M"),
                "limit": 1000,
                "apikey": self.api_key,
            }
        )
        request = Request(f"{self.base_url}?{params}", headers={"User-Agent": "stock-ai-dashboard/0.1"})
        payload = fetch_json_with_retries(request)
        return parse_alpha_vantage_news(payload, ticker=symbol, start_date=start_date, end_date=end_date)


def parse_alpha_vantage_news(payload: dict, ticker: str, start_date: datetime, end_date: datetime) -> list[NormalizedArticle]:
    detect_quota_message(payload)
    if "Error Message" in payload:
        raise ProviderError(str(payload["Error Message"]))
    if "Note" in payload or "Information" in payload:
        raise ProviderQuotaError(str(payload.get("Note") or payload.get("Information")))
    feed = payload.get("feed")
    if not isinstance(feed, list):
        raise ProviderError("Alpha Vantage response missing feed")

    articles: list[NormalizedArticle] = []
    for row in feed:
        headline = row.get("title")
        url = row.get("url")
        published_at = _parse_alpha_time(row.get("time_published"))
        if not headline or not url or published_at is None:
            continue
        if published_at < start_date or published_at > end_date:
            continue
        if not _mentions_ticker(row, ticker):
            continue
        external_id = hashlib.sha256(f"{url}|{row.get('time_published', '')}".encode("utf-8")).hexdigest()
        articles.append(
            NormalizedArticle(
                ticker=ticker,
                headline=headline.strip(),
                summary=(row.get("summary") or "").strip() or None,
                source=(row.get("source") or "").strip() or None,
                published_at=published_at,
                url=url.strip(),
                provider="alpha_vantage",
                external_id=external_id,
            )
        )
    return sorted(articles, key=lambda article: article.published_at)


def _parse_alpha_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.strptime(value[:13], "%Y%m%dT%H%M").replace(tzinfo=timezone.utc)


def _mentions_ticker(row: dict, ticker: str) -> bool:
    ticker_sentiment = row.get("ticker_sentiment") or []
    for item in ticker_sentiment:
        if str(item.get("ticker", "")).upper() == ticker:
            return True
    return True if not ticker_sentiment else False

