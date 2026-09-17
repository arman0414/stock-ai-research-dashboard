from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, balanced_accuracy_score, mean_absolute_error, precision_score
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from stock_ai.config import PROJECT_ROOT
from stock_ai.features.context import CONTEXT_FEATURE_COLUMNS, add_context_features
from stock_ai.features.dataset import build_feature_dataset, price_bars_to_dataframe
from stock_ai.features.targets import DEFAULT_HORIZONS, DirectionThresholds, add_future_targets
from stock_ai.ml.benchmark import _summarize_training_result
from stock_ai.ml.config import ModelConfig
from stock_ai.ml.training import train_horizon_models
from stock_ai.models.market_data import PriceBar
from stock_ai.schemas.stocks import normalize_ticker
from stock_ai.universe import FOCUS_STOCKS, REFERENCE_ASSETS, REFERENCE_UNIVERSE, SPECIALIZED_TRAINING_UNIVERSE
from stock_ai.utils.json_safe import write_json_file


MODEL_B = "technical_price_action"
MODEL_C = "technical_price_action_context"
TARGET_FIXED_3PCT = "fixed_3pct"
TARGET_HORIZON_SPECIFIC = "horizon_specific"
TARGET_VOLATILITY_ADJUSTED = "volatility_adjusted"
TARGET_MODES = (TARGET_FIXED_3PCT, TARGET_HORIZON_SPECIFIC, TARGET_VOLATILITY_ADJUSTED)
MIN_FOCUS_TEST_ROWS = 20

HORIZON_SPECIFIC_THRESHOLDS = {
    "5d": DirectionThresholds(up=0.02, down=-0.02),
    "10d": DirectionThresholds(up=0.03, down=-0.03),
    "15d": DirectionThresholds(up=0.04, down=-0.04),
    "21d": DirectionThresholds(up=0.05, down=-0.05),
    "63d": DirectionThresholds(up=0.08, down=-0.08),
}


def run_phase5_focus_experiments(
    db: Session,
    horizons: list[str] | None = None,
    classification_models: list[str] | None = None,
    regression_models: list[str] | None = None,
    config: ModelConfig | None = None,
) -> dict:
    horizons = horizons or list(DEFAULT_HORIZONS)
    config = config or ModelConfig()

    load_tickers = tuple(dict.fromkeys((*REFERENCE_UNIVERSE, *SPECIALIZED_TRAINING_UNIVERSE, *REFERENCE_ASSETS)))
    prices, price_summary = load_prices_for_tickers(db, load_tickers)
    experiments = {}
    for experiment_name, training_universe in {
        "broad_reference": REFERENCE_UNIVERSE,
        "specialized_focus_context": SPECIALIZED_TRAINING_UNIVERSE,
    }.items():
        training_tickers = tuple(ticker for ticker in training_universe if ticker not in REFERENCE_ASSETS)
        experiments[experiment_name] = {}
        for target_mode in TARGET_MODES:
            experiments[experiment_name][target_mode] = {}
            for feature_group in (MODEL_B, MODEL_C):
                dataset = build_phase5_dataset(prices, training_tickers, feature_group=feature_group, target_mode=target_mode)
                experiments[experiment_name][target_mode][feature_group] = run_phase5_model_group(
                    dataset,
                    horizons=horizons,
                    focus_stocks=FOCUS_STOCKS,
                    classification_models=classification_models,
                    regression_models=regression_models,
                    config=config,
                )

    selection = select_validation_winners(experiments)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "focus_stocks": list(FOCUS_STOCKS),
        "reference_assets": list(REFERENCE_ASSETS),
        "price_summary": price_summary,
        "experiments": experiments,
        "validation_selection": selection,
    }


def load_prices_for_tickers(db: Session, tickers: Iterable[str]) -> tuple[pd.DataFrame, dict[str, dict]]:
    frames = []
    summary = {}
    for ticker in tickers:
        normalized = normalize_ticker(ticker)
        bars = list(db.scalars(select(PriceBar).where(PriceBar.ticker == normalized).order_by(PriceBar.date.asc())))
        count, start, end = db.execute(
            select(func.count(), func.min(PriceBar.date), func.max(PriceBar.date)).where(PriceBar.ticker == normalized)
        ).one()
        summary[normalized] = {
            "rows": int(count or 0),
            "first_date": None if start is None else start.isoformat(),
            "last_date": None if end is None else end.isoformat(),
        }
        if bars:
            frames.append(price_bars_to_dataframe(bars))
    if not frames:
        return pd.DataFrame(), summary
    return pd.concat(frames, ignore_index=True).sort_values(["ticker", "date"]).reset_index(drop=True), summary


def build_phase5_dataset(
    price_data: pd.DataFrame,
    training_tickers: Iterable[str],
    feature_group: str,
    target_mode: str,
) -> pd.DataFrame:
    if feature_group not in {MODEL_B, MODEL_C}:
        raise ValueError(f"Unsupported Phase 5 feature group: {feature_group}")
    if target_mode not in TARGET_MODES:
        raise ValueError(f"Unsupported Phase 5 target mode: {target_mode}")

    dataset = build_feature_dataset(price_data, include_targets=False, include_price_action=True)
    if feature_group == MODEL_C:
        dataset = add_context_features(dataset, price_data)

    selected = {normalize_ticker(ticker) for ticker in training_tickers}
    selected -= set(REFERENCE_ASSETS)
    dataset = dataset[dataset["ticker"].isin(selected)].copy()
    return add_phase5_targets(dataset, target_mode=target_mode)


def add_phase5_targets(dataset: pd.DataFrame, target_mode: str) -> pd.DataFrame:
    if target_mode == TARGET_FIXED_3PCT:
        return add_future_targets(dataset, thresholds=DirectionThresholds(up=0.03, down=-0.03))
    if target_mode == TARGET_HORIZON_SPECIFIC:
        return _add_horizon_specific_targets(dataset)
    if target_mode == TARGET_VOLATILITY_ADJUSTED:
        return _add_volatility_adjusted_targets(dataset)
    raise ValueError(f"Unsupported Phase 5 target mode: {target_mode}")


def run_phase5_model_group(
    dataset: pd.DataFrame,
    horizons: list[str],
    focus_stocks: Iterable[str],
    classification_models: list[str] | None,
    regression_models: list[str] | None,
    config: ModelConfig,
) -> dict:
    focus = [normalize_ticker(ticker) for ticker in focus_stocks]
    results = {}
    errors = {}
    for horizon in horizons:
        try:
            result = train_horizon_models(
                dataset,
                horizon=horizon,
                classification_models=classification_models,
                regression_models=regression_models,
                config=config,
            )
            results[horizon] = {
                **_summarize_training_result(result),
                "focus_stock_metrics": focus_stock_metrics(result.backtest, focus),
            }
        except Exception as exc:
            errors[horizon] = str(exc)
    return {
        "row_count": int(len(dataset)),
        "tickers": sorted(dataset["ticker"].dropna().unique().tolist()) if not dataset.empty else [],
        "date_range": _date_range(dataset),
        "context_feature_count": sum(1 for column in CONTEXT_FEATURE_COLUMNS if column in dataset.columns),
        "horizons": results,
        "errors": errors,
    }


def focus_stock_metrics(backtest: pd.DataFrame, focus_stocks: list[str]) -> dict[str, dict]:
    output = {}
    for ticker in focus_stocks:
        rows = backtest[backtest["ticker"] == ticker]
        if len(rows) < MIN_FOCUS_TEST_ROWS or rows["actual_class"].nunique() < 2:
            output[ticker] = {
                "status": "INSUFFICIENT_SAMPLE",
                "test_predictions": int(len(rows)),
            }
            continue
        actual_class = rows["actual_class"].to_numpy()
        predicted_class = rows["predicted_class"].to_numpy()
        actual_return = pd.to_numeric(rows["actual_return"], errors="coerce").to_numpy(dtype=float)
        predicted_return = pd.to_numeric(rows["predicted_return"], errors="coerce").to_numpy(dtype=float)
        output[ticker] = {
            "status": "OK",
            "test_predictions": int(len(rows)),
            "classification_accuracy": float(accuracy_score(actual_class, predicted_class)),
            "balanced_accuracy": float(balanced_accuracy_score(actual_class, predicted_class)),
            "up_precision": float(precision_score(actual_class, predicted_class, labels=["UP"], average="micro", zero_division=0)),
            "down_precision": float(precision_score(actual_class, predicted_class, labels=["DOWN"], average="micro", zero_division=0)),
            "regression_mae": float(mean_absolute_error(actual_return, predicted_return)),
            "direction_accuracy": float((np.sign(actual_return) == np.sign(predicted_return)).mean()),
        }
    return output


def select_validation_winners(experiments: dict) -> dict:
    winners = {}
    for horizon in DEFAULT_HORIZONS:
        best = None
        for experiment_name, target_modes in experiments.items():
            for target_mode, feature_groups in target_modes.items():
                for feature_group, report in feature_groups.items():
                    horizon_report = report.get("horizons", {}).get(horizon)
                    if not horizon_report:
                        continue
                    model_name = horizon_report["best_classifier"]
                    validation = horizon_report["classification_validation"].get(model_name, {})
                    score = validation.get("macro_f1")
                    if score is None:
                        continue
                    candidate = {
                        "experiment": experiment_name,
                        "target_mode": target_mode,
                        "feature_group": feature_group,
                        "horizon": horizon,
                        "best_classifier": model_name,
                        "validation_macro_f1": float(score),
                    }
                    if best is None or candidate["validation_macro_f1"] > best["validation_macro_f1"]:
                        best = candidate
        if best:
            winners[horizon] = best
    return winners


def save_phase5_report(report: dict, root: Path | None = None) -> Path:
    root = root or PROJECT_ROOT / "artifacts" / "benchmarks"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"phase5_focus_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    write_json_file(path, report, indent=2, sort_keys=True)
    return path


def _add_horizon_specific_targets(dataset: pd.DataFrame) -> pd.DataFrame:
    output = dataset.copy()
    for horizon, thresholds in HORIZON_SPECIFIC_THRESHOLDS.items():
        output = _add_single_horizon_targets(output, horizon, DEFAULT_HORIZONS[horizon], thresholds)
    return output


def _add_volatility_adjusted_targets(dataset: pd.DataFrame) -> pd.DataFrame:
    output = dataset.copy()
    for horizon, sessions in DEFAULT_HORIZONS.items():
        output = _add_single_horizon_targets(output, horizon, sessions, thresholds=None, volatility_adjusted=True)
    return output


def _add_single_horizon_targets(
    dataset: pd.DataFrame,
    horizon: str,
    sessions: int,
    thresholds: DirectionThresholds | None,
    volatility_adjusted: bool = False,
) -> pd.DataFrame:
    frames = []
    data = dataset.copy()
    data["date"] = pd.to_datetime(data["date"])
    for _, group in data.sort_values(["ticker", "date"]).groupby("ticker", sort=False):
        close = pd.to_numeric(group["close"], errors="coerce")
        future_close = close.shift(-sessions)
        future_return = future_close / close - 1
        group[f"target_close_{horizon}"] = future_close
        group[f"target_return_{horizon}"] = future_return
        if volatility_adjusted:
            rolling_volatility = pd.to_numeric(group.get("volatility_20d"), errors="coerce").fillna(pd.to_numeric(group.get("return_1d"), errors="coerce").rolling(20).std())
            threshold = (rolling_volatility * np.sqrt(sessions) * 0.75).clip(lower=0.015, upper=0.12)
            group[f"target_class_{horizon}"] = _classify_dynamic(future_return, threshold)
        else:
            group[f"target_class_{horizon}"] = _classify_static(future_return, thresholds or DirectionThresholds())
        frames.append(group)
    return pd.concat(frames, ignore_index=True).sort_values(["ticker", "date"]).reset_index(drop=True)


def _classify_static(future_return: pd.Series, thresholds: DirectionThresholds) -> pd.Series:
    values = np.select(
        [future_return > thresholds.up, future_return < thresholds.down, future_return.notna()],
        ["UP", "DOWN", "NEUTRAL"],
        default=pd.NA,
    )
    return pd.Series(values, index=future_return.index, dtype="string")


def _classify_dynamic(future_return: pd.Series, threshold: pd.Series) -> pd.Series:
    values = np.select(
        [future_return > threshold, future_return < -threshold, future_return.notna()],
        ["UP", "DOWN", "NEUTRAL"],
        default=pd.NA,
    )
    return pd.Series(values, index=future_return.index, dtype="string")


def _date_range(dataset: pd.DataFrame) -> dict[str, str | None]:
    if dataset.empty:
        return {"start": None, "end": None}
    dates = pd.to_datetime(dataset["date"])
    return {"start": dates.min().date().isoformat(), "end": dates.max().date().isoformat()}
