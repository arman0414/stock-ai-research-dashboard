"""ENTRY SETUP: a research interpretation layer on top of existing model
outputs -- never a new model, never BUY/SELL, never a numeric score. These
tests prove the v1 heuristic rules produce the states/labels the product
requires, and that persistence never touches or is touched by anything
else (frozen snapshot immutability, no impact on prediction values).
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from stock_ai.models.predictions import PredictionRecord
from stock_ai.services.entry_setup import (
    ENTRY_SETUP_VERSION,
    GOOD_SETUP,
    INSUFFICIENT_DATA,
    WAIT,
    WATCH,
    EntryResearchHeuristics,
    evaluate_entry_setup,
)
from stock_ai.services.prediction_history import backfill_outcomes, record_prediction


def test_bullish_signal_with_reasonable_upside_and_healthy_setup_is_good_setup():
    result = evaluate_entry_setup(
        signal_status="BULLISH",
        current_price=210.0,
        predicted_price=220.0,
        support=206.0,
        resistance=225.0,
        buyer_pressure="STRONG",
    )
    assert result.state == GOOD_SETUP
    assert result.version == ENTRY_SETUP_VERSION
    assert result.expected_upside_pct == pytest.approx(4.7619, abs=1e-3)
    assert result.resistance_room_pct == pytest.approx(7.1429, abs=1e-3)
    assert result.support_distance_pct == pytest.approx(1.9048, abs=1e-3)
    assert result.research_reward_risk == pytest.approx(2.5, abs=1e-3)


def test_no_strong_signal_never_becomes_good_setup_by_itself():
    """Predicted price > current price is not enough on its own -- a
    NO_STRONG_SIGNAL validated signal must never produce GOOD_SETUP no
    matter how favorable the other numbers look."""
    result = evaluate_entry_setup(
        signal_status="NO_STRONG_SIGNAL",
        current_price=100.0,
        predicted_price=115.0,  # a large predicted upside
        support=90.0,
        resistance=140.0,  # plenty of room
        buyer_pressure="STRONG",
    )
    assert result.state != GOOD_SETUP


def test_negative_predicted_upside_results_in_wait():
    result = evaluate_entry_setup(
        signal_status="BULLISH",
        current_price=210.0,
        predicted_price=205.0,  # predicted price BELOW current
        support=200.0,
        resistance=225.0,
        buyer_pressure="STRONG",
    )
    assert result.state == WAIT
    assert result.expected_upside_pct < 0


def test_resistance_extremely_close_downgrades_from_good_setup():
    """Same bullish setup as the GOOD_SETUP case, except resistance sits
    right at the current price -- must not stay GOOD_SETUP."""
    result = evaluate_entry_setup(
        signal_status="BULLISH",
        current_price=210.0,
        predicted_price=220.0,
        support=206.0,
        resistance=210.8,  # only ~0.4% of room
        buyer_pressure="STRONG",
    )
    assert result.state != GOOD_SETUP


def test_missing_support_or_resistance_is_conservative_insufficient_data():
    result = evaluate_entry_setup(signal_status="BULLISH", current_price=210.0, predicted_price=220.0, support=None, resistance=225.0)
    assert result.state == INSUFFICIENT_DATA
    result2 = evaluate_entry_setup(signal_status="BULLISH", current_price=210.0, predicted_price=220.0, support=206.0, resistance=None)
    assert result2.state == INSUFFICIENT_DATA


def test_contradictory_support_and_resistance_is_insufficient_data():
    result = evaluate_entry_setup(signal_status="BULLISH", current_price=210.0, predicted_price=220.0, support=230.0, resistance=200.0)
    assert result.state == INSUFFICIENT_DATA


def test_watch_state_for_a_borderline_but_interesting_setup():
    result = evaluate_entry_setup(
        signal_status="NO_STRONG_SIGNAL",
        current_price=100.0,
        predicted_price=104.0,
        support=97.0,
        resistance=108.0,
        buyer_pressure="MODERATE",
    )
    assert result.state == WATCH


def test_reward_risk_calculation_matches_the_documented_example():
    # Current $210, Support $205, Model Target $220 -> risk $5, reward $10 -> 2.0x
    result = evaluate_entry_setup(signal_status="BULLISH", current_price=210.0, predicted_price=220.0, support=205.0, resistance=230.0, buyer_pressure="STRONG")
    assert result.potential_risk == pytest.approx(5.0)
    assert result.potential_reward == pytest.approx(10.0)
    assert result.research_reward_risk == pytest.approx(2.0)


def test_resistance_below_model_target_is_flagged_and_weakens_the_setup():
    result = evaluate_entry_setup(signal_status="BULLISH", current_price=210.0, predicted_price=225.0, support=206.0, resistance=219.0, buyer_pressure="STRONG")
    assert result.resistance_below_target is True
    assert result.state != GOOD_SETUP  # the model target sits beyond a real resistance level -- must not be GOOD_SETUP


def test_heuristics_are_configurable_not_hardcoded():
    lenient = EntryResearchHeuristics(min_expected_upside_pct_for_good_setup=0.1, min_room_to_resistance_pct_for_good_setup=0.1, min_research_reward_risk_for_good_setup=0.1)
    result = evaluate_entry_setup(
        signal_status="BULLISH",
        current_price=100.0,
        predicted_price=100.5,
        support=99.0,
        resistance=101.0,
        buyer_pressure="STRONG",
        heuristics=lenient,
    )
    assert result.state == GOOD_SETUP  # would not qualify under the default (stricter) heuristics


def test_default_heuristics_reject_the_same_marginal_case():
    result = evaluate_entry_setup(signal_status="BULLISH", current_price=100.0, predicted_price=100.5, support=99.0, resistance=101.0, buyer_pressure="STRONG")
    assert result.state != GOOD_SETUP


def test_never_produces_a_numeric_score_or_buy_sell_label():
    result = evaluate_entry_setup(signal_status="BULLISH", current_price=210.0, predicted_price=220.0, support=206.0, resistance=225.0, buyer_pressure="STRONG")
    assert result.state in (GOOD_SETUP, WATCH, WAIT, INSUFFICIENT_DATA)
    assert "BUY" not in result.summary.upper()
    assert "SELL" not in result.summary.upper()


# ---------------------------------------------------------------------------
# Persistence: saved once with the official prediction, immutable afterward.
# ---------------------------------------------------------------------------


def _signal_with_setup(ticker="NVDA", horizon="5d", as_of="2026-09-15", current_price=210.0, predicted_price=220.0, support=206.0, resistance=225.0, signal_status="BULLISH", buyer_pressure="STRONG"):
    return {
        "ticker": ticker,
        "as_of": as_of,
        "horizon": horizon,
        "current_price": current_price,
        "classification": {"direction": "UP", "raw_probability": 0.7, "calibrated_probability": 0.65, "signal_status": signal_status, "confidence": "HIGH"},
        "regression": {"predicted_return": (predicted_price / current_price) - 1, "model_target_price": predicted_price, "uncertainty_low": current_price * 0.9, "uncertainty_high": current_price * 1.15},
        "setup": {"quality": "STRONG", "buyer_pressure": buyer_pressure, "seller_pressure": "WEAK", "support": support, "resistance": resistance},
        "model": {"classification_version": "random_forest_5d_seed42", "regression_version": "random_forest_raw_5d", "calibration_method": "sigmoid"},
    }


def test_entry_setup_is_saved_with_the_official_prediction_snapshot(db_session):
    record_prediction(db_session, _signal_with_setup(), prediction_source="LIVE_DAILY")
    row = db_session.scalar(select(PredictionRecord).where(PredictionRecord.ticker == "NVDA"))
    assert row.entry_setup_state == GOOD_SETUP
    assert row.entry_setup_version == ENTRY_SETUP_VERSION
    assert row.entry_setup_reasons_json is not None
    import json

    reasons = json.loads(row.entry_setup_reasons_json)
    assert len(reasons) > 0
    assert all("symbol" in r and "text" in r for r in reasons)


def test_entry_setup_snapshot_is_not_altered_by_outcome_resolution(db_session):
    """Once saved, entry_setup_state must never change -- not even after the
    prediction resolves and the real outcome is known."""
    record_prediction(db_session, _signal_with_setup(current_price=100.0, predicted_price=105.0, support=95.0, resistance=110.0), prediction_source="LIVE_DAILY")
    row = db_session.scalar(select(PredictionRecord).where(PredictionRecord.ticker == "NVDA"))
    original_state = row.entry_setup_state
    original_reasons = row.entry_setup_reasons_json

    # Mature the prediction with an outcome that has NOTHING to do with the
    # entry setup evaluation (the stock crashed) -- this must not rewrite
    # the original entry_setup_state after the fact.
    for offset in range(1, 6):
        db_session.add(_price_bar("NVDA", date.fromordinal(date(2026, 9, 15).toordinal() + offset), 50.0))
    db_session.commit()
    backfill_outcomes(db_session, ticker="NVDA")

    db_session.refresh(row)
    assert row.outcome_status == "RESOLVED"
    assert row.entry_setup_state == original_state
    assert row.entry_setup_reasons_json == original_reasons


def test_entry_setup_version_is_stored_and_distinguishable_from_a_future_version(db_session):
    record_prediction(db_session, _signal_with_setup(ticker="AMD"), prediction_source="LIVE_DAILY")
    row = db_session.scalar(select(PredictionRecord).where(PredictionRecord.ticker == "AMD"))
    assert row.entry_setup_version == "entry-v1"


def test_entry_setup_never_changes_the_stored_prediction_values(db_session):
    """Entry Setup is a read-only interpretation layer -- it must never
    alter predicted_return, model_target_price, or signal_status."""
    signal = _signal_with_setup(current_price=210.0, predicted_price=220.0)
    record_prediction(db_session, signal, prediction_source="LIVE_DAILY")
    row = db_session.scalar(select(PredictionRecord).where(PredictionRecord.ticker == "NVDA"))
    assert float(row.model_target_price) == pytest.approx(220.0)
    assert float(row.current_price) == pytest.approx(210.0)
    assert row.signal_status == "BULLISH"


def test_missing_setup_data_in_the_signal_is_handled_conservatively(db_session):
    """Older/simpler signal dicts without a "setup" key (as used throughout
    the existing test suite) must never crash prediction recording -- they
    fall back to INSUFFICIENT_DATA."""
    signal = _signal_with_setup()
    del signal["setup"]
    record_prediction(db_session, signal, prediction_source="LIVE_DAILY")
    row = db_session.scalar(select(PredictionRecord).where(PredictionRecord.ticker == "NVDA"))
    assert row.entry_setup_state == INSUFFICIENT_DATA


def _price_bar(ticker: str, on: date, close: float):
    from stock_ai.models.market_data import PriceBar

    return PriceBar(ticker=ticker, date=on, open=close, high=close, low=close, close=close, adjusted_close=close, volume=1000, source="test")
