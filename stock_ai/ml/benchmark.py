from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from stock_ai.config import PROJECT_ROOT
from stock_ai.features.dataset import build_feature_dataset, price_bars_to_dataframe
from stock_ai.features.news_features import news_coverage
from stock_ai.features.targets import DEFAULT_HORIZONS
from stock_ai.ml.config import DEFAULT_CLASSIFICATION_MODELS, DEFAULT_REGRESSION_MODELS, ModelConfig
from stock_ai.ml.training import train_horizon_models
from stock_ai.models.market_data import PriceBar
from stock_ai.models.news import NewsArticle
from stock_ai.schemas.stocks import normalize_ticker
from stock_ai.utils.json_safe import write_json_file


DEFAULT_BENCHMARK_UNIVERSE = [
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "GOOGL",
    "META",
    "TSLA",
    "JPM",
    "WMT",
    "XOM",
    "AMD",
    "NFLX",
    "AVGO",
    "COST",
    "CRM",
]


def load_multi_stock_prices(db: Session, tickers: Iterable[str]) -> tuple[pd.DataFrame, dict[str, str]]:
    frames = []
    skipped: dict[str, str] = {}
    for ticker in tickers:
        normalized = normalize_ticker(ticker)
        bars = list(db.scalars(select(PriceBar).where(PriceBar.ticker == normalized).order_by(PriceBar.date.asc())))
        if len(bars) < 320:
            skipped[normalized] = f"insufficient price history: {len(bars)} rows"
            continue
        frames.append(price_bars_to_dataframe(bars))
    if not frames:
        return pd.DataFrame(), skipped
    return pd.concat(frames, ignore_index=True).sort_values(["ticker", "date"]).reset_index(drop=True), skipped


def load_multi_stock_news(db: Session, tickers: Iterable[str]) -> list[NewsArticle]:
    normalized = [normalize_ticker(ticker) for ticker in tickers]
    return list(
        db.scalars(
            select(NewsArticle)
            .where(NewsArticle.ticker.in_(normalized))
            .order_by(NewsArticle.ticker.asc(), NewsArticle.published_at.asc())
        )
    )


def build_benchmark_dataset(
    price_data: pd.DataFrame,
    feature_group: str,
    news_articles: list[NewsArticle] | pd.DataFrame | None = None,
) -> pd.DataFrame:
    if feature_group == "technical":
        return build_feature_dataset(price_data, include_targets=True)
    if feature_group == "technical_price_action":
        return build_feature_dataset(price_data, include_targets=True, include_price_action=True)
    if feature_group == "technical_price_action_news":
        return build_feature_dataset(
            price_data,
            include_targets=True,
            include_price_action=True,
            include_news=True,
            news_articles=news_articles,
        )
    raise ValueError(f"Unsupported benchmark feature group: {feature_group}")


def run_benchmark(
    price_data: pd.DataFrame,
    feature_group: str,
    horizons: list[str] | None = None,
    news_articles: list[NewsArticle] | pd.DataFrame | None = None,
    config: ModelConfig | None = None,
    classification_models: list[str] | None = None,
    regression_models: list[str] | None = None,
) -> dict:
    horizons = horizons or list(DEFAULT_HORIZONS)
    dataset = build_benchmark_dataset(price_data, feature_group=feature_group, news_articles=news_articles)
    results = {}
    for horizon in horizons:
        result = train_horizon_models(
            dataset,
            horizon=horizon,
            classification_models=classification_models or DEFAULT_CLASSIFICATION_MODELS,
            regression_models=regression_models or DEFAULT_REGRESSION_MODELS,
            config=config,
        )
        results[horizon] = _summarize_training_result(result)
    return {
        "feature_group": feature_group,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "row_count": int(len(dataset)),
        "date_range": _date_range(dataset),
        "features": _feature_columns(dataset),
        "news_coverage": news_coverage(dataset) if feature_group.endswith("_news") else None,
        "horizons": results,
    }


def compare_benchmarks(technical: dict, price_action: dict, news: dict | None = None) -> dict:
    comparisons = {
        "technical_vs_price_action": _diff_reports(technical, price_action),
    }
    if news is not None:
        comparisons["price_action_vs_news"] = _diff_reports(price_action, news)
        comparisons["technical_vs_news"] = _diff_reports(technical, news)
    return comparisons


def save_benchmark_report(report: dict, prefix: str = "benchmark", root: Path | None = None) -> Path:
    root = root or PROJECT_ROOT / "artifacts" / "benchmarks"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{prefix}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    write_json_file(path, report, indent=2, sort_keys=True)
    return path


def _summarize_training_result(result) -> dict:
    return {
        "class_distribution": result.class_distribution,
        "split": result.split_summary,
        "best_classifier": result.best_classifier_name,
        "best_regressor": result.best_regressor_name,
        "classification_validation": _compact_classification(result.classification_validation_metrics),
        "classification_test": _compact_classification(result.classification_test_metrics),
        "regression_validation": _compact_regression(result.regression_validation_metrics),
        "regression_test": _compact_regression(result.regression_test_metrics),
        "high_confidence": {
            name: metrics.get("confidence", {})
            for name, metrics in result.classification_test_metrics.items()
        },
        "feature_importance": result.feature_importance,
        "strategy_metrics": result.strategy_metrics,
    }


def _compact_classification(metrics_by_model: dict[str, dict]) -> dict[str, dict]:
    return {
        name: {
            "accuracy": metrics.get("accuracy"),
            "balanced_accuracy": metrics.get("balanced_accuracy"),
            "macro_f1": metrics.get("macro_f1"),
            "up_precision": metrics.get("class_metrics", {}).get("UP", {}).get("precision"),
            "down_precision": metrics.get("class_metrics", {}).get("DOWN", {}).get("precision"),
            "log_loss": metrics.get("log_loss"),
            "brier_score_multiclass": metrics.get("brier_score_multiclass"),
        }
        for name, metrics in metrics_by_model.items()
    }


def _compact_regression(metrics_by_model: dict[str, dict]) -> dict[str, dict]:
    return {
        name: {
            "mae": metrics.get("mae"),
            "rmse": metrics.get("rmse"),
            "direction_accuracy": metrics.get("direction_accuracy"),
        }
        for name, metrics in metrics_by_model.items()
    }


def _diff_reports(left: dict, right: dict) -> dict:
    diff = {}
    for horizon, left_result in left.get("horizons", {}).items():
        right_result = right.get("horizons", {}).get(horizon)
        if not right_result:
            continue
        model = right_result.get("best_classifier")
        left_metrics = left_result.get("classification_test", {}).get(model, {})
        right_metrics = right_result.get("classification_test", {}).get(model, {})
        diff[horizon] = {
            "model": model,
            "balanced_accuracy_delta": _delta(right_metrics, left_metrics, "balanced_accuracy"),
            "macro_f1_delta": _delta(right_metrics, left_metrics, "macro_f1"),
            "up_precision_delta": _delta(right_metrics, left_metrics, "up_precision"),
            "down_precision_delta": _delta(right_metrics, left_metrics, "down_precision"),
        }
    return diff


def _delta(right: dict, left: dict, key: str) -> float | None:
    if right.get(key) is None or left.get(key) is None:
        return None
    return float(right[key] - left[key])


def _date_range(dataset: pd.DataFrame) -> dict[str, str | None]:
    if dataset.empty:
        return {"start": None, "end": None}
    dates = pd.to_datetime(dataset["date"])
    return {"start": dates.min().date().isoformat(), "end": dates.max().date().isoformat()}


def _feature_columns(dataset: pd.DataFrame) -> list[str]:
    excluded_prefixes = ("target_",)
    excluded = {"date", "ticker", "open", "high", "low", "close", "adjusted_close", "volume"}
    return [column for column in dataset.columns if column not in excluded and not column.startswith(excluded_prefixes)]
