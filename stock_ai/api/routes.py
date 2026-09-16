from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from stock_ai.data.providers.errors import ProviderError
from stock_ai.data.providers.market import get_market_data_provider
from stock_ai.data.providers.news import get_news_provider
from stock_ai.config import get_settings
from stock_ai.db.session import get_db
from stock_ai.features.dataset import latest_features_for_ticker, latest_structure_for_ticker, load_price_history
from stock_ai.news.sentiment import FinBertSentimentAnalyzer
from stock_ai.news.services import analyze_unanalyzed_articles, list_articles, refresh_news, sentiment_summary
from stock_ai.schemas.alerts import AlertRuleCreate, AlertRuleRead, AlertStatus
from stock_ai.schemas.positions import PositionCreate, PositionRead, PositionUpdate
from stock_ai.schemas.stocks import RefreshAllResult, RefreshResult, StockCreate, StockDetail, StockRead
from stock_ai.services import price_history, watchlist
from stock_ai.services import alerts as alert_service
from stock_ai.services import positions as position_service
from stock_ai.services.explain import build_explanation
from stock_ai.services.model_performance import get_model_performance_summary
from stock_ai.services.model_review import model_review_status
from stock_ai.services.entry_setup import evaluate_entry_setup
from stock_ai.services.prediction import predict_multi_horizon
from stock_ai.services.prediction_history import backfill_outcomes, list_prediction_history, prediction_record_to_dict, record_prediction
from stock_ai.services.prediction_performance import model_live_performance, stock_live_performance
from stock_ai.services.daily_run_status import latest_daily_run_status
from stock_ai.services.quote_service import get_quote, get_quotes
from stock_ai.ml.champion import CHAMPION_HORIZONS
from stock_ai.schemas.stocks import normalize_ticker
from stock_ai.universe import daily_tracking_tickers


router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/stocks", response_model=list[StockRead])
def list_watchlist(db: Session = Depends(get_db)) -> list[StockRead]:
    return watchlist.list_stocks(db)


@router.post("/stocks", response_model=StockRead, status_code=status.HTTP_201_CREATED)
def add_stock(payload: StockCreate, db: Session = Depends(get_db)) -> StockRead:
    try:
        return watchlist.create_stock(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/stocks/{ticker}", response_model=StockDetail)
def get_stock(ticker: str, db: Session = Depends(get_db)) -> StockDetail:
    stock = watchlist.get_stock_detail(db, ticker)
    if not stock:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stock not found")
    return stock


@router.get("/stocks/{ticker}/features/latest")
def get_latest_features(ticker: str, db: Session = Depends(get_db)) -> dict:
    features = latest_features_for_ticker(db, ticker)
    if not features:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No feature-ready price history found")
    return features


_PRICE_HISTORY_RANGES = {"1M": 30, "3M": 90, "6M": 182, "1Y": 365, "5Y": 365 * 5}


@router.get("/stocks/{ticker}/prices")
def get_price_history(
    ticker: str,
    range: str = Query(default="6M", pattern="^(1M|3M|6M|1Y|5Y)$"),
    db: Session = Depends(get_db),
) -> list[dict]:
    days = _PRICE_HISTORY_RANGES[range]
    start_date = (datetime.now(timezone.utc) - timedelta(days=days)).date()
    prices = load_price_history(db, ticker=ticker, start_date=start_date)
    if prices.empty:
        return []
    return [
        {
            "date": row["date"].date().isoformat() if hasattr(row["date"], "date") else str(row["date"]),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": int(row["volume"]),
        }
        for _, row in prices.iterrows()
    ]


@router.get("/stocks/{ticker}/quote")
def get_stock_quote(ticker: str, db: Session = Depends(get_db)) -> dict:
    """Fresh CURRENT PRICE for display -- distinct from a prediction's frozen
    start price and from a completed daily PriceBar. Never fails outright:
    on a provider error this falls back to the latest stored price with
    is_stale=True."""
    provider = get_market_data_provider()
    return get_quote(db, provider, ticker).to_dict()


@router.get("/quotes")
def get_stock_quotes(tickers: str = Query(..., description="Comma-separated tickers, e.g. NVDA,AMD,MU"), db: Session = Depends(get_db)) -> dict:
    """Batch quotes -- one provider request for the whole list where the
    provider supports it, instead of one request per card. One ticker's
    failure never fails the others."""
    requested = [t.strip() for t in tickers.split(",") if t.strip()]
    provider = get_market_data_provider()
    results = get_quotes(db, provider, requested)
    return {"quotes": {ticker: result.to_dict() for ticker, result in results.items()}}


@router.get("/stocks/{ticker}/structure")
def get_latest_structure(ticker: str, db: Session = Depends(get_db)) -> dict:
    structure = latest_structure_for_ticker(db, ticker)
    if not structure:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No structure-ready price history found")
    return structure


@router.get("/stocks/{ticker}/prediction")
def get_prediction(
    ticker: str,
    store: bool = Query(default=False, description="Persist this prediction snapshot to prediction history"),
    db: Session = Depends(get_db),
) -> dict:
    try:
        result = predict_multi_horizon(db, ticker)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Champion models are not trained yet. Run scripts/train_champion_models.py first.",
        ) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No feature-ready price history found")

    if store:
        for horizon_signal in result["predictions"].values():
            if horizon_signal is not None:
                record_prediction(db, horizon_signal)

    return result


@router.get("/stocks/{ticker}/analysis")
def get_analysis(
    ticker: str,
    store: bool = Query(default=False, description="Persist this prediction snapshot to prediction history"),
    db: Session = Depends(get_db),
) -> dict:
    prediction = get_prediction(ticker, store=store, db=db)
    structure = latest_structure_for_ticker(db, ticker)
    primary_signal = prediction["predictions"].get(prediction["primary_research_horizon"])
    explanation = build_explanation(structure, primary_signal)
    return {**prediction, "structure": structure, "explanation": explanation}


@router.get("/stocks/{ticker}/news")
def get_news(ticker: str, limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db)) -> list[dict]:
    return [_article_to_dict(article) for article in list_articles(db, ticker, limit=limit)]


@router.post("/stocks/{ticker}/news/refresh")
def refresh_stock_news(
    ticker: str,
    days: int = Query(default=14, ge=1, le=365),
    analyze_sentiment: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> dict:
    provider = get_news_provider()
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    result = refresh_news(db, provider, ticker, start, end)
    if analyze_sentiment:
        analyzer = FinBertSentimentAnalyzer(get_settings().finbert_model_name)
        result["articles_analyzed"] = analyze_unanalyzed_articles(db, analyzer, ticker=ticker)
    return result


@router.get("/stocks/{ticker}/sentiment")
def get_sentiment(ticker: str, db: Session = Depends(get_db)) -> dict:
    summary = sentiment_summary(db, ticker)
    if summary["last_updated"] is not None and hasattr(summary["last_updated"], "isoformat"):
        summary["last_updated"] = summary["last_updated"].isoformat()
    return summary


@router.get("/stocks/{ticker}/events")
def get_events(ticker: str, limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db)) -> list[dict]:
    return [
        {
            "ticker": article.ticker,
            "published_at": article.published_at.isoformat(),
            "headline": article.headline,
            "event_category": article.event_category,
            "url": article.url,
        }
        for article in list_articles(db, ticker, limit=limit)
    ]


@router.delete("/stocks/{ticker}", status_code=status.HTTP_204_NO_CONTENT)
def remove_stock(ticker: str, db: Session = Depends(get_db)) -> Response:
    deleted = watchlist.delete_stock(db, ticker)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stock not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/stocks/{ticker}/refresh", response_model=RefreshResult)
def refresh_stock(
    ticker: str,
    years: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
) -> RefreshResult:
    provider = get_market_data_provider()
    try:
        result = price_history.refresh_history(db, provider=provider, ticker=ticker, years=years)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not fetch price data for {ticker.upper()} from the market data provider. Check the symbol and try again.",
        ) from exc
    # Fresh price data may make previously-pending predictions eligible for
    # resolution -- never retrains anything, only fills outcome fields.
    backfill_outcomes(db, ticker=ticker)
    return result


@router.post("/refresh/all", response_model=RefreshAllResult)
def refresh_all(
    years: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
) -> RefreshAllResult:
    provider = get_market_data_provider()
    result = price_history.refresh_all(db, provider=provider, years=years)
    backfill_outcomes(db)
    return result


@router.post("/predictions/resolve-outcomes")
def resolve_prediction_outcomes(ticker: str | None = Query(default=None), db: Session = Depends(get_db)) -> dict:
    return backfill_outcomes(db, ticker=ticker)


@router.get("/stocks/{ticker}/predictions/history")
def get_prediction_history(
    ticker: str,
    horizon: str | None = Query(default=None, pattern="^(5d|10d|15d)$"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[dict]:
    records = list_prediction_history(db, ticker=ticker, horizon=horizon, limit=limit)
    return [prediction_record_to_dict(record) for record in records]


@router.get("/stocks/{ticker}/predictions/performance")
def get_prediction_performance(ticker: str, db: Session = Depends(get_db)) -> dict:
    return stock_live_performance(db, ticker)


@router.get("/stocks/{ticker}/entry-setup")
def get_entry_setup(ticker: str, horizon: str = Query(default="5d", pattern="^(5d|10d|15d)$"), db: Session = Depends(get_db)) -> dict:
    """LIVE, on-demand Entry Setup -- recomputed fresh every call using
    today's quote, never persisted. Distinct from the immutable
    entry_setup_state saved alongside the official prediction snapshot
    (see prediction_record_to_dict()), which reflects conditions at the
    moment that snapshot was created and is never recomputed afterward."""
    history = list_prediction_history(db, ticker=ticker, horizon=horizon, limit=1)
    if not history:
        return {"ticker": normalize_ticker(ticker), "horizon": horizon, "available": False, "reason": f"No current {horizon} forecast available."}
    latest = history[0]

    structure = latest_structure_for_ticker(db, ticker)
    provider = get_market_data_provider()
    quote = get_quote(db, provider, ticker)

    model_expected_move_pct = (float(latest.model_target_price) - float(latest.current_price)) / float(latest.current_price) * 100 if latest.current_price else None

    result = evaluate_entry_setup(
        signal_status=latest.signal_status,
        current_price=quote.price,
        predicted_price=float(latest.model_target_price),
        support=structure.get("nearest_support") if structure else None,
        resistance=structure.get("nearest_resistance") if structure else None,
        buyer_pressure=structure.get("buyer_pressure") if structure else None,
    )

    return {
        "ticker": normalize_ticker(ticker),
        "horizon": horizon,
        "available": True,
        "prediction_date": latest.prediction_date.isoformat(),
        "prediction_start_price": float(latest.current_price),
        "predicted_price": float(latest.model_target_price),
        "model_expected_move_pct": round(model_expected_move_pct, 4) if model_expected_move_pct is not None else None,
        "signal_status": latest.signal_status,
        "current_quote": quote.to_dict(),
        "entry_setup": result.to_dict(),
    }


@router.get("/models/performance")
def get_models_performance() -> dict:
    return get_model_performance_summary()


@router.get("/models/live-performance")
def get_models_live_performance(db: Session = Depends(get_db)) -> dict:
    return model_live_performance(db)


@router.get("/models/review-status")
def get_model_review_status(db: Session = Depends(get_db)) -> dict:
    return model_review_status(db)


def _daily_tracking_config() -> dict:
    """Live-config snapshot (not stored on the run row) so the UI always
    reflects the CURRENT DAILY_TRACKING_TICKERS value, even for an older run
    logged before the list last changed."""
    tracked = [normalize_ticker(t) for t in daily_tracking_tickers()]
    return {
        "tracked_tickers": tracked,
        "tracked_ticker_count": len(tracked),
        "predictions_per_market_day": len(tracked) * len(CHAMPION_HORIZONS),
    }


@router.get("/system/daily-run-status")
def get_daily_run_status(db: Session = Depends(get_db)) -> dict:
    status = latest_daily_run_status(db)
    tracking_config = _daily_tracking_config()
    if status is None:
        return {"status": "NEVER_RUN", **tracking_config}
    return {**status, **tracking_config}


@router.get("/positions", response_model=list[PositionRead])
def list_positions(db: Session = Depends(get_db)) -> list[PositionRead]:
    return position_service.list_positions(db)


@router.post("/positions", response_model=PositionRead, status_code=status.HTTP_201_CREATED)
def create_position(payload: PositionCreate, db: Session = Depends(get_db)) -> PositionRead:
    return position_service.create_position(db, payload)


@router.patch("/positions/{position_id}", response_model=PositionRead)
def update_position(position_id: int, payload: PositionUpdate, db: Session = Depends(get_db)) -> PositionRead:
    position = position_service.update_position(db, position_id, payload)
    if not position:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Position not found")
    return position


@router.delete("/positions/{position_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_position(position_id: int, db: Session = Depends(get_db)) -> Response:
    deleted = position_service.delete_position(db, position_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Position not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/positions/{position_id}/current-price")
def get_position_current_price(position_id: int, db: Session = Depends(get_db)) -> dict:
    position = position_service.get_position(db, position_id)
    if not position:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Position not found")
    price = position_service.latest_price_for(db, position.ticker)
    return {"ticker": position.ticker, "current_price": price}


@router.get("/alerts", response_model=list[AlertRuleRead])
def list_alerts(ticker: str | None = Query(default=None), db: Session = Depends(get_db)) -> list[AlertRuleRead]:
    return alert_service.list_alert_rules(db, ticker=ticker)


@router.post("/alerts", response_model=AlertRuleRead, status_code=status.HTTP_201_CREATED)
def create_alert(payload: AlertRuleCreate, db: Session = Depends(get_db)) -> AlertRuleRead:
    return alert_service.create_alert_rule(db, ticker=payload.ticker, alert_type=payload.alert_type, threshold_price=payload.threshold_price)


@router.delete("/alerts/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_alert(alert_id: int, db: Session = Depends(get_db)) -> Response:
    deleted = alert_service.delete_alert_rule(db, alert_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/alerts/check", response_model=list[AlertStatus])
def check_alerts(ticker: str | None = Query(default=None), db: Session = Depends(get_db)) -> list[AlertStatus]:
    rules = alert_service.list_alert_rules(db, ticker=ticker)
    return [AlertStatus(**alert_service.evaluate_alert_rule(db, rule)) for rule in rules if rule.is_active]


def _article_to_dict(article) -> dict:
    sentiment = article.sentiment
    return {
        "id": article.id,
        "ticker": article.ticker,
        "headline": article.headline,
        "summary": article.summary,
        "source": article.source,
        "published_at": article.published_at.isoformat(),
        "url": article.url,
        "provider": article.provider,
        "external_id": article.external_id,
        "event_category": article.event_category,
        "sentiment": None
        if sentiment is None
        else {
            "label": sentiment.sentiment_label,
            "positive_probability": float(sentiment.positive_probability),
            "neutral_probability": float(sentiment.neutral_probability),
            "negative_probability": float(sentiment.negative_probability),
            "sentiment_score": float(sentiment.sentiment_score),
            "model": sentiment.sentiment_model,
            "model_version": sentiment.sentiment_model_version,
            "analyzed_at": sentiment.analyzed_at.isoformat(),
        },
    }
