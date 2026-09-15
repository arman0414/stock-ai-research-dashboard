import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import PredictionCard from "./PredictionCard";
import { makeHorizonPrediction } from "@/lib/testFixtures";

describe("PredictionCard", () => {
  it("renders BULLISH signal, calibrated probability, model target, and range", () => {
    render(<PredictionCard prediction={makeHorizonPrediction()} />);
    expect(screen.getByTestId("signal-badge")).toHaveTextContent("Bullish");
    expect(screen.getByText("68.0%")).toBeInTheDocument(); // calibrated probability
    expect(screen.getByText("$225.00")).toBeInTheDocument(); // model target
    expect(screen.getByText(/\$205\.00.*\$245\.00/)).toBeInTheDocument(); // uncertainty range
    expect(screen.getByText(/61\.0%/)).toBeInTheDocument(); // historical accuracy
    expect(screen.getByText(/143 comparable signals/)).toBeInTheDocument();
  });

  it("never shows raw probability as the primary confidence value", () => {
    render(<PredictionCard prediction={makeHorizonPrediction()} />);
    // The prominent "Model confidence" metric must be the CALIBRATED value (68.0%),
    // not raw_probability (80.0%). Raw probability may only appear tucked away
    // inside the collapsed Advanced Details section.
    const confidenceLabel = screen.getByText("Model confidence");
    const confidenceValue = confidenceLabel.nextElementSibling;
    expect(confidenceValue).toHaveTextContent("68.0%");

    const advancedDetails = screen.getByTestId("advanced-details");
    expect(advancedDetails).toHaveTextContent("80.0%");
  });

  it("renders NO_STRONG_SIGNAL as a normal state with plain-language copy, not an error", () => {
    const prediction = makeHorizonPrediction({
      classification: {
        direction: "NEUTRAL",
        raw_probability: 0.4,
        calibrated_probability: 0.35,
        calibrated_up_probability: 0.3,
        calibrated_down_probability: 0.25,
        signal_status: "NO_STRONG_SIGNAL",
        confidence: "NO_STRONG_SIGNAL",
        gating_reason: "PREDICTED_NEUTRAL",
        historical_signal_accuracy: null,
        historical_signal_samples: null,
        historical_signal_precision: null,
      },
    });
    render(<PredictionCard prediction={prediction} />);
    expect(screen.getByTestId("signal-badge")).toHaveTextContent("No Strong Signal");
    expect(screen.getByText(/does not meet the model's validated confidence requirements/i)).toBeInTheDocument();
    expect(screen.getByText("Insufficient historical evidence")).toBeInTheDocument();
  });

  it("shows a tooltip explaining why a DOWN prediction is suppressed to NO_STRONG_SIGNAL", () => {
    const prediction = makeHorizonPrediction({
      classification: {
        direction: "DOWN",
        raw_probability: 0.46,
        calibrated_probability: 0.37,
        calibrated_up_probability: 0.32,
        calibrated_down_probability: 0.37,
        signal_status: "NO_STRONG_SIGNAL",
        confidence: "NO_STRONG_SIGNAL",
        gating_reason: "BEARISH_THRESHOLD_NOT_VALIDATED",
        historical_signal_accuracy: null,
        historical_signal_samples: null,
        historical_signal_precision: null,
      },
    });
    render(<PredictionCard prediction={prediction} />);
    expect(screen.getByTestId("bearish-tooltip")).toHaveTextContent(/does not currently meet historical validation requirements/i);
    // Crucially, the badge itself still says NO_STRONG_SIGNAL, never BEARISH.
    expect(screen.getByTestId("signal-badge")).toHaveTextContent("No Strong Signal");
  });

  it("only ever renders BEARISH when the backend actually returns that signal_status", () => {
    const prediction = makeHorizonPrediction({
      classification: {
        direction: "DOWN",
        raw_probability: 0.7,
        calibrated_probability: 0.65,
        calibrated_up_probability: 0.1,
        calibrated_down_probability: 0.65,
        signal_status: "BEARISH",
        confidence: "MEDIUM",
        gating_reason: "VALIDATED_BEARISH",
        historical_signal_accuracy: 0.55,
        historical_signal_samples: 80,
        historical_signal_precision: 0.55,
      },
    });
    render(<PredictionCard prediction={prediction} />);
    expect(screen.getByTestId("signal-badge")).toHaveTextContent("Bearish");
  });

  it("labels the primary research horizon", () => {
    render(<PredictionCard prediction={makeHorizonPrediction()} emphasized />);
    expect(screen.getByText("Primary")).toBeInTheDocument();
  });
});
