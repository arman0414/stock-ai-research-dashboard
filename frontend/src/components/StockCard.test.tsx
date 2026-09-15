import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import StockCard from "./StockCard";
import { makeHorizonPrediction, makeQuoteResult, makeStockAnalysis } from "@/lib/testFixtures";

const noop = () => {};

describe("StockCard", () => {
  it("shows NO STRONG SIGNAL only once for the primary horizon even though 10d/15d also report it", () => {
    const analysis = makeStockAnalysis({
      predictions: {
        "5d": makeHorizonPrediction({
          horizon: "5d",
          classification: { ...makeHorizonPrediction().classification, signal_status: "NO_STRONG_SIGNAL", gating_reason: "PREDICTED_NEUTRAL" },
        }),
        "10d": makeHorizonPrediction({ horizon: "10d", classification: { ...makeHorizonPrediction().classification, signal_status: "NO_STRONG_SIGNAL" } }),
        "15d": makeHorizonPrediction({ horizon: "15d", classification: { ...makeHorizonPrediction().classification, signal_status: "NO_STRONG_SIGNAL" } }),
      },
    });

    render(<StockCard ticker="NVDA" analysis={analysis} loading={false} error={null} lastRefreshedAt={null} onRefresh={noop} onRemove={noop} />);

    // The primary block renders ONE prominent signal badge; the two secondary
    // horizons render their own single badges in their own compact rows --
    // three badges total is correct (one per horizon), never a duplicate for
    // the same horizon.
    const badges = screen.getAllByTestId("signal-badge");
    expect(badges).toHaveLength(3);

    expect(screen.getByTestId("compact-horizon-10d")).toBeInTheDocument();
    expect(screen.getByTestId("compact-horizon-15d")).toBeInTheDocument();
  });

  it("shows support and resistance with their percentage distance from current price", () => {
    const analysis = makeStockAnalysis({ current_price: 333.08 });
    render(<StockCard ticker="AAPL" analysis={analysis} loading={false} error={null} lastRefreshedAt={null} onRefresh={noop} onRemove={noop} />);

    expect(screen.getByText("Support")).toBeInTheDocument();
    expect(screen.getByText("Resistance")).toBeInTheDocument();
    expect(screen.getByText(/below current price/)).toBeInTheDocument();
    expect(screen.getByText(/above current price/)).toBeInTheDocument();
  });

  it("shows the 10-day and 15-day compact rows with their own distinct targets, not the 5-day figures", () => {
    const analysis = makeStockAnalysis({
      predictions: {
        "5d": makeHorizonPrediction({ horizon: "5d", regression: { predicted_return: 0.03, model_target_price: 225, uncertainty_low: 205, uncertainty_high: 245, p50_abs_error: 0.03 } }),
        "10d": makeHorizonPrediction({ horizon: "10d", regression: { predicted_return: 0.05, model_target_price: 342, uncertainty_low: 305, uncertainty_high: 381, p50_abs_error: 0.04 } }),
        "15d": makeHorizonPrediction({ horizon: "15d", regression: { predicted_return: 0.07, model_target_price: 348, uncertainty_low: 298, uncertainty_high: 396, p50_abs_error: 0.05 } }),
      },
    });
    render(<StockCard ticker="NVDA" analysis={analysis} loading={false} error={null} lastRefreshedAt={null} onRefresh={noop} onRemove={noop} />);

    const row10d = screen.getByTestId("compact-horizon-10d");
    expect(within(row10d).getByText(/Predicted \$342/)).toBeInTheDocument();

    const row15d = screen.getByTestId("compact-horizon-15d");
    expect(within(row15d).getByText(/Predicted \$348/)).toBeInTheDocument();
  });

  it("opens full analysis via a clearly-labeled button", () => {
    render(<StockCard ticker="NVDA" analysis={makeStockAnalysis()} loading={false} error={null} lastRefreshedAt={null} onRefresh={noop} onRemove={noop} />);
    expect(screen.getByText("Open Full Analysis")).toBeInTheDocument();
  });

  it("shows the fresh quote price instead of the stale analysis price once it arrives", () => {
    const analysis = makeStockAnalysis({ current_price: 210.96 });
    const quote = makeQuoteResult({ ticker: "NVDA", price: 214.3 });
    render(<StockCard ticker="NVDA" analysis={analysis} loading={false} error={null} lastRefreshedAt={null} onRefresh={noop} onRemove={noop} quote={quote} />);

    expect(screen.getByText("$214.30")).toBeInTheDocument();
  });

  it("falls back to the last analysis price (never blank, never $0) when no quote has arrived yet", () => {
    const analysis = makeStockAnalysis({ current_price: 210.96 });
    render(<StockCard ticker="NVDA" analysis={analysis} loading={false} error={null} lastRefreshedAt={null} onRefresh={noop} onRemove={noop} />);

    expect(screen.getByText("$210.96")).toBeInTheDocument();
    expect(screen.queryByText("$0.00")).not.toBeInTheDocument();
  });
});
