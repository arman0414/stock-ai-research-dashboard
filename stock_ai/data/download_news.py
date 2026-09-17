from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from stock_ai.config import get_settings
from stock_ai.data.providers.errors import ProviderQuotaError
from stock_ai.data.providers.news import get_news_provider
from stock_ai.db.session import get_session_factory, init_db
from stock_ai.ml.benchmark import DEFAULT_BENCHMARK_UNIVERSE
from stock_ai.models.news import NewsArticle
from stock_ai.news.services import refresh_news
from stock_ai.utils.json_safe import dumps_json


DEFAULT_NEWS_SMOKE = ["AAPL", "NVDA", "TSLA", "MSFT", "AMZN"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Download/cache historical financial news.")
    parser.add_argument("--tickers", nargs="*", default=DEFAULT_NEWS_SMOKE)
    parser.add_argument("--days", type=int, default=365)
    args = parser.parse_args()

    settings = get_settings()
    if settings.historical_news_provider != "alpha_vantage":
        raise SystemExit(
            "Historical news downloads should use Alpha Vantage.\n"
            "Create a free Alpha Vantage account and set this in /Users/armanmalik/Desktop/stocks/.env:\n"
            "HISTORICAL_NEWS_PROVIDER=alpha_vantage\n"
            "ALPHA_VANTAGE_API_KEY=your_key_here"
        )
    if not settings.alpha_vantage_api_key and not settings.news_api_key:
        raise SystemExit(
            "Missing Alpha Vantage API key.\n"
            "Create a free Alpha Vantage account and set this in /Users/armanmalik/Desktop/stocks/.env:\n"
            "HISTORICAL_NEWS_PROVIDER=alpha_vantage\n"
            "ALPHA_VANTAGE_API_KEY=your_key_here"
        )

    init_db()
    provider = get_news_provider(settings, historical=True)
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=args.days)
    session_factory = get_session_factory(settings)
    report = {"provider": provider.name, "tickers": {}, "failed": {}}

    with session_factory() as db:
        for ticker in args.tickers:
            try:
                result = refresh_news(db, provider, ticker, start, end)
                report["tickers"][ticker] = {**result, **_article_summary(db, ticker)}
            except ProviderQuotaError as exc:
                db.rollback()
                report["failed"][ticker] = f"quota/rate limit reached: {exc}"
                break
            except Exception as exc:
                db.rollback()
                report["failed"][ticker] = str(exc)

    print(dumps_json(report, indent=2, sort_keys=True))


def _article_summary(db, ticker: str) -> dict:
    count, earliest, latest = db.execute(
        select(func.count(), func.min(NewsArticle.published_at), func.max(NewsArticle.published_at)).where(NewsArticle.ticker == ticker)
    ).one()
    return {
        "stored_articles": int(count or 0),
        "earliest_article": earliest,
        "latest_article": latest,
    }


if __name__ == "__main__":
    main()
