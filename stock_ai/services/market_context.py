"""Phase 8: a small, direct market/sector trend read for the dashboard.

Deliberately simple (price vs its own 50-day average) rather than reusing the
full ML feature pipeline -- this is a display concern, not a model input."""
from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from stock_ai.models.market_data import PriceBar
from stock_ai.schemas.stocks import normalize_ticker
from stock_ai.universe import GROUP_CONTEXT_ASSETS, ticker_group


def build_market_context(db: Session, ticker: str, feature_row: Any | None) -> dict:
    normalized = normalize_ticker(ticker)
    group = ticker_group(normalized)
    sector_assets = GROUP_CONTEXT_ASSETS.get(group, ())
    sector_ticker = next((asset for asset in sector_assets if asset not in ("SPY", "QQQ")), None)

    stock_vs_qqq = _safe_float(feature_row.get("stock_vs_qqq_20d")) if feature_row is not None else None
    stock_vs_sector = _safe_float(feature_row.get("stock_vs_semiconductor_20d")) if feature_row is not None else None
    if stock_vs_sector is None and feature_row is not None:
        stock_vs_sector = _safe_float(feature_row.get("stock_vs_peer_20d"))

    return {
        "spy_trend": _own_trend(db, "SPY"),
        "qqq_trend": _own_trend(db, "QQQ"),
        "sector_trend": _own_trend(db, sector_ticker) if sector_ticker else "NEUTRAL",
        "sector_asset": sector_ticker,
        "stock_vs_market": _relative_label(stock_vs_qqq),
        "stock_vs_sector": _relative_label(stock_vs_sector),
    }


def _own_trend(db: Session, asset_ticker: str) -> str:
    bars = list(db.scalars(select(PriceBar).where(PriceBar.ticker == asset_ticker).order_by(PriceBar.date.desc()).limit(60)))
    if len(bars) < 50:
        return "NEUTRAL"
    closes = [float(bar.close) for bar in reversed(bars)]
    sma50 = sum(closes[-50:]) / 50
    current = closes[-1]
    if current > sma50 * 1.01:
        return "BULLISH"
    if current < sma50 * 0.99:
        return "BEARISH"
    return "NEUTRAL"


def _relative_label(value: float | None) -> str:
    if value is None:
        return "NEUTRAL"
    if value > 0.02:
        return "OUTPERFORMING"
    if value < -0.02:
        return "UNDERPERFORMING"
    return "NEUTRAL"


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(numeric) else numeric
