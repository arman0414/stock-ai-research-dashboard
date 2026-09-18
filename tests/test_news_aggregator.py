from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from stock_ai.config import Settings
from stock_ai.data.providers.errors import ProviderError
from stock_ai.data.providers.news.base import NormalizedArticle
from stock_ai.data.providers.news.finnhub import parse_finnhub_company_news
from stock_ai.models.news import NewsArticle
from stock_ai.news.aggregator import build_current_news_providers, refresh_current_news
from stock_ai.news.dedupe import deduplicate_articles
from stock_ai.news.sentiment import SentimentResult
from stock_ai.news.services import persist_sentiment, sentiment_summary, upsert_articles


NOW = datetime(2026, 9, 17, 20, 0, tzinfo=timezone.utc)


class FakeProvider:
    supports_historical = False

    def __init__(self, name: str, articles: list[NormalizedArticle] | None = None, error: Exception | None = None) -> None:
        self.name = name
        self.articles = articles or []
        self.error = error
        self.calls: list[tuple[str, datetime, datetime]] = []

    def fetch_news(self, ticker: str, start_date: datetime, end_date: datetime) -> list[NormalizedArticle]:
        self.calls.append((ticker, start_date, end_date))
        if self.error:
            raise self.error
        return self.articles


class FakeAnalyzer:
    def __init__(self) -> None:
        self.text_batches: list[list[str]] = []

    def analyze(self, texts: list[str]) -> list[SentimentResult]:
        self.text_batches.append(texts)
        return [
            SentimentResult(
                label="POSITIVE",
                positive_probability=0.8,
                neutral_probability=0.1,
                negative_probability=0.1,
                sentiment_score=0.7,
                model_name="fake-finbert",
                model_version="test",
                analyzed_at=NOW,
            )
            for _text in texts
        ]


def make_article(
    provider: str,
    headline: str = "Nvidia launches new AI chip",
    url: str = "https://example.com/nvidia-ai-chip?utm_source=yahoo",
    published_at: datetime = NOW,
    source: str = "Reuters",
) -> NormalizedArticle:
    return NormalizedArticle(
        ticker="NVDA",
        headline=headline,
        summary="Nvidia announced a new AI infrastructure product.",
        source=source,
        published_at=published_at,
        url=url,
        provider=provider,
        external_id=f"{provider}-{headline}",
        provider_sources=(provider,),
    )


def test_finnhub_response_normalization() -> None:
    payload = [
        {
            "id": 123,
            "datetime": int(NOW.timestamp()),
            "headline": "Nvidia expands AI infrastructure partnership",
            "summary": "Partnership summary",
            "source": "Reuters",
            "url": "https://example.com/nvda",
        }
    ]

    articles = parse_finnhub_company_news(payload, "NVDA", NOW - timedelta(days=1), NOW + timedelta(minutes=1))

    assert len(articles) == 1
    assert articles[0].ticker == "NVDA"
    assert articles[0].provider == "finnhub"
    assert articles[0].external_id == "123"
    assert articles[0].source == "Reuters"


def test_missing_finnhub_key_marks_provider_unavailable(test_settings: Settings) -> None:
    _providers, statuses = build_current_news_providers(test_settings)

    finnhub = next(status for status in statuses if status.provider == "finnhub")
    assert finnhub.available is False
    assert finnhub.status == "missing_api_key"


def test_yahoo_failure_while_finnhub_succeeds(db_session) -> None:
    yahoo = FakeProvider("yahoo_rss", error=ProviderError("rss unavailable"))
    finnhub = FakeProvider("finnhub", [make_article("finnhub")])

    result = refresh_current_news(db_session, "NVDA", providers=[yahoo, finnhub], end_time=NOW, force=True)

    assert result.articles_received == 1
    assert result.unique_articles == 1
    assert result.articles_created == 1
    assert {status.status for status in result.provider_results} == {"failed", "ok"}
    assert db_session.query(NewsArticle).count() == 1


def test_finnhub_failure_while_yahoo_succeeds(db_session) -> None:
    yahoo = FakeProvider("yahoo_rss", [make_article("yahoo_rss")])
    finnhub = FakeProvider("finnhub", error=ProviderError("finnhub unavailable"))

    result = refresh_current_news(db_session, "NVDA", providers=[yahoo, finnhub], end_time=NOW, force=True)

    assert result.articles_received == 1
    assert result.unique_articles == 1
    assert result.articles_created == 1
    assert {status.provider: status.status for status in result.provider_results}["finnhub"] == "failed"


def test_all_providers_partially_succeed(db_session) -> None:
    providers = [
        FakeProvider("yahoo_rss", [make_article("yahoo_rss", url="https://example.com/one")]),
        FakeProvider("finnhub", [make_article("finnhub", headline="AMD raises AI forecast", url="https://example.com/two")]),
        FakeProvider("alpha_vantage", error=ProviderError("quota")),
    ]

    result = refresh_current_news(db_session, "NVDA", providers=providers, end_time=NOW, force=True)

    assert result.articles_received == 2
    assert result.unique_articles == 2
    assert result.articles_created == 2
    assert [status.status for status in result.provider_results].count("ok") == 2
    assert [status.status for status in result.provider_results].count("failed") == 1


def test_duplicate_url_removal() -> None:
    first = make_article("yahoo_rss", url="https://example.com/story?utm_campaign=x")
    second = make_article("finnhub", url="https://example.com/story")

    unique = deduplicate_articles([first, second])

    assert len(unique) == 1
    assert set(unique[0].provider_sources) == {"yahoo_rss", "finnhub"}


def test_duplicate_normalized_headline_removal() -> None:
    first = make_article("yahoo_rss", headline="Nvidia launches new AI chip - Reuters", url="https://example.com/a")
    second = make_article("finnhub", headline="Nvidia launches new AI chip", url="https://example.com/b")

    unique = deduplicate_articles([first, second])

    assert len(unique) == 1
    assert set(unique[0].provider_sources) == {"yahoo_rss", "finnhub"}


def test_duplicate_article_does_not_run_finbert_twice(db_session) -> None:
    analyzer = FakeAnalyzer()
    providers = [
        FakeProvider("yahoo_rss", [make_article("yahoo_rss", url="https://example.com/story?utm_medium=rss")]),
        FakeProvider("finnhub", [make_article("finnhub", url="https://example.com/story")]),
    ]

    result = refresh_current_news(db_session, "NVDA", providers=providers, end_time=NOW, force=True, analyze_sentiment=True, analyzer=analyzer)

    assert result.unique_articles == 1
    assert result.articles_analyzed == 1
    assert [len(batch) for batch in analyzer.text_batches] == [1]


def test_news_mood_counts_recent_unique_articles_only(db_session) -> None:
    stored, created = upsert_articles(
        db_session,
        [
            make_article("yahoo_rss", headline="Positive recent", url="https://example.com/positive", published_at=NOW - timedelta(hours=4)),
            make_article("yahoo_rss", headline="Old historical", url="https://example.com/old", published_at=NOW - timedelta(days=20)),
        ],
    )
    assert created == 2
    assert len(stored) == 2
    articles = list(db_session.scalars(select(NewsArticle).order_by(NewsArticle.published_at.desc())))
    persist_sentiment(db_session, articles[0], FakeAnalyzer().analyze(["recent"])[0])
    persist_sentiment(db_session, articles[1], FakeAnalyzer().analyze(["old"])[0])
    db_session.commit()

    summary = sentiment_summary(db_session, "NVDA", window_hours=72, as_of=NOW)

    assert summary["articles_7d"] == 1
    assert summary["positive"] == 1
