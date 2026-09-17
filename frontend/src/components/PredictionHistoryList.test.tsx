import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import PredictionHistoryList from "./PredictionHistoryList";
import { makePredictionHistoryRecord } from "@/lib/testFixtures";
import { formatDate } from "@/lib/format";

describe("PredictionHistoryList", () => {
  it("shows an empty state when there is no history yet", () => {
    render(<PredictionHistoryList records={[]} />);
    expect(screen.getByTestId("empty-state")).toHaveTextContent("No prediction history yet.");
  });

  it("groups one date's horizons into a single card with the start price shown once", () => {
    const records = (["10d", "15d", "5d"] as const).map((horizon, index) =>
      makePredictionHistoryRecord({ id: index + 1, horizon, prediction_date: "2026-09-15", current_price: 218.29 })
    );
    render(<PredictionHistoryList records={records} />);

    const card = screen.getByTestId("prediction-group-NVDA-2026-09-15");
    expect(within(card).getAllByTestId("group-start-price")).toHaveLength(1);
    expect(within(card).getAllByTestId(/horizon-column-/).map((c) => c.getAttribute("data-horizon"))).toEqual(["5d", "10d", "15d"]);
  });

  it("shows Final Day and Final Price as Pending for an unresolved prediction, not a guessed date/price", () => {
    render(<PredictionHistoryList records={[makePredictionHistoryRecord({ id: 1, outcome_status: "PENDING" })]} />);
    const column = screen.getByTestId("horizon-column-5d");
    expect(within(column).getByText("Final Day")).toBeInTheDocument();
    expect(within(column).getByText("Final Price")).toBeInTheDocument();
    expect(within(column).getAllByText("Pending")).toHaveLength(2);
    expect(within(column).getByText(/Waiting for 5th trading session/)).toBeInTheDocument();
  });

  it("shows the resolved Final Day Date, Final Day Price, signed difference, and accuracy label", () => {
    const record = makePredictionHistoryRecord({
      id: 2,
      outcome_status: "RESOLVED",
      model_target_price: 220.27,
      actual_future_price: 224.1,
      final_day_date: "2026-09-22",
      signed_price_difference: 3.83,
      signed_prediction_difference_pct: 1.74,
      absolute_prediction_difference_pct: 1.74,
      regression_direction_match: true,
      signal_status: "NO_STRONG_SIGNAL",
      signal_outcome: "NOT_APPLICABLE",
    });
    render(<PredictionHistoryList records={[record]} />);
    const column = screen.getByTestId("horizon-column-5d");
    expect(within(column).getByText(formatDate("2026-09-22"))).toBeInTheDocument();
    expect(within(column).getByTestId("final-price")).toHaveTextContent("$224.10");
    expect(within(column).getByTestId("signed-difference")).toHaveTextContent("+$3.83 (+1.74%)");
    expect(within(column).getByTestId("accuracy-badge")).toHaveTextContent("WITHIN ±2%");
    expect(within(column).getByTestId("direction-badge")).toHaveTextContent("Direction Correct");
  });

  it("shows MORE THAN 10% OFF for a resolved prediction with a big miss", () => {
    const record = makePredictionHistoryRecord({
      id: 3,
      outcome_status: "RESOLVED",
      actual_future_price: 180,
      final_day_date: "2026-09-22",
      signed_price_difference: -48.0,
      signed_prediction_difference_pct: -22.0,
      absolute_prediction_difference_pct: 22.0,
      regression_direction_match: false,
    });
    render(<PredictionHistoryList records={[record]} />);
    expect(screen.getByTestId("accuracy-badge")).toHaveTextContent("MORE THAN 10% OFF");
    expect(screen.getByTestId("direction-badge")).toHaveTextContent("Direction Incorrect");
  });

  it("shows newest prediction dates first", () => {
    const older = makePredictionHistoryRecord({ id: 10, prediction_date: "2026-09-01" });
    const newer = makePredictionHistoryRecord({ id: 11, prediction_date: "2026-09-11" });
    render(<PredictionHistoryList records={[older, newer]} />);
    const cards = screen.getAllByTestId(/prediction-group-/);
    expect(cards[0]).toHaveAttribute("data-prediction-date", "2026-09-11");
    expect(cards[1]).toHaveAttribute("data-prediction-date", "2026-09-01");
  });

  it("keeps technical metadata collapsed behind Details", () => {
    render(<PredictionHistoryList records={[makePredictionHistoryRecord({ id: 1 })]} />);
    const details = screen.getByTestId("prediction-details");
    expect(details).not.toHaveAttribute("open");
  });
});
