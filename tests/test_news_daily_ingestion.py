"""Daily multi-provider news ingestion + relevance filtering.

Every provider here is a fake: these tests never touch a real network, and
never consume Finnhub / Yahoo / Alpha Vantage quota.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from stock_ai.data.providers.errors import ProviderQuotaError, ProviderRateLimitError
from stock_ai.data.providers.news.base import NormalizedArticle
from stock_ai.models.news import NewsArticle
from stock_ai.news.aggregator import (
    DEFAULT_DAILY_WINDOW_HOURS,
    INCREMENTAL_OVERLAP_HOURS,
    MAX_INCREMENTAL_LOOKBACK_HOURS,
    incremental_start_time,
    refresh_current_news,
    refresh_tracked_news,
)
from stock_ai.news.relevance import NOT_RELEVANT, RELEVANT, UNCERTAIN, classify_relevance
from stock_ai.news.sentiment import SentimentResult
from stock_ai.news.services import article_provider_sources, reclassify_relevance, sentiment_summary, upsert_articles

NOW = datetime(2026, 9, 18, 20, 0, tzinfo=timezone.utc)


class FakeProvider:
    supports_historical = False

    def __init__(self, name, articles=None, error=None):
        self.name = name
        self.articles = articles or []
        self.error = error
        self.calls: list[tuple[str, datetime, datetime]] = []

    def fetch_news(self, ticker, start_date, end_date):
        self.calls.append((ticker, start_date, end_date))
        if self.error:
            raise self.error
        return [a for a in self.articles if a.ticker == ticker]


class CountingAnalyzer:
    """Stands in for FinBERT; counts exactly how many texts it is asked to score."""

    def __init__(self):
        self.analyzed_texts: list[str] = []

    def analyze(self, texts):
        self.analyzed_texts.extend(texts)
        return [
            SentimentResult("POSITIVE", 0.8, 0.1, 0.1, 0.7, "fake-finbert", "test", NOW)
            for _ in texts
        ]


def article(ticker="NVDA", provider="finnhub", headline="Nvidia launches new AI chip", published_at=NOW, url=None, summary=None, source="Reuters", external_id=None):
    return NormalizedArticle(
        ticker=ticker,
        headline=headline,
        summary=summary,
        source=source,
        published_at=published_at,
        url=url or f"https://example.com/{abs(hash((headline, provider))) % 10**8}",
        provider=provider,
        external_id=external_id or f"{provider}-{abs(hash(headline)) % 10**8}",
        provider_sources=(provider,),
    )


# --------------------------------------------------------------------------
# Relevance classification
# --------------------------------------------------------------------------


def test_relevant_nvda_article_is_counted():
    assert classify_relevance("NVDA", "Nvidia beats earnings expectations") == RELEVANT
    assert classify_relevance("NVDA", "NVDA rallies after guidance raise") == RELEVANT


def test_brand_and_product_terms_count_as_relevant():
    # A story about Blackwell or CUDA is about Nvidia even without the name.
    assert classify_relevance("NVDA", "Blackwell shipments accelerate") == RELEVANT
    assert classify_relevance("NVDA", "CUDA adoption widens among developers") == RELEVANT
    assert classify_relevance("TSLA", "Elon Musk teases robotaxi launch") == RELEVANT


def test_company_name_alias_matching():
    assert classify_relevance("AMD", "Advanced Micro Devices lifts outlook") == RELEVANT
    assert classify_relevance("MU", "Micron Technology expands HBM output") == RELEVANT
    assert classify_relevance("TSLA", "Tesla deliveries climb") == RELEVANT
    assert classify_relevance("IREN", "Iris Energy expands data centre capacity") == RELEVANT


def test_spacex_only_article_excluded_from_nvda():
    assert classify_relevance("NVDA", "SpaceX Stock Is Down 33% From Its High") == NOT_RELEVANT


def test_xrp_only_article_excluded_from_nvda():
    assert classify_relevance("NVDA", "Why XRP Is Up Today") == NOT_RELEVANT


def test_ethereum_only_article_excluded_from_nvda():
    assert classify_relevance("NVDA", "Why Ethereum Jumped 5.8% Today") == NOT_RELEVANT


def test_generic_unrelated_story_excluded():
    assert classify_relevance("NVDA", "500th Episode: Investing Tips from 11 Years of Podcasting") == NOT_RELEVANT
    assert classify_relevance("NVDA", "Core & Main Is Up 5.0% After Buybacks") == NOT_RELEVANT


def test_industry_only_story_is_uncertain_not_relevant():
    # Real AI-chip news, but no evidence it is about Nvidia -> saved, not counted.
    assert classify_relevance("NVDA", "2 Stocks to Buy as Google Starts Selling Its AI Chips") == UNCERTAIN


def test_lowercase_ticker_words_do_not_false_match():
    # "mu" and "pony" are ordinary words; only the uppercase symbol counts.
    assert classify_relevance("MU", "The orchestra played in mu minor") == NOT_RELEVANT
    assert classify_relevance("PONY", "A pony escaped from the field") == NOT_RELEVANT


def test_cashtag_matches():
    assert classify_relevance("NVDA", "Traders pile into $NVDA calls") == RELEVANT


# --------------------------------------------------------------------------
# News Mood
# --------------------------------------------------------------------------


def _store_with_sentiment(db, articles, analyzer=None):
    stored, _ = upsert_articles(db, articles)
    from stock_ai.news.services import analyze_unanalyzed_articles

    analyze_unanalyzed_articles(db, analyzer or CountingAnalyzer(), limit=len(stored) or 1)
    return stored


def test_news_mood_counts_only_relevant_articles(db_session):
    _store_with_sentiment(
        db_session,
        [
            article(headline="Nvidia beats earnings expectations"),
            article(headline="Why Bitcoin Is Up Today"),
            article(headline="SpaceX Stock Is Down 33% From Its High"),
            article(headline="2 Stocks to Buy as Google Starts Selling Its AI Chips"),
        ],
    )
    summary = sentiment_summary(db_session, "NVDA", window_hours=72, as_of=NOW)
    # Only the Nvidia story counts; the other three are uncertain/unrelated.
    assert summary["articles_7d"] == 1
    assert summary["excluded_unrelated"] == 3


def test_uncertain_article_excluded_from_mood(db_session):
    _store_with_sentiment(db_session, [article(headline="AI chips demand surges across the sector", summary=None)])
    summary = sentiment_summary(db_session, "NVDA", window_hours=72, as_of=NOW)
    assert summary["articles_7d"] == 0
    assert summary["excluded_unrelated"] == 1


def test_news_mood_counts_cross_provider_duplicate_once(db_session):
    """One Reuters story delivered by both Yahoo and Finnhub is one article.

    Goes through the real ingestion path, where cross-provider merging happens
    in deduplicate_articles() before anything is written.
    """
    shared_url = "https://example.com/nvidia-earnings"
    yahoo = FakeProvider("yahoo_rss", [article(provider="yahoo_rss", headline="Nvidia beats earnings expectations", url=shared_url + "?utm_source=yahoo", external_id="y1")])
    finnhub = FakeProvider("finnhub", [article(provider="finnhub", headline="Nvidia beats earnings expectations", url=shared_url, external_id="f1")])

    analyzer = CountingAnalyzer()
    result = refresh_current_news(db_session, "NVDA", providers=[yahoo, finnhub], end_time=NOW, force=True, analyze_sentiment=True, analyzer=analyzer)

    assert result.articles_received == 2
    assert result.unique_articles == 1
    assert result.articles_created == 1

    rows = db_session.scalars(select(NewsArticle).where(NewsArticle.ticker == "NVDA")).all()
    assert len(rows) == 1
    # provider_sources metadata records both origins on the single row.
    assert set(article_provider_sources(rows[0])) == {"yahoo_rss", "finnhub"}

    summary = sentiment_summary(db_session, "NVDA", window_hours=72, as_of=NOW)
    assert summary["articles_7d"] == 1
    assert sorted(summary["providers"]) == ["finnhub", "yahoo_rss"]


def test_existing_saved_articles_can_be_reclassified_locally(db_session):
    # Simulate rows saved before the filter existed: force them all RELEVANT.
    upsert_articles(
        db_session,
        [
            article(headline="Nvidia beats earnings expectations"),
            article(headline="Why XRP Is Up Today"),
            article(headline="AI chips demand surges"),
        ],
    )
    for row in db_session.scalars(select(NewsArticle)):
        row.relevance = RELEVANT
    db_session.commit()

    report = reclassify_relevance(db_session, "NVDA")
    assert report["counts"][RELEVANT] == 1
    assert report["counts"][NOT_RELEVANT] == 1
    assert report["counts"][UNCERTAIN] == 1
    assert report["changed"] == 2


# --------------------------------------------------------------------------
# Incremental fetching
# --------------------------------------------------------------------------


def test_incremental_start_uses_default_window_on_first_run(db_session):
    start = incremental_start_time(db_session, "NVDA", "finnhub", NOW)
    assert start == NOW - timedelta(hours=DEFAULT_DAILY_WINDOW_HOURS)


def test_incremental_start_resumes_from_latest_saved_article(db_session):
    latest = NOW - timedelta(hours=5)
    upsert_articles(db_session, [article(published_at=latest)])
    start = incremental_start_time(db_session, "NVDA", "finnhub", NOW)
    assert start == latest - timedelta(hours=INCREMENTAL_OVERLAP_HOURS)


def test_incremental_start_is_floored_for_long_gaps(db_session):
    # A stale archive must not turn into an unbounded historical download.
    upsert_articles(db_session, [article(published_at=NOW - timedelta(days=30))])
    start = incremental_start_time(db_session, "NVDA", "finnhub", NOW)
    assert start == NOW - timedelta(hours=MAX_INCREMENTAL_LOOKBACK_HOURS)


def test_incremental_window_is_per_provider(db_session):
    upsert_articles(db_session, [article(provider="finnhub", published_at=NOW - timedelta(hours=2))])
    finnhub_start = incremental_start_time(db_session, "NVDA", "finnhub", NOW)
    yahoo_start = incremental_start_time(db_session, "NVDA", "yahoo_rss", NOW)
    # Yahoo has nothing saved, so it still gets the full default window.
    assert finnhub_start > yahoo_start


def test_overlap_window_does_not_create_duplicate_rows(db_session):
    repeated = article(published_at=NOW - timedelta(hours=1))
    provider = FakeProvider("finnhub", [repeated])

    first = refresh_current_news(db_session, "NVDA", providers=[provider], end_time=NOW, force=True, incremental=True)
    second = refresh_current_news(db_session, "NVDA", providers=[provider], end_time=NOW, force=True, incremental=True)

    assert first.articles_created == 1
    assert second.articles_created == 0  # re-delivered by the overlap, already stored
    assert second.duplicates_skipped == 1
    assert len(db_session.scalars(select(NewsArticle)).all()) == 1


# --------------------------------------------------------------------------
# Provider isolation
# --------------------------------------------------------------------------


def test_yahoo_failure_does_not_block_finnhub(db_session):
    yahoo = FakeProvider("yahoo_rss", error=RuntimeError("feed unreachable"))
    finnhub = FakeProvider("finnhub", [article(headline="Nvidia ships Blackwell")])

    result = refresh_current_news(db_session, "NVDA", providers=[yahoo, finnhub], end_time=NOW, force=True)

    statuses = {p.provider: p.status for p in result.provider_results}
    assert statuses["yahoo_rss"] == "failed"
    assert statuses["finnhub"] == "ok"
    assert result.articles_created == 1


def test_finnhub_failure_does_not_block_yahoo(db_session):
    finnhub = FakeProvider("finnhub", error=RuntimeError("finnhub down"))
    yahoo = FakeProvider("yahoo_rss", [article(provider="yahoo_rss", headline="Nvidia ships Blackwell")])

    result = refresh_current_news(db_session, "NVDA", providers=[finnhub, yahoo], end_time=NOW, force=True)

    statuses = {p.provider: p.status for p in result.provider_results}
    assert statuses["finnhub"] == "failed"
    assert statuses["yahoo_rss"] == "ok"
    assert result.articles_created == 1


def test_alpha_vantage_rate_limit_does_not_fail_refresh(db_session):
    alpha = FakeProvider("alpha_vantage", error=ProviderQuotaError("daily quota reached"))
    finnhub = FakeProvider("finnhub", [article(headline="Nvidia ships Blackwell")])

    result = refresh_current_news(db_session, "NVDA", providers=[finnhub, alpha], end_time=NOW, force=True)

    statuses = {p.provider: p.status for p in result.provider_results}
    assert statuses["alpha_vantage"] == "rate_limited"
    assert result.articles_created == 1


def test_rate_limited_provider_is_not_retried_within_the_cycle(db_session):
    alpha = FakeProvider("alpha_vantage", error=ProviderRateLimitError("slow down"))
    refresh_current_news(db_session, "NVDA", providers=[alpha], end_time=NOW, force=True)
    assert len(alpha.calls) == 1


def test_all_providers_failing_keeps_existing_saved_news(db_session):
    upsert_articles(db_session, [article(headline="Nvidia beats earnings expectations")])
    broken = [FakeProvider("yahoo_rss", error=RuntimeError("x")), FakeProvider("finnhub", error=RuntimeError("y"))]

    result = refresh_current_news(db_session, "NVDA", providers=broken, end_time=NOW, force=True)

    assert result.articles_created == 0
    assert len(db_session.scalars(select(NewsArticle)).all()) == 1  # nothing lost


# --------------------------------------------------------------------------
# FinBERT behavior
# --------------------------------------------------------------------------


def test_finbert_only_analyzes_articles_missing_sentiment(db_session):
    analyzer = CountingAnalyzer()
    provider = FakeProvider("finnhub", [article(headline="Nvidia beats earnings expectations")])

    refresh_current_news(db_session, "NVDA", providers=[provider], end_time=NOW, force=True, analyze_sentiment=True, analyzer=analyzer)
    first_count = len(analyzer.analyzed_texts)
    refresh_current_news(db_session, "NVDA", providers=[provider], end_time=NOW, force=True, analyze_sentiment=True, analyzer=analyzer)

    assert first_count == 1
    assert len(analyzer.analyzed_texts) == 1  # second pass re-analyzed nothing


def test_finbert_failure_still_saves_news(db_session):
    class BrokenAnalyzer:
        def analyze(self, texts):
            raise RuntimeError("torch exploded")

    provider = FakeProvider("finnhub", [article(headline="Nvidia beats earnings expectations")])
    result = refresh_current_news(db_session, "NVDA", providers=[provider], end_time=NOW, force=True, analyze_sentiment=True, analyzer=BrokenAnalyzer())

    assert result.articles_created == 1
    assert result.sentiment_error is not None
    assert len(db_session.scalars(select(NewsArticle)).all()) == 1


# --------------------------------------------------------------------------
# Daily sweep scope + summary
# --------------------------------------------------------------------------


def test_sweep_refreshes_only_tracked_tickers(db_session, monkeypatch):
    monkeypatch.setenv("DAILY_TRACKING_TICKERS", "NVDA,AMD,MU,TSLA,IREN")
    provider = FakeProvider("finnhub", [article(ticker=t, headline=f"{t} story") for t in ("NVDA", "AMD", "MU", "TSLA", "IREN", "AAPL")])

    result = refresh_tracked_news(db_session, providers=[provider], end_time=NOW, analyze_sentiment=False, force=True)

    requested = [call[0] for call in provider.calls]
    assert requested == ["NVDA", "AMD", "MU", "TSLA", "IREN"]
    assert "AAPL" not in requested
    assert result.tickers == ["NVDA", "AMD", "MU", "TSLA", "IREN"]


def test_sweep_continues_after_one_ticker_fails(db_session):
    class FlakyProvider(FakeProvider):
        def fetch_news(self, ticker, start_date, end_date):
            self.calls.append((ticker, start_date, end_date))
            if ticker == "AMD":
                raise RuntimeError("boom")
            return [article(ticker=ticker, headline=f"{ticker} story")]

    provider = FlakyProvider("finnhub")
    result = refresh_tracked_news(db_session, tickers=["NVDA", "AMD", "MU"], providers=[provider], end_time=NOW, analyze_sentiment=False, force=True)

    assert [c[0] for c in provider.calls] == ["NVDA", "AMD", "MU"]
    assert result.articles_created == 2  # NVDA + MU still saved


def test_sweep_summary_reports_relevance_counts(db_session):
    provider = FakeProvider(
        "finnhub",
        [
            article(headline="Nvidia beats earnings expectations"),
            article(headline="Why XRP Is Up Today"),
        ],
    )
    result = refresh_tracked_news(db_session, tickers=["NVDA"], providers=[provider], end_time=NOW, analyze_sentiment=False, force=True)

    assert result.relevant_saved == 1
    assert result.irrelevant_or_uncertain_saved == 1
    text = result.to_text_summary()
    assert "NEWS REFRESH" in text
    assert "Relevant: 1" in text
    assert "TOTAL" in text


def test_cooldown_skips_recently_refreshed_ticker(db_session):
    provider = FakeProvider("finnhub", [article(headline="Nvidia beats earnings expectations")])
    refresh_current_news(db_session, "NVDA", providers=[provider], end_time=NOW, force=True)

    # Not forced this time: the ticker was just refreshed, so no provider call.
    result = refresh_current_news(db_session, "NVDA", providers=[provider], end_time=NOW, force=False, min_refresh_interval_minutes=60)

    assert result.skipped_due_to_recent_cache is True
    assert len(provider.calls) == 1


# --------------------------------------------------------------------------
# Market-data independence + UI read path
# --------------------------------------------------------------------------


def test_news_refresh_runs_while_market_data_is_waiting(db_session, monkeypatch):
    """A ticker WAITING on an unpublished price bar must still collect news.

    News is a separate context layer; gating it behind market-data readiness
    would silently drop a day of stories whenever the price feed lags.
    """
    from stock_ai.services import daily_cycle
    from stock_ai.services.daily_cycle import run_daily_cycle

    monkeypatch.setenv("DAILY_TRACKING_TICKERS", "NVDA")
    monkeypatch.setattr(daily_cycle.price_history, "refresh_history", lambda *a, **k: None)
    monkeypatch.setattr(daily_cycle.price_history, "refresh_price_bars", lambda *a, **k: None)
    monkeypatch.setattr(daily_cycle, "get_market_data_provider", lambda *a, **k: object())
    # No price bars seeded at all -> every tracked ticker is WAITING.

    news_calls: list[dict] = []

    def _fake_sweep(db, **kwargs):
        news_calls.append(kwargs)
        from stock_ai.news.aggregator import DailyNewsRefreshResult

        return DailyNewsRefreshResult(started_at=NOW, tickers=["NVDA"])

    monkeypatch.setattr(daily_cycle, "refresh_tracked_news", _fake_sweep)

    result = run_daily_cycle(db_session, run_news=True, request_pacing_seconds=0)

    assert result.tickers_waiting == 1, "ticker should be waiting on market data"
    assert result.predictions_saved == 0
    assert len(news_calls) == 1, "news must still refresh while market data is waiting"


def test_stock_page_read_does_not_call_providers(db_session, monkeypatch):
    """GET /stocks/{t}/news and /sentiment read SQLite only."""
    import stock_ai.data.providers.news.finnhub as finnhub_mod
    import stock_ai.data.providers.news.yahoo_rss as yahoo_mod
    from stock_ai.news import aggregator as aggregator_mod

    def _boom(*args, **kwargs):
        raise AssertionError("page render must never call a live news provider")

    monkeypatch.setattr(finnhub_mod.FinnhubNewsProvider, "fetch_news", _boom)
    monkeypatch.setattr(yahoo_mod.YahooRssNewsProvider, "fetch_news", _boom)
    monkeypatch.setattr(aggregator_mod, "refresh_current_news", _boom)

    _store_with_sentiment(db_session, [article(headline="Nvidia beats earnings expectations")])

    from stock_ai.news.services import list_articles

    assert len(list_articles(db_session, "NVDA")) == 1
    assert sentiment_summary(db_session, "NVDA", window_hours=72, as_of=NOW)["articles_7d"] == 1
