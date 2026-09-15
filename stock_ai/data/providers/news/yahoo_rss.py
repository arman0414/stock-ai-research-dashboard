from __future__ import annotations

import hashlib
import ssl
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from stock_ai.data.providers.news.base import NormalizedArticle
from stock_ai.schemas.stocks import normalize_ticker


class YahooRssNewsProvider:
    """Free no-key provider useful for live/dev news, not historical ML coverage."""

    name = "yahoo_rss"
    supports_historical = False
    base_url = "https://feeds.finance.yahoo.com/rss/2.0/headline"

    def fetch_news(self, ticker: str, start_date: datetime, end_date: datetime) -> list[NormalizedArticle]:
        normalized_ticker = normalize_ticker(ticker)
        params = urlencode({"s": normalized_ticker, "region": "US", "lang": "en-US"})
        request = Request(f"{self.base_url}?{params}", headers={"User-Agent": "stock-ai-dashboard/0.1"})

        with _open_url(request) as response:
            payload = response.read().decode("utf-8")

        return self.parse_feed(payload, normalized_ticker, start_date, end_date)

    def parse_feed(self, payload: str, ticker: str, start_date: datetime, end_date: datetime) -> list[NormalizedArticle]:
        root = ET.fromstring(payload)
        articles: list[NormalizedArticle] = []
        for item in root.findall(".//item"):
            headline = _text(item, "title")
            url = _text(item, "link")
            if not headline or not url:
                continue

            published_at = _parse_datetime(_text(item, "pubDate"))
            if not published_at or published_at < start_date or published_at > end_date:
                continue

            source = _text(item, "source") or "Yahoo Finance"
            summary = _text(item, "description")
            external_id = _text(item, "guid") or hashlib.sha256(url.encode("utf-8")).hexdigest()
            articles.append(
                NormalizedArticle(
                    ticker=ticker,
                    headline=headline.strip(),
                    summary=summary.strip() if summary else None,
                    source=source.strip() if source else None,
                    published_at=published_at,
                    url=url.strip(),
                    provider=self.name,
                    external_id=external_id.strip(),
                )
            )
        return sorted(articles, key=lambda article: article.published_at)


def _text(item: ET.Element, tag: str) -> str | None:
    child = item.find(tag)
    return child.text if child is not None else None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = parsedate_to_datetime(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


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
