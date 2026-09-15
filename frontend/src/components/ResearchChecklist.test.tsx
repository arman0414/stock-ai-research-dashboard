import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import ResearchChecklist from "./ResearchChecklist";
import { makeHorizonPrediction } from "@/lib/testFixtures";
import type { MarketContext } from "@/lib/types";

const NEUTRAL_CONTEXT: MarketContext = {
  spy_trend: "NEUTRAL",
  qqq_trend: "NEUTRAL",
  sector_trend: "NEUTRAL",
  sector_asset: "SMH",
  stock_vs_market: "NEUTRAL",
  stock_vs_sector: "NEUTRAL",
};

describe("ResearchChecklist", () => {
  it("renders all six checklist items and an overall state", () => {
    render(<ResearchChecklist prediction={makeHorizonPrediction()} marketContext={NEUTRAL_CONTEXT} sentiment={null} />);
    expect(screen.getByText("Calibrated probability above 70%")).toBeInTheDocument();
    expect(screen.getByText("Buyer pressure supportive")).toBeInTheDocument();
    expect(screen.getByText("Market/sector supportive")).toBeInTheDocument();
    expect(screen.getByText("Enough historical evidence")).toBeInTheDocument();
    expect(screen.getByText("Resistance nearby")).toBeInTheDocument();
    expect(screen.getByText("News sentiment positive")).toBeInTheDocument();
    expect(screen.getByTestId("overall-setup-state")).toBeInTheDocument();
  });

  it("shows NO_STRONG_SIGNAL as the overall state when the backend gate says so", () => {
    const prediction = makeHorizonPrediction({
      classification: {
        direction: "UP",
        raw_probability: 0.9,
        calibrated_probability: 0.8,
        calibrated_up_probability: 0.8,
        calibrated_down_probability: 0.05,
        signal_status: "NO_STRONG_SIGNAL",
        confidence: "NO_STRONG_SIGNAL",
        gating_reason: "BULLISH_THRESHOLD_NOT_VALIDATED",
        historical_signal_accuracy: null,
        historical_signal_samples: null,
        historical_signal_precision: null,
        bullish_threshold: null,
        bearish_threshold: null,
      },
    });
    render(<ResearchChecklist prediction={prediction} marketContext={NEUTRAL_CONTEXT} sentiment={null} />);
    expect(screen.getByTestId("overall-setup-state")).toHaveTextContent("NO STRONG SIGNAL");
  });

  it("never renders BUY, SELL, or GUARANTEED language anywhere", () => {
    const { container } = render(<ResearchChecklist prediction={makeHorizonPrediction()} marketContext={NEUTRAL_CONTEXT} sentiment={null} />);
    expect(container.textContent).not.toMatch(/BUY NOW|SELL NOW|GUARANTEED/i);
  });
});
