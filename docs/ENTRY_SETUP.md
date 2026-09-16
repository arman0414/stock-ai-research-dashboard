# Entry Setup

Entry Setup is a research interpretation layer added on top of the existing
model outputs. It answers a practical question the model forecast alone
doesn't: *"based on the existing model forecast and current technical
context, does this look like a reasonable entry setup right now?"*

**It is not a new model.** It runs no ML inference, trains nothing, and
never changes a prediction's stored values (predicted price, predicted
return, probabilities, signal status, historical performance are all
untouched). It combines already-computed information -- validated signal,
predicted upside, support/resistance, buyer pressure -- using simple,
documented, configurable rules.

States: `GOOD_SETUP`, `WATCH`, `WAIT`, `INSUFFICIENT_DATA`. Never `BUY`,
`SELL`, or a numeric score (e.g. "83.47/100") -- categorical labels with
plain-language reasons only. `WAIT` is the conservative default.

## Three separate concepts

| Concept | Example | Source |
|---|---|---|
| Model Forecast | 5D predicted price $220 | Champion regressor, unchanged |
| Validated Model View | `BULLISH` / `NO_STRONG_SIGNAL` | Champion classifier + calibration gate, unchanged |
| Entry Setup | `GOOD_SETUP` / `WATCH` / `WAIT` | `stock_ai/services/entry_setup.py`, this phase |

## Where the logic lives

`stock_ai/services/entry_setup.py` -- a single pure function,
`evaluate_entry_setup()`, with no DB access and no ML inference. Two
callers, both feeding the same function different inputs:

1. **Snapshot evaluation** (`stock_ai/services/prediction_history.py`,
   `record_prediction_with_status()`) -- evaluated ONCE, at the moment an
   official prediction is created, using that same snapshot's own frozen
   `current_price` as "current." Stored on the `PredictionRecord` row
   (`entry_setup_state`, `entry_setup_version`, `entry_setup_reasons_json`)
   and never touched again -- not even when `backfill_outcomes()` later
   resolves the prediction's real outcome. This is what lets a future
   analysis ask "when we said GOOD SETUP, how did it do?" without the
   answer having been silently rewritten after the fact.
2. **Live evaluation** (`GET /stocks/{ticker}/entry-setup?horizon=5d`) --
   recomputed fresh on every call using today's live quote (via
   `stock_ai.services.quote_service`) and the latest structure/prediction
   data. Never persisted. This is what the Dashboard and forecast pages
   display, since "does this look like a reasonable entry right now"
   should reflect right now, not the price at the moment the daily
   prediction was made.

## v1 rules (`entry-v1`)

All thresholds live in `EntryResearchHeuristics` (a single dataclass, not
scattered magic numbers) and are explicitly labeled **heuristic research
values**, not ML-trained thresholds:

```python
min_expected_upside_pct_for_good_setup = 3.0
min_room_to_resistance_pct_for_good_setup = 3.0
min_research_reward_risk_for_good_setup = 1.5
max_support_distance_pct_for_good_setup = 12.0
watch_min_expected_upside_pct = 1.0
watch_min_room_to_resistance_pct = 1.5
```

`GOOD_SETUP` requires ALL of:
- validated signal is `BULLISH`
- expected upside ≥ 3.0%
- room to resistance ≥ 3.0%
- distance above support ≤ 12.0%
- research reward/risk ≥ 1.5x
- resistance is not below the model's target price
- buyer pressure is `STRONG` or `MODERATE` (not `WEAK`/`UNKNOWN`)

Missing support/resistance, or support ≥ resistance (contradictory), always
returns `INSUFFICIENT_DATA` -- never a guess. Anything not `GOOD_SETUP` and
not conservative enough to guarantee no interest at all becomes `WATCH`;
everything else is `WAIT`.

## Calculations

- **Expected Upside** = `(predicted_price - current_price) / current_price × 100`
  -- uses the LIVE quote. Different from the original **Model Expected
  Move** = `(predicted_price - prediction_start_price) / prediction_start_price × 100`,
  which uses the frozen snapshot price. They're equal at the moment a
  snapshot is created and diverge afterward as the live price moves.
- **Support Distance** = `(current_price - support) / current_price × 100`
- **Resistance Room** = `(resistance - current_price) / current_price × 100`
- **Research Reward/Risk** = `(predicted_price - current_price) / (current_price - support)`,
  using support as the reference risk level (never an auto-configured
  stop-loss) and the horizon's `model_target_price` as the reward target.
  If resistance sits below the model target, both are shown and the gap
  weakens (blocks) `GOOD_SETUP`.

## Versioning

`ENTRY_SETUP_VERSION` (currently `"entry-v1"`) is stored with every
snapshot. If the heuristic rules ever change, the version bumps to
`entry-v2` -- old snapshots keep their original `entry-v1` label and are
never silently re-evaluated under the new rules.

## Not yet validated

The specific combination of signal + upside + support/resistance +
reward/risk used here has **not** been separately, historically validated
as an entry strategy. Every live/checklist display carries this disclaimer
verbatim:

> Entry Setup is a research aid based on the current model forecast and
> technical context. Its performance as an entry strategy has not been
> separately validated and is still being evaluated.

Once enough `GOOD_SETUP`/`WATCH`/`WAIT` snapshots have resolved, the
Prediction Tracker is the intended place to eventually show completion
counts, within-±2% rates, direction-correct rates, and average returns
*per Entry Setup state* -- but only once real resolved data exists, and
only for the entry-setup version that actually produced each snapshot.

## Explicitly out of scope for v1

- News Mood is shown alongside Entry Setup but is not a rule input --
  FinBERT sentiment history isn't yet validated as a determinant of setup
  quality.
- Market context (SPY/QQQ/sector trend) is not a hard override. A single
  negative market-trend feature never overrides an otherwise-valid
  `BULLISH` signal.
- No automatic stop-loss is assumed; support is used only as a *reference*
  risk level for the research reward/risk calculation.
