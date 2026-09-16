"""ENTRY SETUP: a research interpretation layer, not a new model.

Answers a practical question the existing model outputs don't answer
directly: "based on the existing model forecast and current technical
context, does this look like a reasonable entry setup right now?" It
combines already-computed, existing information (validated signal,
predicted upside, support/resistance, buyer pressure) using simple,
documented, configurable rules -- it never runs any ML inference, never
trains anything, and never changes a prediction's stored values.

States: GOOD_SETUP, WATCH, WAIT, INSUFFICIENT_DATA. Never BUY/SELL, never a
numeric score (see ENTRY_RESEARCH_HEURISTICS below) -- WAIT is the
conservative default, and GOOD_SETUP requires several things to align at
once, not just "predicted price > current price".

This combination of factors has NOT been separately, historically validated
as an entry strategy yet -- see docs/ENTRY_SETUP.md and
ENTRY_SETUP_DISCLAIMER below. Treat v1 thresholds as heuristic starting
points for research, not proven cutoffs.
"""
from __future__ import annotations

from dataclasses import dataclass

ENTRY_SETUP_VERSION = "entry-v1"

GOOD_SETUP = "GOOD_SETUP"
WATCH = "WATCH"
WAIT = "WAIT"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

ENTRY_SETUP_DISCLAIMER = (
    "Entry Setup is a research aid based on the current model forecast and technical context. "
    "Its performance as an entry strategy has not been separately validated and is still being evaluated."
)


@dataclass(frozen=True)
class EntryResearchHeuristics:
    """Heuristic research thresholds -- NOT ML-trained thresholds. Deliberately
    centralized here (not scattered across callers) so they can be reviewed,
    tuned, and versioned as one unit. Changing any value here should bump
    ENTRY_SETUP_VERSION so old snapshots stay attributable to the rules that
    actually produced them."""

    min_expected_upside_pct_for_good_setup: float = 3.0
    min_room_to_resistance_pct_for_good_setup: float = 3.0
    min_research_reward_risk_for_good_setup: float = 1.5
    max_support_distance_pct_for_good_setup: float = 12.0
    watch_min_expected_upside_pct: float = 1.0
    watch_min_room_to_resistance_pct: float = 1.5


DEFAULT_HEURISTICS = EntryResearchHeuristics()


@dataclass(frozen=True)
class EntrySetupReason:
    symbol: str  # "check" | "cross" | "warning"
    text: str

    def to_dict(self) -> dict:
        return {"symbol": self.symbol, "text": self.text}


@dataclass(frozen=True)
class EntrySetupResult:
    state: str
    version: str
    reasons: list[EntrySetupReason]
    summary: str
    expected_upside_pct: float | None = None
    support_distance_pct: float | None = None
    resistance_room_pct: float | None = None
    potential_reward: float | None = None
    potential_risk: float | None = None
    research_reward_risk: float | None = None
    reward_target_price: float | None = None
    resistance_below_target: bool = False

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "version": self.version,
            "reasons": [r.to_dict() for r in self.reasons],
            "summary": self.summary,
            "expected_upside_pct": self.expected_upside_pct,
            "support_distance_pct": self.support_distance_pct,
            "resistance_room_pct": self.resistance_room_pct,
            "potential_reward": self.potential_reward,
            "potential_risk": self.potential_risk,
            "research_reward_risk": self.research_reward_risk,
            "reward_target_price": self.reward_target_price,
            "resistance_below_target": self.resistance_below_target,
            "disclaimer": ENTRY_SETUP_DISCLAIMER,
        }


def _insufficient_data(reason_text: str) -> EntrySetupResult:
    return EntrySetupResult(
        state=INSUFFICIENT_DATA,
        version=ENTRY_SETUP_VERSION,
        reasons=[EntrySetupReason("cross", reason_text)],
        summary=reason_text,
    )


def evaluate_entry_setup(
    *,
    signal_status: str,
    current_price: float | None,
    predicted_price: float | None,
    support: float | None,
    resistance: float | None,
    buyer_pressure: str | None = None,
    heuristics: EntryResearchHeuristics = DEFAULT_HEURISTICS,
) -> EntrySetupResult:
    """Pure function -- no DB access, no ML inference. Callers decide what
    "current_price" means: the frozen prediction start price (for an
    immutable snapshot saved alongside an official prediction) or a fresh
    live quote (for an on-demand "right now" view). Either is valid; they
    answer slightly different questions and must never be confused."""
    if current_price is None or current_price <= 0 or predicted_price is None:
        return _insufficient_data("Current or predicted price is not available yet.")
    if support is None or resistance is None:
        return _insufficient_data("Support/resistance data is not available yet.")
    if support <= 0 or resistance <= 0 or support >= resistance:
        return _insufficient_data("Support/resistance data looks contradictory right now.")

    expected_upside_pct = (predicted_price - current_price) / current_price * 100
    support_distance_pct = (current_price - support) / current_price * 100
    resistance_room_pct = (resistance - current_price) / current_price * 100
    potential_risk = current_price - support
    potential_reward = predicted_price - current_price
    resistance_below_target = resistance < predicted_price
    research_reward_risk = (potential_reward / potential_risk) if potential_risk > 0 else None

    is_bullish = signal_status == "BULLISH"
    is_bearish = signal_status == "BEARISH"
    meaningful_upside = expected_upside_pct >= heuristics.min_expected_upside_pct_for_good_setup
    good_resistance_room = resistance_room_pct >= heuristics.min_room_to_resistance_pct_for_good_setup
    reasonable_support_distance = support_distance_pct <= heuristics.max_support_distance_pct_for_good_setup
    good_reward_risk = research_reward_risk is not None and research_reward_risk >= heuristics.min_research_reward_risk_for_good_setup
    buyer_acceptable = buyer_pressure in ("STRONG", "MODERATE")
    buyer_supportive = buyer_pressure == "STRONG"

    watch_upside = expected_upside_pct >= heuristics.watch_min_expected_upside_pct
    some_resistance_room = resistance_room_pct >= heuristics.watch_min_room_to_resistance_pct

    good_setup_criteria = [
        is_bullish,
        meaningful_upside,
        good_resistance_room,
        reasonable_support_distance,
        good_reward_risk,
        not resistance_below_target,
        buyer_acceptable,
    ]

    if all(good_setup_criteria):
        state = GOOD_SETUP
    elif not is_bearish and watch_upside and some_resistance_room:
        state = WATCH
    else:
        state = WAIT

    reasons = [
        EntrySetupReason("check" if is_bullish else "cross", "Validated bullish model signal" if is_bullish else "No validated bullish model signal"),
        EntrySetupReason(
            "check" if meaningful_upside else ("warning" if watch_upside else "cross"),
            f"Model target is {expected_upside_pct:+.1f}% vs current price",
        ),
        EntrySetupReason(
            "check" if reasonable_support_distance else "warning",
            f"Price is {support_distance_pct:.1f}% above support",
        ),
        EntrySetupReason(
            "check" if good_resistance_room else ("warning" if some_resistance_room else "cross"),
            f"{resistance_room_pct:.1f}% room before resistance",
        ),
        EntrySetupReason(
            "check" if buyer_supportive else ("warning" if buyer_acceptable else "cross"),
            f"Buyer pressure is {(buyer_pressure or 'UNKNOWN').lower()}",
        ),
    ]
    if research_reward_risk is not None:
        reasons.append(EntrySetupReason("check" if good_reward_risk else "warning", f"Research reward/risk is {research_reward_risk:.1f}x"))
    if resistance_below_target:
        reasons.append(EntrySetupReason("warning", f"Nearest resistance (${resistance:.2f}) sits below the model target (${predicted_price:.2f})"))

    summary = _summary_for(state, is_bullish, resistance_room_pct, meaningful_upside)

    return EntrySetupResult(
        state=state,
        version=ENTRY_SETUP_VERSION,
        reasons=reasons,
        summary=summary,
        expected_upside_pct=round(expected_upside_pct, 4),
        support_distance_pct=round(support_distance_pct, 4),
        resistance_room_pct=round(resistance_room_pct, 4),
        potential_reward=round(potential_reward, 4),
        potential_risk=round(potential_risk, 4) if potential_risk is not None else None,
        research_reward_risk=round(research_reward_risk, 4) if research_reward_risk is not None else None,
        reward_target_price=round(predicted_price, 4),
        resistance_below_target=resistance_below_target,
    )


def _summary_for(state: str, is_bullish: bool, resistance_room_pct: float, meaningful_upside: bool) -> str:
    if state == GOOD_SETUP:
        return "Validated bullish signal, meaningful upside, and healthy room to resistance all line up."
    if state == WATCH:
        return "Some upside potential exists, but the setup has not met every requirement for a stronger signal yet."
    if not is_bullish:
        return "No validated bullish signal yet."
    if resistance_room_pct < 0:
        return "Price is too close to resistance for a clean setup right now."
    return "The technical setup does not currently support an entry."
