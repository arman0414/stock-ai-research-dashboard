from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class NormalizedArticle:
    ticker: str
    headline: str
    summary: str | None
    source: str | None
    published_at: datetime
    url: str
    provider: str
    external_id: str


class NewsProvider(Protocol):
    name: str
    supports_historical: bool

    def fetch_news(self, ticker: str, start_date: datetime, end_date: datetime) -> list[NormalizedArticle]:
        """Return normalized articles for a ticker and date range."""

