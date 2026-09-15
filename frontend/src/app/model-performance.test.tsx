import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import ModelPerformancePage from "./model-performance/page";
import * as api from "@/lib/api";
import type { ModelPerformanceSummary } from "@/lib/types";

const BACKTEST: ModelPerformanceSummary = {
  horizons: {
    "5d": {
      status_label: "Best Current Horizon",
      is_primary_research_horizon: true,
      calibration_method: "sigmoid",
      bullish_threshold: 0.5,
      bullish_status: "VALIDATED",
      bearish_threshold: null,
      bearish_status: "INSUFFICIENT_EVIDENCE",
      bullish_test_precision: 0.6,
      bullish_test_sample_count: 172,
      target_price_mae: 19.5,
      within_5pct: 0.59,
      within_10pct: 0.82,
      multi_seed_balanced_accuracy_mean: 0.41,
      multi_seed_balanced_accuracy_std: 0.006,
      reliability_test_calibrated: [],
    },
    "10d": { status: "NOT_TRAINED" },
    "15d": { status: "NOT_TRAINED" },
  },
};

describe("ModelPerformancePage", () => {
  it("shows an empty/loading-safe live section and keeps backtest and live numbers in clearly separate sections", async () => {
    vi.spyOn(api, "getModelPerformance").mockResolvedValue(BACKTEST);
    vi.spyOn(api, "getModelLivePerformance").mockResolvedValue({
      horizons: {
        "5d": { model_version: "v1", resolved_count: 0, average_absolute_percentage_error: null, within_3pct: null, within_5pct: null, within_10pct: null, regression_direction_match_rate: null },
        "10d": { status: "NOT_TRAINED" },
        "15d": { status: "NOT_TRAINED" },
      },
    });

    render(<ModelPerformancePage />);

    expect(await screen.findByText("Historical Backtest Performance")).toBeInTheDocument();
    expect(screen.getByText("Live Forward Performance")).toBeInTheDocument();

    // The backtest MAE ($19.50) must appear only in the backtest section, not live.
    const liveSection = screen.getByTestId("live-forward-5d");
    expect(within(liveSection).queryByText("$19.50")).not.toBeInTheDocument();
    expect(within(liveSection).getByText("EARLY RESULTS")).toBeInTheDocument();
  });

  it("never mixes a resolved live count with backtest sample counts under one label", async () => {
    vi.spyOn(api, "getModelPerformance").mockResolvedValue(BACKTEST);
    vi.spyOn(api, "getModelLivePerformance").mockResolvedValue({
      horizons: {
        "5d": { model_version: "v1", resolved_count: 127, average_absolute_percentage_error: 0.047, within_3pct: 0.4, within_5pct: 0.69, within_10pct: 0.9, regression_direction_match_rate: 0.58 },
        "10d": { status: "NOT_TRAINED" },
        "15d": { status: "NOT_TRAINED" },
      },
    });

    render(<ModelPerformancePage />);

    const liveSection = await screen.findByTestId("live-forward-5d");
    expect(within(liveSection).getByText("127")).toBeInTheDocument();
    expect(within(liveSection).getByText("4.7%")).toBeInTheDocument();
    expect(within(liveSection).getByText("58.0%")).toBeInTheDocument();
    // The backtest section's own sample count (172) must not appear inside the live card.
    expect(within(liveSection).queryByText("172")).not.toBeInTheDocument();
  });
});
