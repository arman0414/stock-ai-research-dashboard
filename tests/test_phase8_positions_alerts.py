from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from stock_ai.models.alerts import AlertRule
from stock_ai.schemas.alerts import AlertRuleCreate
from stock_ai.schemas.positions import PositionCreate
from stock_ai.services import alerts as alert_service
from stock_ai.services import positions as position_service
from stock_ai.services.explain import build_explanation
from stock_ai.services.market_context import _relative_label


def test_create_and_list_positions(db_session) -> None:
    payload = PositionCreate(ticker="nvda", shares=Decimal("20"), purchase_price=Decimal("190"), purchase_date=date(2026, 1, 5), my_target_price=Decimal("240"))
    position = position_service.create_position(db_session, payload)

    assert position.ticker == "NVDA"  # normalized
    rows = position_service.list_positions(db_session)
    assert len(rows) == 1
    assert rows[0].my_target_price == Decimal("240")


def test_update_position_partial_fields(db_session) -> None:
    payload = PositionCreate(ticker="AMD", shares=Decimal("10"), purchase_price=Decimal("100"), purchase_date=date(2026, 1, 5))
    position = position_service.create_position(db_session, payload)

    from stock_ai.schemas.positions import PositionUpdate

    updated = position_service.update_position(db_session, position.id, PositionUpdate(shares=Decimal("15")))
    assert updated.shares == Decimal("15")
    assert updated.purchase_price == Decimal("100")  # untouched


def test_delete_position(db_session) -> None:
    payload = PositionCreate(ticker="MU", shares=Decimal("5"), purchase_price=Decimal("50"), purchase_date=date(2026, 1, 5))
    position = position_service.create_position(db_session, payload)

    assert position_service.delete_position(db_session, position.id) is True
    assert position_service.delete_position(db_session, position.id) is False


def test_position_target_and_model_target_are_independent_fields() -> None:
    """my_target_price on a Position must never be conflated with a model
    prediction's model_target_price -- they live in entirely separate
    schemas/tables, which this test pins down structurally."""
    payload = PositionCreate(ticker="NVDA", shares=Decimal("1"), purchase_price=Decimal("100"), purchase_date=date(2026, 1, 1), my_target_price=Decimal("999"))
    assert "model_target_price" not in payload.model_dump()
    assert payload.my_target_price == Decimal("999")


def test_alert_rule_create_rejects_unknown_type() -> None:
    with pytest.raises(ValidationError):
        AlertRuleCreate(ticker="NVDA", alert_type="NOT_A_REAL_TYPE")


def test_alert_rule_create_normalizes_ticker_and_type() -> None:
    rule = AlertRuleCreate(ticker="nvda", alert_type="my_target_price", threshold_price=Decimal("240"))
    assert rule.ticker == "NVDA"
    assert rule.alert_type == "MY_TARGET_PRICE"


def test_my_target_price_alert_triggers_when_price_at_or_above_threshold(db_session) -> None:
    rule = alert_service.create_alert_rule(db_session, ticker="NVDA", alert_type="MY_TARGET_PRICE", threshold_price=Decimal("200"))

    from stock_ai.models.market_data import PriceBar

    db_session.add(PriceBar(ticker="NVDA", date=date(2026, 1, 10), open=200, high=205, low=199, close=205, adjusted_close=205, volume=1000, source="test"))
    db_session.commit()

    result = alert_service.evaluate_alert_rule(db_session, rule)
    assert result["is_triggered"] is True
    assert "NVDA" in result["message"]
    assert result["current_price"] == Decimal("205")


def test_my_stop_loss_alert_does_not_trigger_above_threshold(db_session) -> None:
    rule = alert_service.create_alert_rule(db_session, ticker="AMD", alert_type="MY_STOP_LOSS", threshold_price=Decimal("100"))

    from stock_ai.models.market_data import PriceBar

    db_session.add(PriceBar(ticker="AMD", date=date(2026, 1, 10), open=150, high=155, low=149, close=150, adjusted_close=150, volume=1000, source="test"))
    db_session.commit()

    result = alert_service.evaluate_alert_rule(db_session, rule)
    assert result["is_triggered"] is False


def test_delete_alert_rule(db_session) -> None:
    rule = alert_service.create_alert_rule(db_session, ticker="MU", alert_type="MY_TARGET_PRICE", threshold_price=Decimal("50"))
    assert alert_service.delete_alert_rule(db_session, rule.id) is True
    assert alert_service.delete_alert_rule(db_session, rule.id) is False


def test_build_explanation_uses_only_provided_structure_data() -> None:
    structure = {
        "important_observations": ["Price/volume behavior suggests buyers recently defended the support area."],
        "market_structure": "BULLISH",
        "distance_to_resistance": 0.10,
        "breakout_status": "RANGE_BOUND",
    }
    signal = {"classification": {"calibrated_probability": 0.70, "signal_status": "BULLISH"}}
    explanation = build_explanation(structure, signal)
    assert "Price/volume behavior suggests buyers recently defended the support area." in explanation["positives"]
    assert any("bullish" in item.lower() for item in explanation["positives"])
    assert explanation["risks"] == []  # no low-confidence or nearby-resistance risk triggered


def test_build_explanation_flags_low_confidence_and_no_strong_signal() -> None:
    signal = {"classification": {"calibrated_probability": 0.40, "signal_status": "NO_STRONG_SIGNAL"}}
    explanation = build_explanation(None, signal)
    assert any("confidence is limited" in item for item in explanation["risks"])
    assert any("validated confidence requirements" in item for item in explanation["risks"])


def test_build_explanation_handles_missing_structure_and_signal() -> None:
    explanation = build_explanation(None, None)
    assert explanation == {"positives": [], "risks": []}


def test_market_context_relative_label_thresholds() -> None:
    assert _relative_label(0.05) == "OUTPERFORMING"
    assert _relative_label(-0.05) == "UNDERPERFORMING"
    assert _relative_label(0.0) == "NEUTRAL"
    assert _relative_label(None) == "NEUTRAL"
