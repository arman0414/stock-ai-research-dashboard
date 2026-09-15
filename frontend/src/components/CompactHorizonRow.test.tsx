import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import CompactHorizonRow from "./CompactHorizonRow";
import { makeHorizonPrediction } from "@/lib/testFixtures";

describe("CompactHorizonRow", () => {
  it("shows the 10-day predicted price, expected return, and range -- not the 5-day ones", () => {
    const prediction = makeHorizonPrediction({
      horizon: "10d",
      regression: { predicted_return: 0.0124, model_target_price: 342, uncertainty_low: 305, uncertainty_high: 381, p50_abs_error: 0.04 },
    });
    render(<CompactHorizonRow prediction={prediction} />);

    expect(screen.getByText("10 Trading Days")).toBeInTheDocument();
    expect(screen.getByText(/Predicted \$342\.00/)).toBeInTheDocument();
    expect(screen.getByText(/\+1\.2%/)).toBeInTheDocument();
    expect(screen.getByText(/\$305\.00.*\$381\.00/)).toBeInTheDocument();
    expect(screen.queryByText("5 Trading Days")).not.toBeInTheDocument();
  });

  it("shows the 15-day horizon distinctly from 10-day", () => {
    const prediction = makeHorizonPrediction({
      horizon: "15d",
      regression: { predicted_return: 0.03, model_target_price: 348, uncertainty_low: 298, uncertainty_high: 396, p50_abs_error: 0.05 },
    });
    render(<CompactHorizonRow prediction={prediction} />);
    expect(screen.getByText("15 Trading Days")).toBeInTheDocument();
    expect(screen.getByText(/Predicted \$348\.00/)).toBeInTheDocument();
    expect(screen.queryByText("10 Trading Days")).not.toBeInTheDocument();
  });

  it("shows a down arrow for a negative predicted return", () => {
    const prediction = makeHorizonPrediction({
      horizon: "10d",
      regression: { predicted_return: -0.02, model_target_price: 300, uncertainty_low: 270, uncertainty_high: 330, p50_abs_error: 0.03 },
    });
    render(<CompactHorizonRow prediction={prediction} />);
    expect(screen.getByText(/-2\.0%/)).toBeInTheDocument();
  });

  it("renders the validated signal badge matching the backend signal_status", () => {
    const prediction = makeHorizonPrediction({
      horizon: "10d",
      classification: { ...makeHorizonPrediction().classification, signal_status: "NO_STRONG_SIGNAL" },
    });
    render(<CompactHorizonRow prediction={prediction} />);
    expect(screen.getByTestId("signal-badge")).toHaveTextContent("No Strong Signal");
  });
});
