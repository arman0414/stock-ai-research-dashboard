"""Phase 8: minimal in-app alert evaluation.

Alerts are evaluated on demand (when the frontend asks), not by a background
scheduler. Model-based alert types read the existing champion prediction
service and price-action structure summary -- they never re-run or retrain
anything. No email/SMS delivery here yet; only IN_APP evaluation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from stock_ai.features.dataset import latest_features_for_ticker, latest_structure_for_ticker
from stock_ai.models.alerts import AlertRule
from stock_ai.models.market_data import PriceBar
from stock_ai.models.predictions import PredictionRecord
from stock_ai.news.services import sentiment_summary
from stock_ai.schemas.stocks import normalize_ticker
from stock_ai.services.prediction import predict_horizon


def list_alert_rules(db: Session, ticker: str | None = None) -> list[AlertRule]:
    query = select(AlertRule).order_by(AlertRule.created_at.desc())
    if ticker:
        query = query.where(AlertRule.ticker == normalize_ticker(ticker))
    return list(db.scalars(query))


def create_alert_rule(db: Session, ticker: str, alert_type: str, threshold_price: Decimal | None) -> AlertRule:
    rule = AlertRule(ticker=normalize_ticker(ticker), alert_type=alert_type, threshold_price=threshold_price, is_active=True)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def delete_alert_rule(db: Session, alert_id: int) -> bool:
    rule = db.get(AlertRule, alert_id)
    if not rule:
        return False
    db.delete(rule)
    db.commit()
    return True


def evaluate_alert_rule(db: Session, rule: AlertRule) -> dict:
    current_price = _latest_close(db, rule.ticker)
    model_signal = _latest_5d_signal(db, rule.ticker)

    triggered = False
    message: str | None = None

    if rule.alert_type == "MY_TARGET_PRICE":
        if rule.threshold_price is not None and current_price is not None and current_price >= rule.threshold_price:
            triggered = True
            message = f"{rule.ticker} reached your target of ${rule.threshold_price}"

    elif rule.alert_type == "MY_STOP_LOSS":
        if rule.threshold_price is not None and current_price is not None and current_price <= rule.threshold_price:
            triggered = True
            message = f"{rule.ticker} hit your stop loss of ${rule.threshold_price}"

    elif rule.alert_type == "BULLISH_SIGNAL_APPEARED":
        if model_signal == "BULLISH":
            triggered = True
            message = f"{rule.ticker} 5D model signal is now BULLISH"

    elif rule.alert_type == "MODEL_SIGNAL_CHANGED":
        previous_signal = _previous_5d_signal(db, rule.ticker)
        if previous_signal is not None and model_signal is not None and previous_signal != model_signal:
            triggered = True
            message = f"{rule.ticker} 5D model signal changed from {previous_signal} to {model_signal}"

    elif rule.alert_type in ("MAJOR_POSITIVE_NEWS", "MAJOR_NEGATIVE_NEWS"):
        summary = sentiment_summary(db, rule.ticker)
        if rule.alert_type == "MAJOR_POSITIVE_NEWS" and summary["positive"] >= 3 and summary["sentiment_direction"] == "POSITIVE":
            triggered = True
            message = f"{rule.ticker} has {summary['positive']} recent positive news articles"
        if rule.alert_type == "MAJOR_NEGATIVE_NEWS" and summary["negative"] >= 3 and summary["sentiment_direction"] == "NEGATIVE":
            triggered = True
            message = f"{rule.ticker} has {summary['negative']} recent negative news articles"

    elif rule.alert_type == "UNUSUAL_VOLUME":
        features = latest_features_for_ticker(db, rule.ticker)
        relative_volume = features.get("relative_volume") if features else None
        if relative_volume is not None and relative_volume >= 2.0:
            triggered = True
            message = f"{rule.ticker} volume is {relative_volume:.1f}x its recent average"

    elif rule.alert_type == "SUPPORT_BREAK":
        structure = latest_structure_for_ticker(db, rule.ticker)
        if structure and structure["breakout_status"] == "BREAKDOWN":
            triggered = True
            message = f"{rule.ticker} broke below its nearest support"

    elif rule.alert_type == "RESISTANCE_BREAKOUT":
        structure = latest_structure_for_ticker(db, rule.ticker)
        if structure and structure["breakout_status"] == "BREAKOUT":
            triggered = True
            message = f"{rule.ticker} broke above its nearest resistance"

    if triggered:
        rule.last_triggered_at = datetime.now(timezone.utc)
        rule.last_triggered_message = message
        db.commit()
        db.refresh(rule)

    return {
        "rule": rule,
        "is_triggered": triggered,
        "message": message,
        "current_price": current_price,
        "model_5d_signal": model_signal,
    }


def _latest_close(db: Session, ticker: str) -> Decimal | None:
    bar = db.scalar(select(PriceBar).where(PriceBar.ticker == normalize_ticker(ticker)).order_by(PriceBar.date.desc()).limit(1))
    return bar.close if bar else None


def _latest_5d_signal(db: Session, ticker: str) -> str | None:
    try:
        signal = predict_horizon(db, ticker, "5d")
    except FileNotFoundError:
        return None
    return signal["classification"]["signal_status"] if signal else None


def _previous_5d_signal(db: Session, ticker: str) -> str | None:
    rows = list(
        db.scalars(
            select(PredictionRecord)
            .where(PredictionRecord.ticker == normalize_ticker(ticker), PredictionRecord.horizon == "5d")
            .order_by(PredictionRecord.prediction_date.desc())
            .limit(2)
        )
    )
    if len(rows) < 2:
        return None
    return rows[1].signal_status
