/**
 * Presentation-only grouping for the Prediction Tracker. These helpers only
 * ever re-shape prediction records that the backend already produced -- they
 * never recompute a prediction, an outcome, or an accuracy value.
 *
 * The hierarchy the UI wants is STOCK -> PREDICTION DATE -> 5D/10D/15D, so a
 * flat list of records becomes one card per (ticker, prediction_date) with the
 * horizons sitting side by side inside it, instead of one card per record
 * repeating the same date and start price three times.
 */
import type { Horizon, PredictionHistoryRecord } from "./types";
import { HORIZONS } from "./types";

export interface PredictionDateGroup {
  ticker: string;
  predictionDate: string;
  /** The frozen start price of this snapshot. All horizons of one snapshot
   * share it, which is exactly why it is shown once per group, not per
   * horizon. Null only in the (unexpected) case of an empty group. */
  startPrice: number | null;
  /** Horizon records in fixed 5d/10d/15d order -- never database order. A
   * horizon with no saved record for this date is simply absent. */
  horizons: { horizon: Horizon; record: PredictionHistoryRecord }[];
  records: PredictionHistoryRecord[];
}

export interface TickerGroup {
  ticker: string;
  /** Newest prediction date first. */
  dateGroups: PredictionDateGroup[];
  totalCount: number;
  resolvedCount: number;
  pendingCount: number;
}

function horizonRank(horizon: Horizon): number {
  const index = HORIZONS.indexOf(horizon);
  return index === -1 ? HORIZONS.length : index;
}

/** Groups one ticker's records into prediction-date cards, newest date first. */
export function groupByPredictionDate(records: PredictionHistoryRecord[]): PredictionDateGroup[] {
  const byDate = new Map<string, PredictionHistoryRecord[]>();
  for (const record of records) {
    const existing = byDate.get(record.prediction_date);
    if (existing) existing.push(record);
    else byDate.set(record.prediction_date, [record]);
  }

  return [...byDate.entries()]
    .sort((a, b) => (a[0] < b[0] ? 1 : a[0] > b[0] ? -1 : 0))
    .map(([predictionDate, dateRecords]) => {
      const horizons = [...dateRecords]
        .sort((a, b) => horizonRank(a.horizon) - horizonRank(b.horizon))
        .map((record) => ({ horizon: record.horizon, record }));
      return {
        ticker: dateRecords[0]?.ticker ?? "",
        predictionDate,
        startPrice: dateRecords[0]?.current_price ?? null,
        horizons,
        records: dateRecords,
      };
    });
}

/**
 * Groups every record by ticker, in `tickerOrder` (the configured daily
 * tracking order), then by prediction date. Tickers not in `tickerOrder` are
 * left out entirely so a large watchlist never dilutes the tracked five.
 */
export function groupByTicker(records: PredictionHistoryRecord[], tickerOrder: string[]): TickerGroup[] {
  const byTicker = new Map<string, PredictionHistoryRecord[]>();
  for (const record of records) {
    const existing = byTicker.get(record.ticker);
    if (existing) existing.push(record);
    else byTicker.set(record.ticker, [record]);
  }

  return tickerOrder.map((ticker) => {
    const tickerRecords = byTicker.get(ticker) ?? [];
    const resolvedCount = tickerRecords.filter((r) => r.outcome_status === "RESOLVED").length;
    return {
      ticker,
      dateGroups: groupByPredictionDate(tickerRecords),
      totalCount: tickerRecords.length,
      resolvedCount,
      pendingCount: tickerRecords.length - resolvedCount,
    };
  });
}

/** True when every horizon in the group reports the same validated signal --
 * the case where repeating it three times adds nothing. */
export function hasUniformSignal(group: PredictionDateGroup): boolean {
  if (group.horizons.length <= 1) return true;
  const first = group.horizons[0]!.record.signal_status;
  return group.horizons.every(({ record }) => record.signal_status === first);
}

export interface HorizonAccuracySummary {
  horizon: Horizon;
  resolvedCount: number;
  /** Null when nothing has resolved -- the UI must say "no completed
   * predictions yet" rather than print a meaningless 0%. */
  withinTwoPctRate: number | null;
  directionCorrectRate: number | null;
}

export function summarizeHorizonAccuracy(records: PredictionHistoryRecord[]): HorizonAccuracySummary[] {
  return HORIZONS.map((horizon) => {
    const resolved = records.filter((r) => r.horizon === horizon && r.outcome_status === "RESOLVED");
    if (resolved.length === 0) {
      return { horizon, resolvedCount: 0, withinTwoPctRate: null, directionCorrectRate: null };
    }
    const withinTwo = resolved.filter((r) => r.absolute_prediction_difference_pct !== null && r.absolute_prediction_difference_pct <= 2).length;
    const directionCorrect = resolved.filter((r) => r.regression_direction_match === true).length;
    return {
      horizon,
      resolvedCount: resolved.length,
      withinTwoPctRate: withinTwo / resolved.length,
      directionCorrectRate: directionCorrect / resolved.length,
    };
  });
}

export type StatusFilter = "ALL" | "PENDING" | "RESOLVED";
export type DateFilter = "7D" | "30D" | "ALL";
export type HorizonFilter = "ALL" | Horizon;

export interface TrackerFilters {
  ticker: string | "ALL";
  horizon: HorizonFilter;
  status: StatusFilter;
  date: DateFilter;
}

const DATE_FILTER_DAYS: Record<Exclude<DateFilter, "ALL">, number> = { "7D": 7, "30D": 30 };

/**
 * `now` is injectable so the date window is deterministic in tests rather
 * than depending on when the suite happens to run.
 */
export function applyFilters(records: PredictionHistoryRecord[], filters: TrackerFilters, now: Date = new Date()): PredictionHistoryRecord[] {
  let cutoff: string | null = null;
  if (filters.date !== "ALL") {
    const cutoffDate = new Date(now);
    cutoffDate.setDate(cutoffDate.getDate() - DATE_FILTER_DAYS[filters.date]);
    cutoff = cutoffDate.toISOString().slice(0, 10);
  }

  return records.filter((record) => {
    if (filters.ticker !== "ALL" && record.ticker !== filters.ticker) return false;
    if (filters.horizon !== "ALL" && record.horizon !== filters.horizon) return false;
    if (filters.status !== "ALL" && record.outcome_status !== filters.status) return false;
    if (cutoff !== null && record.prediction_date < cutoff) return false;
    return true;
  });
}

/** Flat rows for TABLE view: newest prediction date first, then 5d/10d/15d. */
export function sortForTable(records: PredictionHistoryRecord[]): PredictionHistoryRecord[] {
  return [...records].sort((a, b) => {
    if (a.prediction_date !== b.prediction_date) return a.prediction_date < b.prediction_date ? 1 : -1;
    if (a.ticker !== b.ticker) return a.ticker < b.ticker ? -1 : 1;
    return horizonRank(a.horizon) - horizonRank(b.horizon);
  });
}
