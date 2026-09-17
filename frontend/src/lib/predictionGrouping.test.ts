import { describe, expect, it } from "vitest";
import { applyFilters, groupByPredictionDate, groupByTicker, hasUniformSignal, sortForTable, summarizeHorizonAccuracy } from "./predictionGrouping";
import { makePredictionHistoryRecord } from "./testFixtures";

describe("groupByPredictionDate", () => {
  it("puts every horizon of one snapshot into a single group with one start price", () => {
    const records = [
      makePredictionHistoryRecord({ id: 1, horizon: "10d", prediction_date: "2026-09-15", current_price: 504.2 }),
      makePredictionHistoryRecord({ id: 2, horizon: "15d", prediction_date: "2026-09-15", current_price: 504.2 }),
      makePredictionHistoryRecord({ id: 3, horizon: "5d", prediction_date: "2026-09-15", current_price: 504.2 }),
    ];
    const groups = groupByPredictionDate(records);
    expect(groups).toHaveLength(1);
    expect(groups[0]!.startPrice).toBe(504.2);
    expect(groups[0]!.horizons).toHaveLength(3);
  });

  it("orders horizons 5d, 10d, 15d regardless of the order they arrive in", () => {
    const records = [
      makePredictionHistoryRecord({ id: 1, horizon: "10d", prediction_date: "2026-09-15" }),
      makePredictionHistoryRecord({ id: 2, horizon: "15d", prediction_date: "2026-09-15" }),
      makePredictionHistoryRecord({ id: 3, horizon: "5d", prediction_date: "2026-09-15" }),
    ];
    expect(groupByPredictionDate(records)[0]!.horizons.map((h) => h.horizon)).toEqual(["5d", "10d", "15d"]);
  });

  it("orders groups newest prediction date first", () => {
    const records = [
      makePredictionHistoryRecord({ id: 1, prediction_date: "2026-09-14" }),
      makePredictionHistoryRecord({ id: 2, prediction_date: "2026-09-16" }),
      makePredictionHistoryRecord({ id: 3, prediction_date: "2026-09-15" }),
    ];
    expect(groupByPredictionDate(records).map((g) => g.predictionDate)).toEqual(["2026-09-16", "2026-09-15", "2026-09-14"]);
  });
});

describe("groupByTicker", () => {
  it("keeps the configured tracking order and excludes untracked watchlist stocks", () => {
    const records = [
      makePredictionHistoryRecord({ id: 1, ticker: "AMD" }),
      makePredictionHistoryRecord({ id: 2, ticker: "NVDA" }),
      makePredictionHistoryRecord({ id: 3, ticker: "AAPL" }),
    ];
    const groups = groupByTicker(records, ["NVDA", "AMD", "MU", "TSLA", "IREN"]);
    expect(groups.map((g) => g.ticker)).toEqual(["NVDA", "AMD", "MU", "TSLA", "IREN"]);
    expect(groups.some((g) => g.ticker === "AAPL")).toBe(false);
  });

  it("counts resolved and pending records per ticker", () => {
    const records = [
      makePredictionHistoryRecord({ id: 1, ticker: "NVDA", outcome_status: "RESOLVED" }),
      makePredictionHistoryRecord({ id: 2, ticker: "NVDA", outcome_status: "PENDING" }),
    ];
    const nvda = groupByTicker(records, ["NVDA"])[0]!;
    expect(nvda.resolvedCount).toBe(1);
    expect(nvda.pendingCount).toBe(1);
  });
});

describe("hasUniformSignal", () => {
  it("is true when every horizon reports the same validated signal", () => {
    const group = groupByPredictionDate([
      makePredictionHistoryRecord({ id: 1, horizon: "5d", signal_status: "NO_STRONG_SIGNAL" }),
      makePredictionHistoryRecord({ id: 2, horizon: "10d", signal_status: "NO_STRONG_SIGNAL" }),
    ])[0]!;
    expect(hasUniformSignal(group)).toBe(true);
  });

  it("is false when a horizon disagrees", () => {
    const group = groupByPredictionDate([
      makePredictionHistoryRecord({ id: 1, horizon: "5d", signal_status: "NO_STRONG_SIGNAL" }),
      makePredictionHistoryRecord({ id: 2, horizon: "10d", signal_status: "BULLISH" }),
    ])[0]!;
    expect(hasUniformSignal(group)).toBe(false);
  });
});

describe("summarizeHorizonAccuracy", () => {
  it("reports null rates (not 0%) for a horizon with nothing resolved yet", () => {
    const summary = summarizeHorizonAccuracy([makePredictionHistoryRecord({ id: 1, horizon: "5d", outcome_status: "PENDING" })]);
    const fiveDay = summary.find((s) => s.horizon === "5d")!;
    expect(fiveDay.resolvedCount).toBe(0);
    expect(fiveDay.withinTwoPctRate).toBeNull();
    expect(fiveDay.directionCorrectRate).toBeNull();
  });

  it("computes within-2% and direction rates from resolved records only", () => {
    const summary = summarizeHorizonAccuracy([
      makePredictionHistoryRecord({ id: 1, horizon: "5d", outcome_status: "RESOLVED", absolute_prediction_difference_pct: 1.2, regression_direction_match: true }),
      makePredictionHistoryRecord({ id: 2, horizon: "5d", outcome_status: "RESOLVED", absolute_prediction_difference_pct: 8.0, regression_direction_match: false }),
      makePredictionHistoryRecord({ id: 3, horizon: "5d", outcome_status: "PENDING" }),
    ]);
    const fiveDay = summary.find((s) => s.horizon === "5d")!;
    expect(fiveDay.resolvedCount).toBe(2);
    expect(fiveDay.withinTwoPctRate).toBe(0.5);
    expect(fiveDay.directionCorrectRate).toBe(0.5);
  });
});

describe("applyFilters", () => {
  const records = [
    makePredictionHistoryRecord({ id: 1, ticker: "NVDA", horizon: "5d", outcome_status: "PENDING", prediction_date: "2026-09-15" }),
    makePredictionHistoryRecord({ id: 2, ticker: "AMD", horizon: "10d", outcome_status: "RESOLVED", prediction_date: "2026-09-15" }),
    makePredictionHistoryRecord({ id: 3, ticker: "AMD", horizon: "5d", outcome_status: "PENDING", prediction_date: "2026-07-01" }),
  ];
  const base = { ticker: "ALL", horizon: "ALL", status: "ALL", date: "ALL" } as const;

  it("filters by ticker", () => {
    expect(applyFilters(records, { ...base, ticker: "AMD" }).map((r) => r.id)).toEqual([2, 3]);
  });

  it("filters by horizon", () => {
    expect(applyFilters(records, { ...base, horizon: "5d" }).map((r) => r.id)).toEqual([1, 3]);
  });

  it("filters by status", () => {
    expect(applyFilters(records, { ...base, status: "RESOLVED" }).map((r) => r.id)).toEqual([2]);
  });

  it("filters by date window relative to an injected now", () => {
    const now = new Date("2026-09-16T00:00:00Z");
    expect(applyFilters(records, { ...base, date: "7D" }, now).map((r) => r.id)).toEqual([1, 2]);
    expect(applyFilters(records, { ...base, date: "ALL" }, now)).toHaveLength(3);
  });
});

describe("sortForTable", () => {
  it("sorts newest date first, then 5d/10d/15d", () => {
    const records = [
      makePredictionHistoryRecord({ id: 1, ticker: "NVDA", horizon: "15d", prediction_date: "2026-09-14" }),
      makePredictionHistoryRecord({ id: 2, ticker: "NVDA", horizon: "10d", prediction_date: "2026-09-15" }),
      makePredictionHistoryRecord({ id: 3, ticker: "NVDA", horizon: "5d", prediction_date: "2026-09-15" }),
    ];
    expect(sortForTable(records).map((r) => r.id)).toEqual([3, 2, 1]);
  });
});
