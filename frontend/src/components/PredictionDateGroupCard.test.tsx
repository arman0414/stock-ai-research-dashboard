import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import PredictionDateGroupCard from "./PredictionDateGroupCard";
import { groupByPredictionDate } from "@/lib/predictionGrouping";
import { makePredictionHistoryRecord } from "@/lib/testFixtures";
import { formatDate } from "@/lib/format";

function makeGroup(records = pendingSnapshot()) {
  return groupByPredictionDate(records)[0]!;
}

function pendingSnapshot() {
  return [
    makePredictionHistoryRecord({ id: 1, ticker: "AMD", horizon: "5d", prediction_date: "2026-09-15", current_price: 504.2, model_target_price: 508.91 }),
    makePredictionHistoryRecord({ id: 2, ticker: "AMD", horizon: "10d", prediction_date: "2026-09-15", current_price: 504.2, model_target_price: 509.3 }),
    makePredictionHistoryRecord({ id: 3, ticker: "AMD", horizon: "15d", prediction_date: "2026-09-15", current_price: 504.2, model_target_price: 508.7 }),
  ];
}

describe("PredictionDateGroupCard", () => {
  it("shows the start price once for the whole snapshot, not once per horizon", () => {
    render(<PredictionDateGroupCard group={makeGroup()} />);
    expect(screen.getAllByTestId("group-start-price")).toHaveLength(1);
    expect(screen.getByTestId("group-start-price")).toHaveTextContent("$504.20");
  });

  it("renders 5D/10D/15D together in fixed order inside one card", () => {
    render(<PredictionDateGroupCard group={makeGroup()} />);
    const columns = screen.getAllByTestId(/horizon-column-/);
    expect(columns.map((c) => c.getAttribute("data-horizon"))).toEqual(["5d", "10d", "15d"]);
    expect(within(columns[0]!).getByTestId("predicted-price")).toHaveTextContent("$508.91");
    expect(within(columns[1]!).getByTestId("predicted-price")).toHaveTextContent("$509.30");
    expect(within(columns[2]!).getByTestId("predicted-price")).toHaveTextContent("$508.70");
  });

  it("keeps the pending state compact without the long waiting sentence in every column", () => {
    render(<PredictionDateGroupCard group={makeGroup()} />);
    const column = screen.getByTestId("horizon-column-5d");
    expect(within(column).getByText("Final Day")).toBeInTheDocument();
    expect(within(column).getByText("Final Price")).toBeInTheDocument();
    expect(within(column).getByText(/Waiting for 5th trading session/)).toBeInTheDocument();
    expect(screen.queryByText(/the exact future trading-session date is not known until it happens/)).not.toBeInTheDocument();
  });

  it("shows Final Day Date, Final Day Price, signed difference, accuracy badge and direction once resolved", () => {
    const group = makeGroup([
      makePredictionHistoryRecord({
        id: 1,
        horizon: "5d",
        prediction_date: "2026-09-15",
        model_target_price: 508.91,
        outcome_status: "RESOLVED",
        actual_future_price: 512.1,
        final_day_date: "2026-09-22",
        signed_price_difference: 3.19,
        signed_prediction_difference_pct: 0.63,
        absolute_prediction_difference_pct: 0.63,
        regression_direction_match: true,
      }),
    ]);
    render(<PredictionDateGroupCard group={group} />);
    const column = screen.getByTestId("horizon-column-5d");
    expect(within(column).getByText(formatDate("2026-09-22"))).toBeInTheDocument();
    expect(within(column).getByTestId("final-price")).toHaveTextContent("$512.10");
    expect(within(column).getByTestId("signed-difference")).toHaveTextContent("+$3.19 (+0.63%)");
    expect(within(column).getByTestId("accuracy-badge")).toHaveTextContent("WITHIN ±2%");
    expect(within(column).getByTestId("direction-badge")).toHaveTextContent("Direction Correct");
  });

  it("marks a big miss and an incorrect direction", () => {
    const group = makeGroup([
      makePredictionHistoryRecord({
        id: 1,
        horizon: "5d",
        outcome_status: "RESOLVED",
        actual_future_price: 180,
        final_day_date: "2026-09-22",
        signed_price_difference: -48,
        signed_prediction_difference_pct: -22,
        absolute_prediction_difference_pct: 22,
        regression_direction_match: false,
      }),
    ]);
    render(<PredictionDateGroupCard group={group} />);
    expect(screen.getByTestId("accuracy-badge")).toHaveTextContent("MORE THAN 10% OFF");
    expect(screen.getByTestId("direction-badge")).toHaveTextContent("Direction Incorrect");
  });

  it("states the model view once when every horizon agrees, instead of repeating it per horizon", () => {
    const records = pendingSnapshot().map((record) => ({ ...record, signal_status: "NO_STRONG_SIGNAL" as const }));
    render(<PredictionDateGroupCard group={makeGroup(records)} />);
    expect(screen.getAllByText(/Model View: No Strong Signal/)).toHaveLength(1);
  });

  it("shows a per-horizon model view only when the horizons disagree", () => {
    const records = pendingSnapshot();
    records[0]!.signal_status = "BULLISH";
    records[1]!.signal_status = "NO_STRONG_SIGNAL";
    records[2]!.signal_status = "NO_STRONG_SIGNAL";
    render(<PredictionDateGroupCard group={makeGroup(records)} />);
    expect(within(screen.getByTestId("horizon-column-5d")).getByText(/Model View: Bullish/)).toBeInTheDocument();
    expect(within(screen.getByTestId("horizon-column-10d")).getByText(/Model View: No Strong Signal/)).toBeInTheDocument();
  });

  it("keeps advanced details collapsed by default", () => {
    render(<PredictionDateGroupCard group={makeGroup()} />);
    const details = screen.getByTestId("prediction-details");
    expect(details).not.toHaveAttribute("open");
    expect(within(details).getByText("Details")).toBeInTheDocument();
  });

  it("shows the Latest badge only when asked", () => {
    const { rerender } = render(<PredictionDateGroupCard group={makeGroup()} isLatest />);
    expect(screen.getByTestId("latest-badge")).toBeInTheDocument();
    rerender(<PredictionDateGroupCard group={makeGroup()} />);
    expect(screen.queryByTestId("latest-badge")).not.toBeInTheDocument();
  });
});
