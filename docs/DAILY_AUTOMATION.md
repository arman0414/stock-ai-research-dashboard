# Daily Automation

This document describes the automated daily prediction/evaluation loop added
in Phase 10: what runs, when, how weekends/holidays/missed runs are handled,
what `BACKFILLED_REPLAY` is (and is not) used for, and how a future model
review/retrain would work. **No part of this phase retrains, recalibrates,
or changes any ML model, threshold, or feature.**

## What the daily cycle does

`scripts/run_daily_cycle.py` (implemented in `stock_ai/services/daily_cycle.py`)
runs one end-to-end cycle:

1. Refreshes cached price history for context assets (reference indices/ETFs
   and each watchlist ticker's peer basket) as a best-effort step -- the
   existing champion models' features need this data, but these tickers
   never get predictions of their own and never count as "processed."
2. For each **watchlist** ticker: refreshes its own price history and recent
   news, then runs the existing champion models (unchanged) to produce
   5D/10D/15D predictions.
3. Saves exactly one official `LIVE_DAILY` prediction snapshot per
   `(ticker, horizon, prediction_date, model_version)`. The uniqueness
   constraint on that tuple means re-running the cycle on the same market
   day is a safe no-op (duplicates are skipped, not overwritten).
4. Resolves any previously-saved predictions whose horizon has matured,
   using real stored price bars only.
5. Re-evaluates active alert rules for watchlist tickers.
6. Writes a `DailyRunLog` row (start/end time, counts, status, failures) and
   a human-readable line to `var/logs/daily_cycle.log`.

A small pacing delay (`request_pacing_seconds`, default 2s) is inserted
between per-ticker and per-context-asset provider requests. This was added
after a real dry run against the full watchlist hit Twelve Data's free-tier
per-minute rate limit; it works alongside (not instead of) the existing
retry/backoff logic in `stock_ai/data/providers/http.py`.

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

The scheduler does **not** contain calendar or market-holiday logic, and
deliberately so. The correctness guarantee instead comes from how
`run_daily_cycle` derives its working date:

- Every prediction's `prediction_date` (the "as of" date) comes from
  `predict_multi_horizon`, which in turn is anchored to the **latest row
  actually present in the `price_bars` table** for that ticker -- never the
  wall-clock/calendar date the job happened to run on.
- If the job fires on a Saturday, Sunday, or a market holiday, there is no
  new completed price bar to refresh, so the "latest" bar is still the prior
  trading day's. The cycle computes predictions for that same prior trading
  day, and the `(ticker, horizon, prediction_date, model_version)` unique
  constraint means this collapses to a no-op if a `LIVE_DAILY` snapshot for
  that date already exists (which it normally will, from the prior
  weekday's run).
- This means launchd can fire every day, including weekends, with no risk
  of fabricated or duplicate predictions -- verified by
  `tests/test_phase10_daily_cycle.py::test_weekend_or_holiday_reuses_last_completed_session_as_of_date`.

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
