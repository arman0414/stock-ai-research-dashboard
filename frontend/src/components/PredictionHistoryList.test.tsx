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

  it("shows Final Day Date and Final Day Price as Pending for an unresolved prediction, not a guessed date/price", () => {
    const record = makePredictionHistoryRecord({ id: 1, outcome_status: "PENDING" });
    render(<PredictionHistoryList records={[record]} />);
    const item = screen.getByTestId("prediction-history-1");
    expect(within(item).getByText("Final Day Date")).toBeInTheDocument();
    expect(within(item).getByText("Final Day Price")).toBeInTheDocument();
    expect(within(item).getAllByText("Pending")).toHaveLength(2);
    expect(within(item).getByText(/Waiting for: 5 trading days/i)).toBeInTheDocument();
  });

  it("shows the resolved Final Day Date, Final Day Price, signed difference, and accuracy label", () => {
    const record = makePredictionHistoryRecord({
      id: 2,
      outcome_status: "RESOLVED",
      model_target_price: 220.27,
      actual_future_price: 224.10,
      final_day_date: "2026-09-22",
      signed_price_difference: 3.83,
      signed_prediction_difference_pct: 1.74,
      absolute_prediction_difference_pct: 1.74,
      regression_direction_match: true,
      signal_status: "NO_STRONG_SIGNAL",
      signal_outcome: "NOT_APPLICABLE",
    });
    render(<PredictionHistoryList records={[record]} />);
    const item = screen.getByTestId("prediction-history-2");
    expect(within(item).getByText("Final Day Date")).toBeInTheDocument();
    expect(within(item).getByText(formatDate("2026-09-22"))).toBeInTheDocument();
    expect(within(item).getByText("Final Day Price")).toBeInTheDocument();
    expect(within(item).getByText("$224.10")).toBeInTheDocument();
    expect(within(item).queryByText("Actual Price")).not.toBeInTheDocument();
    expect(within(item).getByText("+$3.83 (+1.74%)")).toBeInTheDocument();
    expect(within(item).getByText("WITHIN ±2%")).toBeInTheDocument();
    expect(within(item).getByText("Direction Correct")).toBeInTheDocument();
    expect(within(item).getByText(/No Strong Signal/)).toBeInTheDocument();
    expect(within(item).getByText(/Not Applicable/)).toBeInTheDocument();
  });

  it("shows MORE THAN 10% OFF for a resolved prediction with a big miss", () => {
    const record = makePredictionHistoryRecord({
      id: 3,
      outcome_status: "RESOLVED",
      signed_price_difference: -48.0,
      signed_prediction_difference_pct: -22.0,
      absolute_prediction_difference_pct: 22.0,
      regression_direction_match: false,
    });
    render(<PredictionHistoryList records={[record]} />);
    const item = screen.getByTestId("prediction-history-3");
    expect(within(item).getByText("MORE THAN 10% OFF")).toBeInTheDocument();
    expect(within(item).getByText("Direction Incorrect")).toBeInTheDocument();
  });

  it("shows newest predictions first", () => {
    const older = makePredictionHistoryRecord({ id: 10, prediction_date: "2026-09-01" });
    const newer = makePredictionHistoryRecord({ id: 11, prediction_date: "2026-09-11" });
    render(<PredictionHistoryList records={[older, newer]} />);
    const items = screen.getAllByTestId(/prediction-history-/);
    expect(items[0]).toHaveAttribute("data-testid", "prediction-history-11");
    expect(items[1]).toHaveAttribute("data-testid", "prediction-history-10");
  });
});
