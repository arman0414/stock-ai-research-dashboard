from __future__ import annotations

import numpy as np
import pandas as pd

from stock_ai.models.news import NewsArticle
from stock_ai.news.timing import eligible_prediction_date


NEWS_WINDOWS = (1, 3, 7, 14, 30)
IMPORTANT_EVENT_FEATURES = {
    "EARNINGS_BEAT": "earnings_positive_count_30d",
    "EARNINGS_MISS": "earnings_negative_count_30d",
    "ANALYST_UPGRADE": "upgrade_count_30d",
    "ANALYST_DOWNGRADE": "downgrade_count_30d",
    "PARTNERSHIP": "partnership_count_30d",
    "NEW_CONTRACT": "contract_count_30d",
    "REGULATORY_RISK": "regulatory_risk_count_30d",
    "LAWSUIT": "lawsuit_count_30d",
    "STOCK_OFFERING": "stock_offering_count_30d",
}

NEWS_FEATURE_COLUMNS = [
    "positive_count_7d",
    "neutral_count_7d",
    "negative_count_7d",
    "max_positive_probability_7d",
    "max_negative_probability_7d",
    "sentiment_std_7d",
    "sentiment_change_7d",
    "sentiment_change_3d",
    "weighted_sentiment_7d",
    "news_volume_ratio",
    *IMPORTANT_EVENT_FEATURES.values(),
]

for window in NEWS_WINDOWS:
    NEWS_FEATURE_COLUMNS.extend(
        [
            f"news_count_{window}d",
            f"average_sentiment_{window}d",
            f"has_news_{window}d",
        ]
    )


def articles_to_dataframe(articles: list[NewsArticle]) -> pd.DataFrame:
    rows = []
    for article in articles:
        sentiment = article.sentiment
        rows.append(
            {
                "ticker": article.ticker,
                "headline": article.headline,
                "published_at": article.published_at,
                "eligible_date": eligible_prediction_date(article.published_at),
                "event_category": article.event_category,
                "sentiment_label": sentiment.sentiment_label if sentiment else "NEUTRAL",
                "positive_probability": float(sentiment.positive_probability) if sentiment else 0.0,
                "neutral_probability": float(sentiment.neutral_probability) if sentiment else 1.0,
                "negative_probability": float(sentiment.negative_probability) if sentiment else 0.0,
                "sentiment_score": float(sentiment.sentiment_score) if sentiment else 0.0,
            }
        )
    return pd.DataFrame(rows)


def add_news_features(dataset: pd.DataFrame, articles: pd.DataFrame | list[NewsArticle] | None) -> pd.DataFrame:
    output = dataset.copy()
    for column in NEWS_FEATURE_COLUMNS:
        output[column] = 0.0
    if articles is None or (hasattr(articles, "empty") and articles.empty):
        return output

    article_frame = articles_to_dataframe(articles) if isinstance(articles, list) else articles.copy()
    if article_frame.empty:
        return output
    article_frame["eligible_date"] = pd.to_datetime(article_frame["eligible_date"])
    output["date"] = pd.to_datetime(output["date"])

    frames = []
    for ticker, rows in output.groupby("ticker", sort=False):
        ticker_articles = article_frame[article_frame["ticker"] == ticker].copy()
        frames.append(_add_news_for_ticker(rows.copy(), ticker_articles))
    return pd.concat(frames, ignore_index=True).sort_values(["ticker", "date"]).reset_index(drop=True)


def news_coverage(dataset: pd.DataFrame) -> dict[str, float | int]:
    if dataset.empty or "has_news_7d" not in dataset.columns:
        return {"rows": int(len(dataset)), "rows_with_news_7d": 0, "coverage_7d": 0.0}
    rows_with_news = int((dataset["has_news_7d"] > 0).sum())
    return {
        "rows": int(len(dataset)),
        "rows_with_news_7d": rows_with_news,
        "coverage_7d": float(rows_with_news / len(dataset)) if len(dataset) else 0.0,
    }


def _add_news_for_ticker(rows: pd.DataFrame, articles: pd.DataFrame) -> pd.DataFrame:
    if articles.empty:
        return rows
    articles = articles.sort_values("eligible_date")
    for index, row in rows.iterrows():
        current_date = row["date"]
        available = articles[articles["eligible_date"] <= current_date]
        if available.empty:
            continue

        for window in NEWS_WINDOWS:
            start = current_date - pd.Timedelta(days=window)
            window_articles = available[available["eligible_date"] > start]
            rows.at[index, f"news_count_{window}d"] = len(window_articles)
            rows.at[index, f"has_news_{window}d"] = 1.0 if len(window_articles) else 0.0
            rows.at[index, f"average_sentiment_{window}d"] = window_articles["sentiment_score"].mean() if len(window_articles) else 0.0

        last_7 = available[available["eligible_date"] > current_date - pd.Timedelta(days=7)]
        prev_7 = available[(available["eligible_date"] <= current_date - pd.Timedelta(days=7)) & (available["eligible_date"] > current_date - pd.Timedelta(days=14))]
        last_3 = available[available["eligible_date"] > current_date - pd.Timedelta(days=3)]
        prev_3 = available[(available["eligible_date"] <= current_date - pd.Timedelta(days=3)) & (available["eligible_date"] > current_date - pd.Timedelta(days=6))]
        rows.at[index, "positive_count_7d"] = int((last_7["sentiment_label"] == "POSITIVE").sum())
        rows.at[index, "neutral_count_7d"] = int((last_7["sentiment_label"] == "NEUTRAL").sum())
        rows.at[index, "negative_count_7d"] = int((last_7["sentiment_label"] == "NEGATIVE").sum())
        rows.at[index, "max_positive_probability_7d"] = last_7["positive_probability"].max() if len(last_7) else 0.0
        rows.at[index, "max_negative_probability_7d"] = last_7["negative_probability"].max() if len(last_7) else 0.0
        rows.at[index, "sentiment_std_7d"] = last_7["sentiment_score"].std(ddof=0) if len(last_7) else 0.0
        rows.at[index, "sentiment_change_7d"] = (last_7["sentiment_score"].mean() if len(last_7) else 0.0) - (prev_7["sentiment_score"].mean() if len(prev_7) else 0.0)
        rows.at[index, "sentiment_change_3d"] = (last_3["sentiment_score"].mean() if len(last_3) else 0.0) - (prev_3["sentiment_score"].mean() if len(prev_3) else 0.0)
        rows.at[index, "weighted_sentiment_7d"] = _weighted_sentiment(last_7, current_date)
        rows.at[index, "news_volume_ratio"] = _safe_ratio(len(last_3), max(1, len(prev_7) / 7 * 3))
        last_30 = available[available["eligible_date"] > current_date - pd.Timedelta(days=30)]
        for category, column in IMPORTANT_EVENT_FEATURES.items():
            rows.at[index, column] = int((last_30["event_category"] == category).sum())
    return rows


def _weighted_sentiment(articles: pd.DataFrame, current_date: pd.Timestamp, decay: float = 0.25) -> float:
    if articles.empty:
        return 0.0
    ages = (current_date - articles["eligible_date"]).dt.days.clip(lower=0)
    weights = np.exp(-decay * ages)
    return float(np.average(articles["sentiment_score"], weights=weights))


def _safe_ratio(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator else 0.0

