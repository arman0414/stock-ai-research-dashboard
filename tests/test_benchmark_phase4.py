from __future__ import annotations

import numpy as np
import pandas as pd

from stock_ai.ml.benchmark import build_benchmark_dataset, compare_benchmarks, run_benchmark
from stock_ai.ml.config import ModelConfig, XGBoostConfig


def synthetic_prices(rows: int = 340) -> pd.DataFrame:
    frames = []
    for ticker, offset in [("AAPL", 0), ("MSFT", 5)]:
        dates = pd.bdate_range("2024-01-02", periods=rows)
        close = 100 + offset + np.arange(rows) * 0.1 + np.sin(np.arange(rows) / 5)
        frames.append(
            pd.DataFrame(
                {
                    "date": dates,
                    "ticker": ticker,
                    "open": close - 0.2,
                    "high": close + 1,
                    "low": close - 1,
                    "close": close,
                    "adjusted_close": close,
                    "volume": 1_000_000 + np.arange(rows),
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def tiny_config() -> ModelConfig:
    return ModelConfig(xgboost=XGBoostConfig(n_estimators=3, max_depth=2, learning_rate=0.1, random_state=7, n_jobs=1), random_state=7)


def test_benchmark_dataset_feature_groups() -> None:
    prices = synthetic_prices()

    technical = build_benchmark_dataset(prices, "technical")
    price_action = build_benchmark_dataset(prices, "technical_price_action")

    assert "buyer_pressure_score" not in technical.columns
    assert "buyer_pressure_score" in price_action.columns
    assert technical["ticker"].nunique() == 2
    assert price_action["ticker"].nunique() == 2


def test_run_benchmark_and_compare_reports() -> None:
    prices = synthetic_prices()

    technical = run_benchmark(
        prices,
        "technical",
        horizons=["5d"],
        classification_models=["dummy"],
        regression_models=["dummy"],
        config=tiny_config(),
    )
    price_action = run_benchmark(
        prices,
        "technical_price_action",
        horizons=["5d"],
        classification_models=["dummy"],
        regression_models=["dummy"],
        config=tiny_config(),
    )
    comparison = compare_benchmarks(technical, price_action)

    assert "5d" in technical["horizons"]
    assert technical["horizons"]["5d"]["classification_test"]["dummy"]["accuracy"] is not None
    assert "technical_vs_price_action" in comparison

