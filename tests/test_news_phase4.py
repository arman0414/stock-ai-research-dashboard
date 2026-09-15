from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pandas as pd

from stock_ai.data.providers.news.base import NormalizedArticle
from stock_ai.data.providers.news.yahoo_rss import YahooRssNewsProvider
from stock_ai.features.dataset import build_feature_dataset
from stock_ai.features.news_features import add_news_features, news_coverage
from stock_ai.models.news import NewsArticle
from stock_ai.news.events import categorize_event
from stock_ai.news.sentiment import SentimentResult, parse_finbert_output
from stock_ai.news.services import persist_sentiment, upsert_articles
from stock_ai.news.timing import eligible_prediction_date


def article(ticker: str = "AAPL", published_at: datetime | None = None, headline: str = "Apple raises guidance") -> NormalizedArticle:
    published_at = published_at or datetime(2024, 1, 5, 15, 0, tzinfo=timezone.utc)
    return NormalizedArticle(
        ticker=ticker,
        headline=headline,
        summary="Company wins contract and raises outlook",
        source="Test",
        published_at=published_at,
        url=f"https://example.com/{headline.replace(' ', '-')}",
        provider="test",
        external_id=headline,
    )


def test_yahoo_rss_article_normalization() -> None:
    payload = """<?xml version="1.0"?><rss><channel>
    <item><title>Apple wins contract</title><link>https://example.com/a</link><pubDate>Fri, 05 Jan 2024 15:00:00 GMT</pubDate><source>Example</source><guid>a-1</guid><description>Summary</description></item>
    </channel></rss>"""
    provider = YahooRssNewsProvider()

    articles = provider.parse_feed(payload, "AAPL", datetime(2024, 1, 1, tzinfo=timezone.utc), datetime(2024, 1, 10, tzinfo=timezone.utc))

    assert len(articles) == 1
    assert articles[0].ticker == "AAPL"
    assert articles[0].headline == "Apple wins contract"
    assert articles[0].external_id == "a-1"


def test_news_duplicate_handling_and_event_categorization(db_session) -> None:
    stored, created = upsert_articles(db_session, [article(), article()])

    assert created == 1
    assert len(stored) == 2
    assert db_session.query(NewsArticle).count() == 1
    assert stored[0].event_category == "GUIDANCE_RAISED"
    assert categorize_event("Analyst downgraded by major bank") == "ANALYST_DOWNGRADE"
    assert categorize_event("Company announces regular update") == "GENERAL_NEWS"


def test_finbert_result_parsing_and_sentiment_score(db_session) -> None:
    stored, _ = upsert_articles(db_session, [article()])
    raw = [
        {"label": "positive", "score": 0.8},
        {"label": "neutral", "score": 0.15},
        {"label": "negative", "score": 0.05},
    ]
    result = parse_finbert_output(raw)
    persist_sentiment(db_session, stored[0], result)
    db_session.commit()

    assert result.label == "POSITIVE"
    assert result.sentiment_score == 0.75
    assert float(stored[0].sentiment.sentiment_score) == 0.75


def test_after_market_close_maps_to_next_business_day() -> None:
    after_close = datetime(2024, 1, 5, 22, 0, tzinfo=timezone.utc)

    assert eligible_prediction_date(after_close).isoformat() == "2024-01-08"


def test_news_features_are_backward_looking_and_handle_no_news() -> None:
    prices = pd.DataFrame(
        {
            "date": pd.bdate_range("2024-01-02", periods=40),
            "ticker": "AAPL",
            "open": range(40),
            "high": range(1, 41),
            "low": range(40),
            "close": range(1, 41),
            "adjusted_close": range(1, 41),
            "volume": [1_000_000] * 40,
        }
    )
    dataset = build_feature_dataset(prices, include_targets=False)
    news = pd.DataFrame(
        [
            {
                "ticker": "AAPL",
                "eligible_date": pd.Timestamp("2024-01-10"),
                "sentiment_label": "POSITIVE",
                "positive_probability": 0.9,
                "neutral_probability": 0.05,
                "negative_probability": 0.05,
                "sentiment_score": 0.85,
                "event_category": "NEW_CONTRACT",
            }
        ]
    )

    no_news = add_news_features(dataset, None)
    with_news = add_news_features(dataset, news)

    assert no_news["news_count_7d"].sum() == 0
    assert with_news.loc[with_news["date"] < pd.Timestamp("2024-01-10"), "news_count_7d"].sum() == 0
    assert with_news.loc[with_news["date"] == pd.Timestamp("2024-01-10"), "news_count_7d"].iloc[0] == 1
    assert with_news.loc[with_news["date"] == pd.Timestamp("2024-01-10"), "contract_count_30d"].iloc[0] == 1
    assert news_coverage(with_news)["coverage_7d"] > 0

