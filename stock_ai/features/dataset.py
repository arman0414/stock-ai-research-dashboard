from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from stock_ai.features.news_features import NEWS_FEATURE_COLUMNS, add_news_features
from stock_ai.features.price_action import PRICE_ACTION_FEATURE_COLUMNS, add_price_action_features, summarize_latest_structure
from stock_ai.features.targets import DEFAULT_HORIZONS, DirectionThresholds, add_future_targets, target_columns
from stock_ai.features.technical import TECHNICAL_FEATURE_COLUMNS, add_technical_features
from stock_ai.models.market_data import PriceBar
from stock_ai.models.news import NewsArticle
from stock_ai.schemas.stocks import normalize_ticker


BASE_PRICE_COLUMNS = ["date", "ticker", "open", "high", "low", "close", "adjusted_close", "volume"]
TARGET_COLUMN_PREFIXES = ("target_close_", "target_return_", "target_class_")


@dataclass(frozen=True)
class TrainingData:
    X: pd.DataFrame
    y_classification: pd.Series
    y_regression: pd.Series
    dates: pd.Series


def price_bars_to_dataframe(price_bars: list[PriceBar]) -> pd.DataFrame:
    rows = [
        {
            "date": bar.date,
            "ticker": bar.ticker,
            "open": float(bar.open),
            "high": float(bar.high),
            "low": float(bar.low),
            "close": float(bar.close),
            "adjusted_close": float(bar.adjusted_close),
            "volume": bar.volume,
        }
        for bar in price_bars
    ]
    return pd.DataFrame(rows, columns=BASE_PRICE_COLUMNS)


def load_price_history(
    db: Session,
    ticker: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> pd.DataFrame:
    normalized_ticker = normalize_ticker(ticker)
    query = select(PriceBar).where(PriceBar.ticker == normalized_ticker).order_by(PriceBar.date.asc())
    if start_date:
        query = query.where(PriceBar.date >= start_date)
    if end_date:
        query = query.where(PriceBar.date <= end_date)

    return price_bars_to_dataframe(list(db.scalars(query)))


def build_feature_dataset(
    price_data: pd.DataFrame,
    ticker: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    include_targets: bool = True,
    training_ready: bool = False,
    horizon: str | None = None,
    horizons: dict[str, int] | None = None,
    thresholds: DirectionThresholds | None = None,
    include_price_action: bool = False,
    include_news: bool = False,
    news_articles: pd.DataFrame | list[NewsArticle] | None = None,
) -> pd.DataFrame:
    """Build a chronological feature dataset, optionally with supervised targets."""
    if price_data.empty:
        return pd.DataFrame(columns=BASE_PRICE_COLUMNS + TECHNICAL_FEATURE_COLUMNS)

    data = price_data.copy()
    data["date"] = pd.to_datetime(data["date"])
    if ticker:
        data = data[data["ticker"] == normalize_ticker(ticker)]
    if start_date:
        data = data[data["date"] >= pd.Timestamp(start_date)]
    if end_date:
        data = data[data["date"] <= pd.Timestamp(end_date)]

    data = data.sort_values(["ticker", "date"]).reset_index(drop=True)
    dataset = add_technical_features(data)
    if include_price_action:
        dataset = add_price_action_features(dataset)
    if include_news:
        dataset = add_news_features(dataset, news_articles)

    selected_horizons = horizons or DEFAULT_HORIZONS
    if include_targets:
        dataset = add_future_targets(dataset, horizons=selected_horizons, thresholds=thresholds)

    if training_ready:
        if not include_targets:
            raise ValueError("training_ready=True requires include_targets=True")
        if horizon is None:
            raise ValueError("A horizon is required when building a training-ready dataset")
        if horizon not in selected_horizons:
            raise ValueError(f"Unsupported horizon: {horizon}")
        required_features = (
            TECHNICAL_FEATURE_COLUMNS
            + (PRICE_ACTION_FEATURE_COLUMNS if include_price_action else [])
            + (NEWS_FEATURE_COLUMNS if include_news else [])
        )
        dataset = dataset.dropna(subset=required_features + [f"target_return_{horizon}", f"target_class_{horizon}"])

    return dataset.sort_values(["ticker", "date"]).reset_index(drop=True)


def build_dataset_from_db(
    db: Session,
    ticker: str,
    start_date: date | None = None,
    end_date: date | None = None,
    include_targets: bool = True,
    training_ready: bool = False,
    horizon: str | None = None,
    include_price_action: bool = False,
    include_news: bool = False,
) -> pd.DataFrame:
    prices = load_price_history(db, ticker=ticker, start_date=start_date, end_date=end_date)
    news_articles = _load_news_articles(db, ticker) if include_news else None
    return build_feature_dataset(
        prices,
        ticker=ticker,
        include_targets=include_targets,
        training_ready=training_ready,
        horizon=horizon,
        include_price_action=include_price_action,
        include_news=include_news,
        news_articles=news_articles,
    )


def build_training_data(
    price_data: pd.DataFrame,
    horizon: str,
    ticker: str | None = None,
    horizons: dict[str, int] | None = None,
    thresholds: DirectionThresholds | None = None,
    include_price_action: bool = False,
    include_news: bool = False,
    news_articles: pd.DataFrame | list[NewsArticle] | None = None,
) -> TrainingData:
    selected_horizons = horizons or DEFAULT_HORIZONS
    if horizon not in selected_horizons:
        raise ValueError(f"Unsupported horizon: {horizon}")

    dataset = build_feature_dataset(
        price_data,
        ticker=ticker,
        include_targets=True,
        training_ready=True,
        horizon=horizon,
        horizons=selected_horizons,
        thresholds=thresholds,
        include_price_action=include_price_action,
        include_news=include_news,
        news_articles=news_articles,
    )
    feature_columns = get_feature_columns(dataset)

    return TrainingData(
        X=dataset[feature_columns].copy(),
        y_classification=dataset[f"target_class_{horizon}"].copy(),
        y_regression=dataset[f"target_return_{horizon}"].copy(),
        dates=dataset["date"].copy(),
    )


def get_feature_columns(dataset: pd.DataFrame) -> list[str]:
    excluded = set(BASE_PRICE_COLUMNS)
    return [
        column
        for column in dataset.columns
        if column not in excluded and not column.startswith(TARGET_COLUMN_PREFIXES)
    ]


def latest_features_for_ticker(db: Session, ticker: str) -> dict[str, Any] | None:
    dataset = build_dataset_from_db(db, ticker=ticker, include_targets=False)
    if dataset.empty:
        return None

    feature_rows = dataset.dropna(subset=["sma_20", "sma_50", "relative_volume"], how="any")
    if feature_rows.empty:
        return None

    row = feature_rows.iloc[-1]
    keys = [
        "ticker",
        "date",
        "close",
        "rsi_14",
        "sma_20",
        "sma_50",
        "relative_volume",
        "volatility_20d",
        "macd",
        "macd_signal",
    ]
    return {key: _json_safe(row[key]) for key in keys}


def latest_structure_for_ticker(db: Session, ticker: str) -> dict[str, Any] | None:
    dataset = build_dataset_from_db(db, ticker=ticker, include_targets=False, include_price_action=True)
    return summarize_latest_structure(dataset)


def _load_news_articles(db: Session, ticker: str) -> list[NewsArticle]:
    return list(
        db.scalars(
            select(NewsArticle)
            .where(NewsArticle.ticker == normalize_ticker(ticker))
            .order_by(NewsArticle.published_at.asc())
        )
    )


def _json_safe(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (float, int, str)):
        return value
    return float(value)
