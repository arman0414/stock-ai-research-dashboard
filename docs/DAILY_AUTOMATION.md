# Daily Automation

This document describes the automated daily prediction/evaluation loop added
in Phase 10: what runs, when, how weekends/holidays/missed runs are handled,
what `BACKFILLED_REPLAY` is (and is not) used for, and how a future model
review/retrain would work. **No part of this phase retrains, recalibrates,
or changes any ML model, threshold, or feature.**

## What the daily cycle does

`scripts/run_daily_cycle.py` (implemented in `stock_ai/services/daily_cycle.py`)
runs one end-to-end cycle:

1. Determines the **expected completed NYSE trading session** using
   `stock_ai.market_calendar` (real weekday/holiday calendar, not naive
   calendar-day arithmetic) -- see "Data freshness" below.
2. Refreshes cached price history for context assets (reference indices/ETFs
   and each tracked ticker's peer basket) as a best-effort step -- the
   existing champion models' features need this data, but these tickers
   never get predictions of their own and never count as "processed."
3. For each **tracked** ticker (`DAILY_TRACKING_TICKERS`): refreshes its own
   price history and recent news, checks whether its latest stored price bar
   has actually reached the expected session, and only if so runs the
   existing champion models (unchanged) to produce 5D/10D/15D predictions.
4. Saves exactly one official `LIVE_DAILY` prediction snapshot per
   `(ticker, horizon, prediction_date, model_version)`. The uniqueness
   constraint on that tuple means re-running the cycle on the same market
   day is a safe no-op (duplicates are skipped, not overwritten).
5. Resolves any previously-saved predictions whose horizon has matured,
   using real stored price bars only.
6. Re-evaluates active alert rules for the full watchlist.
7. Writes a `DailyRunLog` row (start/end time, counts, status, per-ticker
   freshness) and a human-readable line to `var/logs/daily_cycle.log`.

A pacing delay (`request_pacing_seconds`, configurable via
`DAILY_CYCLE_REQUEST_PACING_SECONDS`, default 2s) is inserted between
per-ticker and per-context-asset provider requests. This was added after a
real dry run against the full watchlist hit Twelve Data's free-tier
per-minute rate limit; it works alongside (not instead of) the retry/backoff
logic in `stock_ai/data/providers/http.py`, which now also honors a 429
response's `Retry-After` header (capped at 60s) instead of always using a
fixed exponential formula.

## Data freshness: never a stale or fabricated prediction

A ticker's `PriceBar` history can lag behind the real calendar for two
reasons: the market simply hasn't closed yet, or the data provider is slow
(or rate-limited) to publish/return the latest session's bar. The daily
cycle tells these apart explicitly, per tracked ticker, using
`stock_ai.market_calendar.latest_completed_trading_session()`:

- **CURRENT** -- the ticker's latest stored bar date is at or after the
  expected completed session. Predictions are created (or found to already
  exist, in which case the run is a no-op for that ticker).
- **WAITING** -- the latest stored bar is still behind the expected
  session, whether because the provider hasn't published it yet or because
  refreshing it just failed (rate limit, transient network/HTTP error). No
  prediction is created for that ticker this run -- **never** a stale or
  fabricated one. Because runs are idempotent per `(ticker, horizon,
  prediction_date, model_version)`, simply running the cycle again later
  (the next scheduled run, or `scripts/manage_scheduler.sh run-now`) safely
  fills in whatever is still missing, without ever duplicating a ticker
  that already succeeded.
- **FAILED** -- a non-freshness problem (no champion model trained yet, or
  not enough feature-ready history). Retrying won't help until that
  underlying issue is fixed some other way.

One ticker's status never affects another's: NVDA being rate-limited or
one day stale does not block AMD, MU, TSLA, or IREN from getting their
predictions on the same run if their own data is ready.

A market day is **complete** only once every tracked ticker is CURRENT for
that expected session (`session_complete` in the run summary / the
`/system/daily-run-status` response). There is no separate "day state" to
manage -- completeness is always derived live from what's actually stored,
so an incomplete day is automatically retried by simply running the cycle
again; nothing needs to be manually reset or replayed.

The overall run `status` reflects this: `SUCCESS` (all tracked tickers
CURRENT), `WAITING_FOR_MARKET_DATA` (some tickers WAITING, none FAILED --
this is expected and benign, not an alarm), `PARTIAL_FAILURE` (a mix
including at least one FAILED), or `FAILURE` (all tracked tickers FAILED).

## Schedule

- **When**: 21:30 local time, Monday-Friday (configurable via
  `STOCK_AI_SCHEDULE_HOUR` / `STOCK_AI_SCHEDULE_MINUTE` env vars passed to
  `scripts/manage_scheduler.sh install`). This is well after the 16:00 ET US
  market close, leaving margin for the data provider's end-of-day bar to be
  finalized.
- **Timezone**: whatever the Mac's local timezone is at the time launchd
  evaluates the schedule (`StartCalendarInterval` uses system local time).
- **Mechanism**: a per-user `launchd` agent
  (`~/Library/LaunchAgents/com.stockai.dailycycle.plist`), managed via
  `scripts/manage_scheduler.sh`.

### Weekend / holiday / no-new-data handling

The scheduler itself does **not** contain calendar logic; `stock_ai
.market_calendar` does, and `run_daily_cycle` consults it before creating
anything:

- The **expected completed session** is computed independently of any
  stored data, from the real NYSE weekday/holiday calendar (see "Data
  freshness" above) -- so a naive "today's calendar date" is never mistaken
  for a real trading session.
- Every prediction's `prediction_date` (the "as of" date) still comes from
  `predict_multi_horizon`, anchored to the **latest row actually present in
  the `price_bars` table** for that ticker -- but that row is only used once
  it's confirmed to have reached the expected session.
- If the job fires on a Saturday, Sunday, or a market holiday, there is no
  new completed price bar to refresh, so the ticker's latest bar is still
  the prior trading day's -- which the calendar also recognizes as the
  currently-expected session, so the ticker is CURRENT (not WAITING) and the
  `(ticker, horizon, prediction_date, model_version)` unique constraint
  makes the run a safe no-op if that day's snapshot already exists.
- This means launchd can fire every day, including weekends, with no risk
  of fabricated, stale, or duplicate predictions -- verified by
  `tests/test_market_calendar.py` (the calendar itself) and
  `tests/test_phase10_daily_cycle.py` (freshness gating end to end).

### Missed runs (sleep, shutdown, etc.)

`launchd`'s `StartCalendarInterval` fires the job as soon as the machine
wakes if it was asleep at the scheduled time, rather than silently skipping
that day. If the Mac was off entirely through a scheduled time, the job
simply does not run for that day -- there is no catch-up/backfill behavior,
because retroactively constructing "as of yesterday" predictions using data
that includes information from days after "yesterday" would violate the
project's core fairness rule (a live prediction must only ever see data
available at the time it claims to represent). A missed day surfaces as a
gap in the `daily_run_logs` table / `GET /system/daily-run-status`, not as a
fabricated entry.

## `prediction_source` and `BACKFILLED_REPLAY`

Every `PredictionRecord` now carries a `prediction_source`:

- `LIVE_DAILY` -- written by the scheduled daily cycle described above.
- `MANUAL_LIVE` -- written by any on-demand/dashboard-triggered prediction
  call outside the daily cycle (e.g. a user opening a stock detail page).
- `BACKFILLED_REPLAY` -- reserved for a **future**, explicitly-labeled
  historical replay feature (running the champion models against past
  dates to build a larger evaluation sample). **This value is not produced
  by any code in this phase.** The schema field and the exclusion logic
  (`LIVE_PREDICTION_SOURCES` in `stock_ai/services/prediction_performance.py`
  and `stock_ai/services/model_review.py`) exist so that if/when a replay
  feature is built later, it is structurally impossible for replay records
  to silently mix into live performance stats or the model-review counter --
  they are excluded by construction, not by convention.

Both `LIVE_DAILY` and `MANUAL_LIVE` are treated as equally "live" for
performance/review purposes, since both reflect a real prediction made
without foreknowledge of the outcome.

## Model review (informational only -- never auto-retrains)

`GET /models/review-status` (via `stock_ai.services.model_review`) reports
whether enough new live evidence has accumulated to justify a **human**
looking at whether the current champion model should be reviewed:

- `NOT_TRAINED` -- no champion model exists yet for the review horizon.
- `COLLECTING_DATA` -- fewer than `REVIEW_THRESHOLD` (100) resolved,
  live-source (`LIVE_DAILY`/`MANUAL_LIVE`), correct-horizon (5D) predictions
  generated on-or-after the current champion's `created_at` exist yet.
- `READY_FOR_MODEL_REVIEW` -- at least 100 such predictions exist.

This status is purely informational. **Nothing in this codebase reads this
status and triggers retraining, recalibration, or promotion.** Reaching
`READY_FOR_MODEL_REVIEW` only means "there is now enough fresh live data
that a human could meaningfully evaluate whether a new candidate model
would beat the current champion" -- it does not mean a new model exists.

### Future candidate-model workflow (documentation only -- not implemented)

If/when model improvement work resumes, the intended workflow is:

1. Current champion continues serving live predictions, unchanged.
2. A new candidate model is trained offline (manually invoked, e.g. via
   `scripts/train_champion_models.py` or a successor), using the same
   historical + newly-accumulated data.
3. The candidate is validated against historical backtest data (never live
   forward data it could have seen).
4. The candidate is then evaluated against the **recent live holdout**
   (the `LIVE_DAILY`/`MANUAL_LIVE` predictions accumulated since the
   current champion was trained) -- this is what `model_review_status`'s
   counter is tracking readiness for.
5. A human compares candidate vs. champion on both historical and live-
   holdout metrics.
6. Only if the candidate is clearly better is it manually promoted to
   become the new champion. There is no automatic promotion step, and none
   is planned to run unattended.

This explicitly avoids a single bad live day (e.g. one wrong prediction)
ever causing the model to retrain or change itself.

## Managing the scheduler

```bash
scripts/manage_scheduler.sh install     # generate the plist and load it
scripts/manage_scheduler.sh status      # show load state + last log lines
scripts/manage_scheduler.sh run-now     # trigger one run immediately
scripts/manage_scheduler.sh disable     # unload (stop future scheduled runs)
scripts/manage_scheduler.sh enable      # re-load a previously installed job
scripts/manage_scheduler.sh uninstall   # unload and remove the plist
```

The generated `.plist` never contains API keys or other secrets. It invokes
the project's venv Python directly against `scripts/run_daily_cycle.py`,
which loads `.env` itself at runtime via `stock_ai.config.get_settings()` --
identical to running the script manually from a terminal. The job does not
depend on VS Code, a browser, or the frontend dev server being open; it only
needs the Mac to be powered on (or to wake from sleep) at the scheduled time.

### Logs

- `var/logs/daily_cycle.log` -- application-level log (one line per run,
  in the format produced by `logging`), written by `run_daily_cycle.py`
  itself regardless of how it's invoked.
- `var/logs/scheduler.out.log` / `var/logs/scheduler.err.log` -- raw
  stdout/stderr captured by launchd for the scheduled process.

All of the above are covered by the existing `*.log` entry in `.gitignore`.
