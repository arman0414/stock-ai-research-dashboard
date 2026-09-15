# Stock AI Dashboard

A personal, experimental research dashboard for **absolute** stock direction and return prediction (not relative/ranking, not brokerage-connected, not automated trading). It combines technical/price-action features, calibrated machine learning forecasts, news sentiment, and manual portfolio/alert tracking behind a small FastAPI backend and a Next.js dashboard.

**This is a research tool, not a trading system.** Predictions are experimental and calibrated against historical data; they are not guarantees of future performance. See "Model Limitations" below.

## What This Project Does

- Downloads and caches historical OHLCV price data per ticker (Twelve Data, with a Stooq fallback).
- Builds backward-looking technical, price-action, and market/sector-context features.
- Trains and calibrates absolute direction classifiers (UP/NEUTRAL/DOWN) and return regressors for 5-day, 10-day, and 15-day horizons, with validated confidence thresholds and honest uncertainty ranges.
- Serves predictions, price-action structure, news sentiment, and plain-language explanations through a FastAPI backend.
- Presents everything in a Next.js dashboard: watchlist, per-stock analysis, manual position tracking (with P/L), in-app alerts, and a model-performance page that reports calibration and reliability honestly rather than overselling the model.

## Stack

- **Backend:** Python, FastAPI, SQLAlchemy, SQLite (local), scikit-learn, XGBoost, pandas.
- **Frontend:** Next.js (App Router) + TypeScript + Tailwind CSS, `lightweight-charts` for candlesticks.
- **ML research:** chronological train/validation/test splitting with purge gaps, Random Forest classification/regression, sigmoid/isotonic probability calibration selected per horizon, validated bullish/bearish thresholds with minimum-evidence gating, multi-seed and walk-forward stability checks.

## Model Limitations (read before trusting a signal)

- **5D is the strongest horizon; 10D is secondary; 15D is weaker.** The dashboard marks 5D as the "Primary Research Horizon" for this reason.
- **Validated bearish signals are not currently available.** Bearish predictions display `NO_STRONG_SIGNAL` until enough evidence exists to validate a bearish threshold.
- Displayed probabilities are **calibrated**, not raw model output, and calibration quality itself varies by horizon (best at 5D).
- A signal only appears as BULLISH/BEARISH when the backend's validated threshold and minimum-evidence requirements are met — never from a raw probability alone.

## Quick Start

### 1. Backend setup

```bash
cd /Users/armanmalik/Desktop/stocks
python3 -m venv .venv        # requires Python 3.10+
source .venv/bin/activate
python3 -m pip install -r requirements.txt
cp .env.example .env         # then fill in your own API keys locally -- never commit .env
```

### 2. Run the backend

```bash
source .venv/bin/activate
uvicorn stock_ai.main:app --port 8000
```

API docs: http://127.0.0.1:8000/docs

### 3. Frontend setup and run

```bash
cd frontend
npm install
npm run dev
```

Dashboard: http://localhost:3000 (expects the backend at `http://localhost:8000`; override with `frontend/.env.local` → `NEXT_PUBLIC_API_BASE_URL`).

### 4. Train champion models (required once before predictions work)

```bash
source .venv/bin/activate
python3 scripts/train_champion_models.py
```

This downloads/uses cached price history, trains calibrated classifiers/regressors per horizon, and saves them under `artifacts/models/champions/<horizon>/`. The large `.joblib` binaries are intentionally excluded from Git (see `.gitignore`) — regenerate them locally with this command rather than expecting them to be checked out.

### 5. Tests

```bash
# Backend
source .venv/bin/activate
pytest

# Frontend
cd frontend
npm test -- --run
npm run lint
npm run build
```

## Legacy Phase-by-Phase Notes

The sections below document how each subsystem was originally built, phase by phase, and remain accurate for understanding the codebase's internals.

Phase 1 foundation for a personal AI/ML stock analysis dashboard.

This first milestone intentionally focuses on market-data plumbing, storage, and watchlist CRUD. It does not build ML forecasts or the frontend yet.

## What Works Now

- FastAPI backend
- SQLite database for local development
- Watchlist add/list/get/delete
- Free delayed/end-of-day historical market data from Stooq
- Historical OHLCV storage with idempotent upserts
- Refresh one ticker or the full watchlist
- Backward-looking technical indicators
- Multi-horizon future targets for 5D, 10D, 15D, 1M, and 3M
- Reusable dataset builder for future model training
- Feature matrix helper that excludes target and raw price columns
- Chronological train/validation/test splitting with horizon purge gaps
- Baseline, Logistic/Ridge, Random Forest, and XGBoost model training
- Classification, regression, confidence, calibration, and backtest evaluation helpers
- Model artifact save/load support
- Tests for watchlist behavior, price-history storage, and date alignment

## Project Layout

```text
stock_ai/
  api/                  FastAPI routes
  db/                   SQLAlchemy engine/session
  models/               Database models
  schemas/              API schemas
  services/             Business logic
  data/providers/market Market-data provider implementations
  features/             Technical features, future targets, dataset building
  ml/                   Splitting, preprocessing, training, evaluation, backtesting
  alerts/               Future alert engine
  notifications/        Future notifications
frontend/               Future React/Next.js dashboard
scripts/                Helper scripts
tests/                  Pytest suite
config/                 Non-secret config files
var/data/               Local SQLite data
```

## Setup

```bash
cd /Users/armanmalik/Desktop/stocks
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
cp .env.example .env
```

The MVP does not require paid API keys.

## Run The API

```bash
cd /Users/armanmalik/Desktop/stocks
uvicorn stock_ai.main:app --reload
```

Open:

- API: http://127.0.0.1:8000
- Docs: http://127.0.0.1:8000/docs

## Common API Calls

Add a stock:

```bash
curl -X POST http://127.0.0.1:8000/stocks \
  -H "Content-Type: application/json" \
  -d '{"ticker":"AAPL","company_name":"Apple Inc."}'
```

Refresh one ticker:

```bash
curl -X POST "http://127.0.0.1:8000/stocks/AAPL/refresh?years=5"
```

List watchlist:

```bash
curl http://127.0.0.1:8000/stocks
```

Refresh all watchlist symbols:

```bash
curl -X POST "http://127.0.0.1:8000/refresh/all?years=5"
```

Inspect the latest ready technical features for a stock:

```bash
curl http://127.0.0.1:8000/stocks/AAPL/features/latest
```

## Phase 2: Features And Targets

Phase 2 adds the foundation needed before model training. It creates historical feature rows and future labels, but it does not train a classifier or regression model yet.

Features are inputs the model can know on a given date, such as momentum, moving averages, RSI, MACD, volatility, and volume behavior.

Targets are future outcomes used for supervised learning, such as the close price 10 trading sessions later or whether the stock moved UP, DOWN, or stayed NEUTRAL.

Classification means predicting the direction class. Regression means predicting a numeric value such as future return or future close.

### Technical Indicators

Generated indicators include:

- Returns: `return_1d`, `return_5d`, `return_10d`, `return_20d`, `return_50d`
- Moving averages: `sma_5`, `sma_10`, `sma_20`, `sma_50`, `sma_100`, `sma_200`
- Exponential averages: `ema_12`, `ema_26`
- Momentum: `rsi_14`, `macd`, `macd_signal`, `macd_histogram`
- Volatility: `volatility_5d`, `volatility_20d`, `volatility_50d`
- Volume: `volume_sma_5`, `volume_sma_20`, `relative_volume`
- Price position: `distance_from_sma20`, `distance_from_sma50`, `distance_from_sma200`, `distance_from_52w_high`, `distance_from_52w_low`
- Trend flags: `price_above_sma20`, `price_above_sma50`, `price_above_sma200`, `sma20_above_sma50`, `sma50_above_sma200`
- Range/bands: `atr_14`, `bollinger_upper`, `bollinger_lower`, `bollinger_width`

All technical features are backward-looking. The code does not backfill financial features from future rows.

### Target Horizons

The initial target horizons are:

- `5d`: 5 trading sessions
- `10d`: 10 trading sessions
- `15d`: 15 trading sessions
- `21d`: 21 trading sessions, used as the first 1-month approximation
- `63d`: 63 trading sessions, used as the first 3-month approximation

Each horizon creates:

- `target_close_*`
- `target_return_*`
- `target_class_*`

Direction labels use the initial configurable thresholds:

- `UP`: future return greater than `+3%`
- `DOWN`: future return less than `-3%`
- `NEUTRAL`: between `-3%` and `+3%`

### Building A Dataset

Use the pure pandas builder when model-training code is added later:

```python
from stock_ai.features.dataset import build_feature_dataset, build_training_data

dataset = build_feature_dataset(price_dataframe)
training = build_training_data(price_dataframe, horizon="10d")

X = training.X
y_classification = training.y_classification
y_regression = training.y_regression
dates = training.dates
```

`X` contains technical features only. It excludes raw OHLCV fields and all `target_*` columns so future labels cannot leak into model inputs.

## Phase 3: Training, Evaluation, Backtesting

Phase 3 adds a reusable machine-learning framework. It still does not build the frontend, production prediction endpoints, news, or FinBERT.

Supported classification models:

- `dummy`
- `logistic`
- `random_forest`
- `xgboost`

Supported regression models:

- `dummy`
- `ridge`
- `random_forest`
- `xgboost`

Classification predicts `UP`, `NEUTRAL`, or `DOWN` with probabilities. Regression predicts future return, such as `target_return_10d`. A later prediction layer can convert that return into a target price with:

```text
predicted_price = current_price * (1 + predicted_return)
```

### Chronological Splitting

Financial rows are never shuffled. Splitting uses sorted dates:

```text
earliest dates -> train
middle dates   -> validation
latest dates   -> test
```

Default split proportions are 70% train, 15% validation, and 15% test.

The splitter applies a purge gap between train/validation and validation/test. The purge gap equals the selected horizon length, for example:

- `10d` model: 10-session purge gap
- `63d` model: 63-session purge gap

This reduces boundary leakage where a row's future target period overlaps the next evaluation period.

### Preprocessing

Preprocessing selects numeric model-compatible features and excludes:

- `date`
- `ticker`
- OHLCV/raw price identifiers
- every `target_*` column
- every `future_*` column

Missing and infinite values are handled with a median imputer fit only on training data. Scaling is also fit only on training data, then reused for validation and test.

### Metrics

Classification reports:

- accuracy
- balanced accuracy
- macro precision
- macro recall
- macro F1
- confusion matrix
- class-specific precision/recall/F1
- log loss
- multiclass Brier score
- high-confidence slices at `>=0.50`, `>=0.60`, `>=0.70`, `>=0.80`

Regression reports:

- MAE
- RMSE
- R2
- direction accuracy

Validation metrics select the best model. Test metrics are final reporting only and are not used for model selection.

### Confidence Labels

Initial display labels:

- `<0.50`: `NO_STRONG_SIGNAL`
- `0.50-0.60`: `LOW`
- `0.60-0.70`: `MEDIUM`
- `0.70-0.80`: `HIGH`
- `>=0.80`: `VERY_HIGH`

These labels are display helpers only. They should be adjusted later using real calibration and backtesting results.

### Backtesting

The backtest module records one row per test-period prediction:

- ticker
- prediction date
- horizon
- current price
- predicted class
- actual class
- predicted probability
- confidence
- predicted return
- actual return
- predicted target price
- actual future price
- classification correctness
- regression error

It also includes simple research-only signal statistics for high-confidence UP/DOWN predictions. Non-overlapping signal evaluation is available so long-horizon daily signals are not treated as fully independent trades.

Historical backtest results do not guarantee future performance. The simple strategy metrics do not include transaction costs, slippage, taxes, liquidity, or position sizing.

### Model Artifacts

Artifacts can be saved under:

```text
artifacts/models/
  classification/<horizon>/<model_version>/
  regression/<horizon>/<model_version>/
```

Each artifact contains:

- `model.joblib`
- `metadata.json`

Metadata includes model version, task, horizon, feature columns, split date ranges, metrics, configuration, and timestamp. Generated model artifacts are ignored by git.

### Training Command

Train and compare all default models for one ticker/horizon:

```bash
cd /Users/armanmalik/Desktop/stocks
python3 -m stock_ai.ml.train --ticker AAPL --horizon 10d --compare-all
```

Train all horizons:

```bash
python3 -m stock_ai.ml.train --ticker AAPL --all-horizons --compare-all
```

Save best validation-selected artifacts:

```bash
python3 -m stock_ai.ml.train --ticker AAPL --horizon 10d --save-artifacts
```

Example report shape:

```json
{
  "10d": {
    "best_classifier": "random_forest",
    "best_regressor": "ridge",
    "classification_validation": {
      "dummy": {"accuracy": 0.43, "balanced_accuracy": 0.33, "macro_f1": 0.20}
    },
    "regression_validation": {
      "dummy": {"mae": 0.04, "rmse": 0.05, "direction_accuracy": 0.50}
    }
  }
}
```

## Tests

```bash
cd /Users/armanmalik/Desktop/stocks
pytest
```

## Environment Variables

Use `.env` locally. Never commit real secrets.

- `DATABASE_URL`: defaults to local SQLite at `var/data/stocks.sqlite3`
- `MARKET_DATA_PROVIDER`: use `twelve_data` for benchmarks; `stooq` remains a development fallback
- `MARKET_DATA_API_KEY`: generic market-data key fallback
- `TWELVE_DATA_API_KEY`: Twelve Data historical price API key
- `NEWS_PROVIDER`: defaults to `yahoo_rss`
- `HISTORICAL_NEWS_PROVIDER`: use `alpha_vantage` for historical news research
- `NEWS_API_KEY`: placeholder for future historical news providers
- `ALPHA_VANTAGE_API_KEY`: Alpha Vantage NEWS_SENTIMENT API key
- `FINBERT_MODEL_NAME`: defaults to `ProsusAI/finbert`
- `HUGGINGFACE_TOKEN`: optional Hugging Face token for model downloads
- `EMAIL_USERNAME` / `EMAIL_PASSWORD`: future email alerts

## Phase 4: Price Action And News

Phase 4 adds price-action/market-structure features, news infrastructure, FinBERT sentiment, event categorization, and benchmark tooling.

It does not add the frontend, portfolio tracking, alerts, scheduled jobs, brokerage integration, or an LLM research agent.

### Price Action

Optional price-action features are generated with:

```python
from stock_ai.features.dataset import build_feature_dataset

dataset = build_feature_dataset(
    price_dataframe,
    include_targets=True,
    include_price_action=True,
)
```

Implemented feature groups:

- Candle anatomy: `candle_body`, `candle_range`, `upper_wick`, `lower_wick`, wick ratios, `close_location`
- Rejection strength: `bullish_rejection_strength`, `bearish_rejection_strength`
- Multi-day pressure: candle ratios, close-location averages, up/down volume ratios, `buyer_pressure_*`, `seller_pressure_*`
- Flow indicators: `obv`, `adl`, `cmf_20`, `mfi_14`
- Directional movement: `adx_14`, `plus_di_14`, `minus_di_14`
- Market structure: higher-high/higher-low/lower-high/lower-low ratios and `trend_structure_score`
- Support/resistance: nearest levels, distance, touch counts, strength, support/resistance rejection
- Breakout/rejection: breakout, failed breakout, breakdown, volume ratios, distance measures
- Compression/divergence: ATR ratio, range compression, Bollinger width change, volume compression, OBV/CMF divergence
- Composite pressure: `buyer_pressure_score`, `seller_pressure_score`

All price-action calculations are backward-looking. Support/resistance and breakout levels use prior data where the current candle could otherwise define the level being tested.

Development endpoint:

```bash
curl http://127.0.0.1:8000/stocks/AAPL/structure
```

The structure summary uses cautious language such as "Price/volume behavior suggests..." and does not claim knowledge of actual order flow.

### Historical Data Providers

Primary benchmark price provider:

```text
MARKET_DATA_PROVIDER=twelve_data
TWELVE_DATA_API_KEY=your_key_here
```

Create a free Twelve Data account, place the key in `.env`, then run the three-stock smoke download first:

```bash
cd /Users/armanmalik/Desktop/stocks
python3 -m stock_ai.data.download_benchmark --smoke --years 5
```

If the smoke report shows stored rows and usable price-action fields for AAPL/MSFT/NVDA, download the full benchmark universe:

```bash
python3 -m stock_ai.data.download_benchmark --years 5
```

Historical prices are cached in SQLite. The first load requests the full range; later refreshes start from the latest stored date minus a small overlap and use upserts, so training reads from the local database instead of repeatedly calling the provider.

Twelve Data daily endpoint values are stored as provided by the API; the current implementation treats `close` as `adjusted_close` because the selected endpoint does not provide a separate adjusted close in the normalized response. Split-adjusted production training should add explicit corporate-action handling before relying on long historical windows.

Optional configured fallback:

```text
MARKET_DATA_PROVIDER=twelve_data_fallback
TWELVE_DATA_API_KEY=your_key_here
```

This tries Twelve Data first and then Stooq. A single successful provider supplies the whole request; it does not mix providers for one ticker/date fetch.

### News And FinBERT

The initial free development provider is `yahoo_rss`. It requires no API key, but it should be treated as a current/live development feed, not a reliable historical news source for supervised ML training. In this environment, Yahoo RSS returned an HTML block/consent page when checked directly, so article coverage is currently zero until a reachable news provider is configured.

Historical news provider:

```text
HISTORICAL_NEWS_PROVIDER=alpha_vantage
ALPHA_VANTAGE_API_KEY=your_key_here
```

Create a free Alpha Vantage account and cache a small historical-news universe first:

```bash
python3 -m stock_ai.data.download_news --tickers AAPL NVDA TSLA MSFT AMZN --days 365
```

If quota is reached, the command saves progress and exits cleanly. Running it later resumes through deduplication and will not duplicate stored articles.

FinBERT support uses `ProsusAI/finbert`. The wrapper analyzes headline plus summary, returns positive/neutral/negative probabilities, and stores `sentiment_score = positive_probability - negative_probability` along with model version and timestamp.

Real FinBERT smoke test:

```bash
python3 -m stock_ai.news.finbert_smoke
```

News features are optional:

```python
dataset = build_feature_dataset(
    price_dataframe,
    include_targets=True,
    include_price_action=True,
    include_news=True,
    news_articles=articles,
)
```

News windows include 1d, 3d, 7d, 14d, and 30d counts/averages. Features include sentiment counts, max probabilities, sentiment changes, recency-weighted sentiment, news-volume ratio, event counts, and `has_news_*` flags.

After-market articles are mapped to the next business day so they do not leak into same-day close predictions.

### Benchmarking

Run the Phase 4 benchmark script:

```bash
cd /Users/armanmalik/Desktop/stocks
python3 scripts/run_phase4_benchmark.py --horizons 5d 10d 15d 21d 63d
```

Feature groups:

- `technical`
- `technical_price_action`
- `technical_price_action_news`

Reports are saved under `artifacts/benchmarks/`.

After benchmark data is cached locally, run:

```bash
python3 scripts/run_phase4_benchmark.py --horizons 5d 10d 15d 21d 63d
```

Current local benchmark status: the script created a failure artifact because Stooq is behind a browser verification page from this environment and returned no usable CSV data. A fair technical-only, technical+price-action, or news ablation benchmark needs reachable historical OHLCV data first. Yahoo RSS also does not provide sufficient historical coverage here, so a fair news ablation cannot yet be performed.

## Phase 5 Next

Phase 5 should proceed only after real historical price data is reachable. Then it can run the full three-way benchmark and, if results justify it, add production prediction endpoints and dashboard-facing model metadata.
