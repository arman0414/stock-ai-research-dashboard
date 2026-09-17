from __future__ import annotations

import numpy as np
import pandas as pd

from stock_ai.schemas.stocks import normalize_ticker
from stock_ai.universe import GROUP_CONTEXT_ASSETS, SEMICONDUCTOR_AI_HARDWARE, peer_basket_for, ticker_group


CONTEXT_WINDOWS = (5, 10, 20, 50)
MARKET_CONTEXT_COLUMNS = [
    *(f"stock_vs_spy_{window}d" for window in CONTEXT_WINDOWS),
    *(f"stock_vs_qqq_{window}d" for window in CONTEXT_WINDOWS),
]
SECTOR_CONTEXT_COLUMNS = [f"stock_vs_semiconductor_{window}d" for window in CONTEXT_WINDOWS]
PEER_CONTEXT_COLUMNS = [
    *(f"peer_average_return_{window}d" for window in CONTEXT_WINDOWS),
    *(f"stock_vs_peer_{window}d" for window in CONTEXT_WINDOWS),
    *(f"peer_breadth_{window}d" for window in CONTEXT_WINDOWS),
]
CONTEXT_FEATURE_COLUMNS = [*MARKET_CONTEXT_COLUMNS, *SECTOR_CONTEXT_COLUMNS, *PEER_CONTEXT_COLUMNS]


def add_context_features(
    feature_data: pd.DataFrame,
    context_price_data: pd.DataFrame,
    peer_baskets: dict[str, tuple[str, ...]] | None = None,
) -> pd.DataFrame:
    """Attach market, sector, and peer-basket relative-strength features.

    The peer basket for a ticker always excludes the ticker itself. Context
    assets can be present in context_price_data without becoming training rows.
    """
    output = feature_data.copy()
    for column in CONTEXT_FEATURE_COLUMNS:
        output[column] = np.nan
    if output.empty or context_price_data.empty:
        return output

    output["date"] = pd.to_datetime(output["date"])
    prices = context_price_data.copy()
    prices["date"] = pd.to_datetime(prices["date"])
    prices["ticker"] = prices["ticker"].map(normalize_ticker)
    prices["close"] = pd.to_numeric(prices["close"], errors="coerce")

    returns = _return_matrix(prices)
    output["ticker"] = output["ticker"].map(normalize_ticker)

    frames = []
    for _, rows in output.groupby("ticker", sort=False):
        frames.append(_add_context_for_ticker(rows.copy(), returns, peer_baskets))
    return pd.concat(frames, ignore_index=True).sort_values(["ticker", "date"]).reset_index(drop=True)


def _return_matrix(price_data: pd.DataFrame) -> dict[int, pd.DataFrame]:
    pivot = price_data.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index()
    return {window: pivot.pct_change(periods=window, fill_method=None) for window in CONTEXT_WINDOWS}


def _add_context_for_ticker(
    rows: pd.DataFrame,
    returns_by_window: dict[int, pd.DataFrame],
    peer_baskets: dict[str, tuple[str, ...]] | None,
) -> pd.DataFrame:
    ticker = normalize_ticker(str(rows["ticker"].iloc[0]))
    group = ticker_group(ticker)
    peers = peer_basket_for(ticker, peer_baskets)
    dates = pd.to_datetime(rows["date"])

    for window, returns in returns_by_window.items():
        own_return = _aligned_returns(returns, ticker, dates)
        spy_return = _aligned_returns(returns, "SPY", dates)
        qqq_return = _aligned_returns(returns, "QQQ", dates)
        rows[f"stock_vs_spy_{window}d"] = own_return - spy_return
        rows[f"stock_vs_qqq_{window}d"] = own_return - qqq_return

        semiconductor_asset = _first_available_asset(returns, GROUP_CONTEXT_ASSETS[SEMICONDUCTOR_AI_HARDWARE])
        if group == SEMICONDUCTOR_AI_HARDWARE and semiconductor_asset:
            rows[f"stock_vs_semiconductor_{window}d"] = own_return - _aligned_returns(returns, semiconductor_asset, dates)

        available_peers = [peer for peer in peers if peer in returns.columns and peer != ticker]
        if available_peers:
            peer_returns = returns.reindex(dates)[available_peers]
            peer_average = peer_returns.mean(axis=1, skipna=True)
            peer_breadth = (peer_returns > 0).sum(axis=1) / peer_returns.notna().sum(axis=1).replace(0, np.nan)
            rows[f"peer_average_return_{window}d"] = peer_average.to_numpy()
            rows[f"stock_vs_peer_{window}d"] = own_return - peer_average.to_numpy()
            rows[f"peer_breadth_{window}d"] = peer_breadth.to_numpy()

    return rows


def _aligned_returns(returns: pd.DataFrame, ticker: str, dates: pd.Series) -> np.ndarray:
    normalized = normalize_ticker(ticker)
    if normalized not in returns.columns:
        return np.full(len(dates), np.nan)
    return returns.reindex(dates)[normalized].to_numpy()


def _first_available_asset(returns: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    for ticker in candidates:
        if normalize_ticker(ticker) in returns.columns:
            return normalize_ticker(ticker)
    return None
