import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import PredictionCard from "./PredictionCard";
import { makeHorizonPrediction } from "@/lib/testFixtures";
import type { Classification } from "@/lib/types";

function noStrongSignalClassification(overrides: Partial<Classification> = {}): Classification {
  return {
    direction: "UP",
    raw_probability: 0.5,
    calibrated_probability: 0.37,
    calibrated_up_probability: 0.37,
    calibrated_down_probability: 0.1,
    signal_status: "NO_STRONG_SIGNAL",
    confidence: "NO_STRONG_SIGNAL",
    gating_reason: "BELOW_BULLISH_THRESHOLD",
    historical_signal_accuracy: null,
    historical_signal_samples: null,
    historical_signal_precision: null,
    bullish_threshold: 0.5,
    bearish_threshold: null,
    ...overrides,
  };
}

describe("PredictionCard", () => {
  it("shows NO STRONG SIGNAL exactly once, with Model Lean shown separately from the validated signal", () => {
    const prediction = makeHorizonPrediction({ horizon: "5d", classification: noStrongSignalClassification() });
    render(<PredictionCard prediction={prediction} />);

    const badges = screen.getAllByTestId("signal-badge");
    expect(badges).toHaveLength(1);
    expect(badges[0]).toHaveTextContent("No Strong Signal");

    // "NO STRONG SIGNAL" text (case-insensitive) must not appear a second time
    // as a duplicate headline elsewhere in the card.
    const allNoStrongSignalOccurrences = screen.getAllByText(/no strong signal/i);
    expect(allNoStrongSignalOccurrences).toHaveLength(1);

    expect(screen.getByText("Model Lean")).toBeInTheDocument();
    const leanLabel = screen.getByText("Model Lean");
    expect(leanLabel.nextElementSibling).toHaveTextContent("UP");
  });

  it("shows the real gating reason as a why-explanation, not an invented one", () => {
    const prediction = makeHorizonPrediction({
      horizon: "5d",
      classification: noStrongSignalClassification({ calibrated_probability: 0.37, bullish_threshold: 0.5 }),
    });
    render(<PredictionCard prediction={prediction} />);
    const reason = screen.getByTestId("no-strong-signal-reason");
    expect(reason).toHaveTextContent("Model leans UP");
    expect(reason).toHaveTextContent("37");
    expect(reason).toHaveTextContent("50");
  });

  it("renders the bearish-disabled reason correctly", () => {
    const prediction = makeHorizonPrediction({
      classification: noStrongSignalClassification({
        direction: "DOWN",
        calibrated_probability: 0.72,
        gating_reason: "BEARISH_THRESHOLD_NOT_VALIDATED",
        bearish_threshold: null,
      }),
    });
    render(<PredictionCard prediction={prediction} />);
    expect(screen.getByTestId("no-strong-signal-reason")).toHaveTextContent(/not currently supported by enough historical evidence/);
  });

  it("renders the insufficient-evidence (unvalidated bullish) reason correctly", () => {
    const prediction = makeHorizonPrediction({
      classification: noStrongSignalClassification({ gating_reason: "BULLISH_THRESHOLD_NOT_VALIDATED", bullish_threshold: null }),
    });
    render(<PredictionCard prediction={prediction} />);
    expect(screen.getByTestId("no-strong-signal-reason")).toHaveTextContent(/not currently supported by enough historical evidence/);
  });

  it("does not render a why-explanation when the signal is validated", () => {
    const prediction = makeHorizonPrediction(); // fixture default: BULLISH, validated
    render(<PredictionCard prediction={prediction} />);
    expect(screen.queryByTestId("no-strong-signal-reason")).not.toBeInTheDocument();
  });

  it("labels the 5-day card explicitly as 5 Trading Days, not just '5D'", () => {
    render(<PredictionCard prediction={makeHorizonPrediction({ horizon: "5d" })} />);
    expect(screen.getByText("5 TRADING DAYS")).toBeInTheDocument();
    expect(screen.getByText(/Model Estimate in 5 Trading Days/)).toBeInTheDocument();
  });

  it("labels the 10-day card as 10 Trading Days and never mislabels it as 5", () => {
    render(<PredictionCard prediction={makeHorizonPrediction({ horizon: "10d" })} />);
    expect(screen.getByText("10 TRADING DAYS")).toBeInTheDocument();
    expect(screen.getByText(/Model Estimate in 10 Trading Days/)).toBeInTheDocument();
    expect(screen.queryByText("5 TRADING DAYS")).not.toBeInTheDocument();
    expect(screen.queryByText(/Model Estimate in 5 Trading Days/)).not.toBeInTheDocument();
  });

  it("labels the 15-day card as 15 Trading Days and never mislabels it as 5", () => {
    render(<PredictionCard prediction={makeHorizonPrediction({ horizon: "15d" })} />);
    expect(screen.getByText("15 TRADING DAYS")).toBeInTheDocument();
    expect(screen.getByText(/Model Estimate in 15 Trading Days/)).toBeInTheDocument();
    expect(screen.queryByText("5 TRADING DAYS")).not.toBeInTheDocument();
  });

  it("labels the price range as a historical error range, not an implied guarantee", () => {
    render(<PredictionCard prediction={makeHorizonPrediction()} />);
    expect(screen.getByText("Historical 80% Error Range")).toBeInTheDocument();
  });

  it("shows a working info tooltip for the trading-day range and the price range", () => {
    render(<PredictionCard prediction={makeHorizonPrediction({ horizon: "5d" })} />);
    const tooltips = screen.getAllByTestId("info-tooltip");
    expect(tooltips.some((tip) => tip.title.includes("5 Trading Days usually means"))).toBe(true);
    expect(tooltips.some((tip) => tip.title.includes("historical prediction error"))).toBe(true);
  });

  it("keeps Model Confidence and Historical Success visually and numerically distinct", () => {
    const prediction = makeHorizonPrediction({
      classification: {
        ...makeHorizonPrediction().classification,
        calibrated_probability: 0.62,
        historical_signal_accuracy: 0.58,
        historical_signal_samples: 147,
      },
    });
    render(<PredictionCard prediction={prediction} />);

    const confidenceLabel = screen.getByText("Model Confidence");
    expect(within(confidenceLabel.parentElement as HTMLElement).getByText("62.0%")).toBeInTheDocument();

    const successLabel = screen.getByText("Historical Success of Similar Signals");
    expect(successLabel.nextElementSibling).toHaveTextContent("58.0%");

    const samplesLabel = screen.getByText("Historical Examples");
    expect(samplesLabel.nextElementSibling).toHaveTextContent("147");
  });

  it("shows 'Not enough validated examples yet' when historical reliability is unavailable", () => {
    const prediction = makeHorizonPrediction({
      classification: { ...makeHorizonPrediction().classification, historical_signal_accuracy: null, historical_signal_samples: null },
    });
    render(<PredictionCard prediction={prediction} />);
    expect(screen.getByText("Not enough validated examples yet")).toBeInTheDocument();
  });

  it("labels the primary research horizon", () => {
    render(<PredictionCard prediction={makeHorizonPrediction()} emphasized />);
    expect(screen.getByText("Primary")).toBeInTheDocument();
  });

  it("puts raw probability only inside Advanced Details, never as the headline confidence", () => {
    render(<PredictionCard prediction={makeHorizonPrediction()} />);
    const confidenceLabel = screen.getByText("Model Confidence");
    expect(within(confidenceLabel.parentElement as HTMLElement).getByText("68.0%")).toBeInTheDocument(); // calibrated, from fixture
    expect(screen.getByTestId("advanced-details")).toHaveTextContent("80.0%"); // raw, from fixture
  });
});
