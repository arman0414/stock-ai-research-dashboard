import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import ResearchSummaryPanel from "./ResearchSummaryPanel";
import { makeHorizonPrediction, makeStockAnalysis } from "@/lib/testFixtures";

describe("ResearchSummaryPanel", () => {
  it("shows STRONG research strength alongside a validated BULLISH signal", () => {
    const analysis = makeStockAnalysis();
    const prediction = { ...makeHorizonPrediction(), classification: { ...makeHorizonPrediction().classification, calibrated_probability: 0.75 } };
    render(<ResearchSummaryPanel prediction={prediction} marketContext={analysis.market_context} sentiment={null} structure={analysis.structure} />);

    expect(screen.getByTestId("signal-badge")).toHaveTextContent("Bullish");
    expect(screen.getByTestId("research-strength-badge")).toHaveTextContent("STRONG RESEARCH SIGNAL");
    expect(screen.getByText("Model Research Summary")).toBeInTheDocument();
  });

  it("never overrides the backend's NO_STRONG_SIGNAL even with a high displayed probability", () => {
    const prediction = makeHorizonPrediction({
      classification: {
        direction: "UP",
        raw_probability: 0.9,
        calibrated_probability: 0.72,
        calibrated_up_probability: 0.72,
        calibrated_down_probability: 0.1,
        signal_status: "NO_STRONG_SIGNAL",
        confidence: "NO_STRONG_SIGNAL",
        gating_reason: "BULLISH_THRESHOLD_NOT_VALIDATED",
        historical_signal_accuracy: null,
        historical_signal_samples: null,
        historical_signal_precision: null,
      },
    });
    const context = { spy_trend: "NEUTRAL" as const, qqq_trend: "NEUTRAL" as const, sector_trend: "NEUTRAL" as const, sector_asset: null, stock_vs_market: "NEUTRAL" as const, stock_vs_sector: "NEUTRAL" as const };

    render(<ResearchSummaryPanel prediction={prediction} marketContext={context} sentiment={null} structure={null} />);

    expect(screen.getByTestId("signal-badge")).toHaveTextContent("No Strong Signal");
    expect(screen.getByTestId("research-strength-badge")).toHaveTextContent("NO STRONG SIGNAL");
    expect(screen.getByText("Insufficient evidence")).toBeInTheDocument();
  });
});
