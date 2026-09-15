import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import LiveForecastPerformance from "./LiveForecastPerformance";
import { makeStockLivePerformance } from "@/lib/testFixtures";

describe("LiveForecastPerformance", () => {
  it("shows EARLY RESULTS and no stats table when a horizon has zero resolved predictions", () => {
    render(<LiveForecastPerformance performance={makeStockLivePerformance()} />);
    const panel5d = screen.getByTestId("live-performance-5d");
    expect(within(panel5d).getByText("EARLY RESULTS")).toBeInTheDocument();
    expect(within(panel5d).queryByText("Average Miss")).not.toBeInTheDocument();
  });

  it("shows full stats once a horizon has resolved predictions", () => {
    const performance = makeStockLivePerformance({
      horizons: {
        "5d": { resolved_count: 42, within_2pct: 0.3, within_5pct: 0.67, within_10pct: 0.86, more_than_10pct_off: 0.14, direction_correct_rate: 0.59, average_miss_pct: 3.8 },
        "10d": { resolved_count: 0, within_2pct: null, within_5pct: null, within_10pct: null, more_than_10pct_off: null, direction_correct_rate: null, average_miss_pct: null },
        "15d": { resolved_count: 0, within_2pct: null, within_5pct: null, within_10pct: null, more_than_10pct_off: null, direction_correct_rate: null, average_miss_pct: null },
      },
    });
    render(<LiveForecastPerformance performance={performance} />);
    const panel5d = screen.getByTestId("live-performance-5d");
    expect(within(panel5d).getByText("3.80%")).toBeInTheDocument(); // average miss
    expect(within(panel5d).getByText("59.0%")).toBeInTheDocument(); // direction correct
    expect(within(panel5d).getByTestId("sample-size-notice")).toHaveAttribute("data-label", "LIMITED_LIVE_EVIDENCE");
  });

  it("sums resolved forecasts across all three horizons in the header", () => {
    const performance = makeStockLivePerformance({
      horizons: {
        "5d": { resolved_count: 10, within_2pct: 0.5, within_5pct: 0.7, within_10pct: 0.9, more_than_10pct_off: 0.1, direction_correct_rate: 0.6, average_miss_pct: 3.0 },
        "10d": { resolved_count: 5, within_2pct: 0.4, within_5pct: 0.6, within_10pct: 0.8, more_than_10pct_off: 0.2, direction_correct_rate: 0.5, average_miss_pct: 4.0 },
        "15d": { resolved_count: 0, within_2pct: null, within_5pct: null, within_10pct: null, more_than_10pct_off: null, direction_correct_rate: null, average_miss_pct: null },
      },
    });
    render(<LiveForecastPerformance performance={performance} />);
    expect(screen.getByText("15")).toBeInTheDocument(); // 10 + 5
  });
});
