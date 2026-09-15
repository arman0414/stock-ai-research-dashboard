from __future__ import annotations

import os
from dataclasses import dataclass

from stock_ai.schemas.stocks import normalize_ticker


FOCUS_STOCKS = (
    "NVDA",
    "AMD",
    "MU",
    "SNDK",
    "IREN",
    "PONY",
    "TSLA",
    "RDDT",
    "APLD",
    "SMCI",
)

LEGACY_BENCHMARK_UNIVERSE = (
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
)

MARKET_CONTEXT_ASSETS = ("SPY", "QQQ")
SECTOR_CONTEXT_ASSETS = ("SMH", "XLC")

SEMICONDUCTOR_AI_HARDWARE = "SEMICONDUCTOR_AI_HARDWARE"
AI_INFRASTRUCTURE = "AI_INFRASTRUCTURE"
AUTONOMOUS_EV = "AUTONOMOUS_EV"
DIGITAL_PLATFORM = "DIGITAL_PLATFORM"
GENERAL_REFERENCE = "GENERAL_REFERENCE"

GROUP_BY_TICKER = {
    "NVDA": SEMICONDUCTOR_AI_HARDWARE,
    "AMD": SEMICONDUCTOR_AI_HARDWARE,
    "MU": SEMICONDUCTOR_AI_HARDWARE,
    "SNDK": SEMICONDUCTOR_AI_HARDWARE,
    "SMCI": SEMICONDUCTOR_AI_HARDWARE,
    "IREN": AI_INFRASTRUCTURE,
    "APLD": AI_INFRASTRUCTURE,
    "TSLA": AUTONOMOUS_EV,
    "PONY": AUTONOMOUS_EV,
    "RDDT": DIGITAL_PLATFORM,
}

GROUP_CONTEXT_ASSETS = {
    SEMICONDUCTOR_AI_HARDWARE: ("SMH", "QQQ", "SPY"),
    AI_INFRASTRUCTURE: ("QQQ", "SPY", "SMH"),
    AUTONOMOUS_EV: ("QQQ", "SPY"),
    DIGITAL_PLATFORM: ("XLC", "QQQ", "SPY"),
    GENERAL_REFERENCE: ("QQQ", "SPY"),
}

PEER_BASKETS = {
    "NVDA": ("AMD", "MU", "SNDK", "SMCI"),
    "AMD": ("NVDA", "MU", "SNDK", "SMCI"),
    "MU": ("NVDA", "AMD", "SNDK", "SMCI"),
    "SNDK": ("NVDA", "AMD", "MU", "SMCI"),
    "SMCI": ("NVDA", "AMD", "MU", "SNDK"),
    "IREN": ("APLD", "NVDA", "SMCI"),
    "APLD": ("IREN", "NVDA", "SMCI"),
    "TSLA": ("PONY",),
    "PONY": ("TSLA",),
    "RDDT": ("META", "GOOGL", "NFLX"),
}

REFERENCE_UNIVERSE = tuple(
    dict.fromkeys(
        (
            *LEGACY_BENCHMARK_UNIVERSE,
            *FOCUS_STOCKS,
            "MU",
            "SNDK",
            "IREN",
            "PONY",
            "RDDT",
            "APLD",
            "SMCI",
            *MARKET_CONTEXT_ASSETS,
            *SECTOR_CONTEXT_ASSETS,
        )
    )
)

SPECIALIZED_TRAINING_UNIVERSE = tuple(
    dict.fromkeys(
        (
            *FOCUS_STOCKS,
            "AAPL",
            "MSFT",
            "AMZN",
            "GOOGL",
            "META",
            "AVGO",
            *MARKET_CONTEXT_ASSETS,
            *SECTOR_CONTEXT_ASSETS,
        )
    )
)

REFERENCE_ASSETS = tuple(dict.fromkeys((*MARKET_CONTEXT_ASSETS, *SECTOR_CONTEXT_ASSETS)))


@dataclass(frozen=True)
class UniverseConfig:
    focus_stocks: tuple[str, ...] = FOCUS_STOCKS
    reference_universe: tuple[str, ...] = REFERENCE_UNIVERSE
    specialized_training_universe: tuple[str, ...] = SPECIALIZED_TRAINING_UNIVERSE
    reference_assets: tuple[str, ...] = REFERENCE_ASSETS
    peer_baskets: dict[str, tuple[str, ...]] | None = None


def parse_ticker_list(value: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if not value:
        return default
    tickers = [normalize_ticker(item) for item in value.split(",") if item.strip()]
    return tuple(dict.fromkeys(tickers)) or default


def default_watchlist() -> tuple[str, ...]:
    return parse_ticker_list(os.getenv("DEFAULT_WATCHLIST"), FOCUS_STOCKS)


def ticker_group(ticker: str) -> str:
    return GROUP_BY_TICKER.get(normalize_ticker(ticker), GENERAL_REFERENCE)


def peer_basket_for(ticker: str, peer_baskets: dict[str, tuple[str, ...]] | None = None) -> tuple[str, ...]:
    normalized = normalize_ticker(ticker)
    baskets = peer_baskets or PEER_BASKETS
    peers = tuple(normalize_ticker(peer) for peer in baskets.get(normalized, ()))
    return tuple(peer for peer in peers if peer != normalized)

