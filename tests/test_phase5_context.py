from __future__ import annotations

import numpy as np
import pandas as pd

from stock_ai.features.context import add_context_features
from stock_ai.features.dataset import build_feature_dataset
from stock_ai.ml.phase5 import TARGET_FIXED_3PCT, build_phase5_dataset
from stock_ai.universe import FOCUS_STOCKS, REFERENCE_ASSETS, default_watchlist, peer_basket_for


def synthetic_context_prices(rows: int = 90) -> pd.DataFrame:
    frames = []
    dates = pd.bdate_range("2025-01-02", periods=rows)
    specs = {
        "NVDA": 1.00,
        "AMD": 0.50,
        "MU": 0.25,
        "SPY": 0.10,
        "QQQ": 0.20,
        "SMH": 0.30,
    }
    for ticker, slope in specs.items():
        close = 100 + np.arange(rows) * slope
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


def test_peer_basket_excludes_self_even_if_configured() -> None:
    assert "NVDA" not in peer_basket_for("NVDA", {"NVDA": ("NVDA", "AMD", "MU")})


def test_peer_average_excludes_same_stock_returns() -> None:
    prices = synthetic_context_prices()
    features = build_feature_dataset(prices[prices["ticker"] == "NVDA"], include_targets=False, include_price_action=True)
    enriched = add_context_features(features, prices, peer_baskets={"NVDA": ("NVDA", "AMD", "MU")})

    last_date = pd.to_datetime(enriched.iloc[-1]["date"])
    pivot = prices.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index()
    returns_5d = pivot.pct_change(periods=5, fill_method=None)
    expected_peer_average = returns_5d.reindex([last_date])[["AMD", "MU"]].mean(axis=1).iloc[0]

    assert enriched.iloc[-1]["peer_average_return_5d"] == expected_peer_average
    assert enriched.iloc[-1]["peer_average_return_5d"] != returns_5d.reindex([last_date])[["NVDA", "AMD", "MU"]].mean(axis=1).iloc[0]


def test_phase5_dataset_keeps_reference_assets_out_of_training_rows() -> None:
    prices = synthetic_context_prices()
    dataset = build_phase5_dataset(prices, training_tickers=("NVDA", *REFERENCE_ASSETS), feature_group="technical_price_action_context", target_mode=TARGET_FIXED_3PCT)

    assert set(dataset["ticker"].unique()) == {"NVDA"}
    assert "stock_vs_spy_5d" in dataset.columns
    assert "stock_vs_semiconductor_5d" in dataset.columns


def test_default_watchlist_uses_focus_stocks_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("DEFAULT_WATCHLIST", raising=False)
    assert default_watchlist() == FOCUS_STOCKS
