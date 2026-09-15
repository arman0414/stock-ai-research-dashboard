import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import LiveForecastPerformance from "./LiveForecastPerformance";
import { makeStockLivePerformance } from "@/lib/testFixtures";

describe("LiveForecastPerformance", () => {
  it("shows EARLY RESULTS and no stats table when a horizon has zero resolved predictions", () => {
    render(<LiveForecastPerformance performance={makeStockLivePerformance()} />);
    const panel5d = screen.getByTestId("live-performance-5d");
    expect(within(panel5d).getByText("EARLY RESULTS")).toBeInTheDocument();
    expect(within(panel5d).queryByText("Average Price Error")).not.toBeInTheDocument();
  });

  it("shows full stats once a horizon has resolved predictions", () => {
    const performance = makeStockLivePerformance({
      horizons: {
        "5d": { resolved_count: 42, average_absolute_percentage_error: 0.038, within_3pct: 0.46, within_5pct: 0.67, within_10pct: 0.86, regression_direction_match_rate: 0.59 },
        "10d": { resolved_count: 0, average_absolute_percentage_error: null, within_3pct: null, within_5pct: null, within_10pct: null, regression_direction_match_rate: null },
        "15d": { resolved_count: 0, average_absolute_percentage_error: null, within_3pct: null, within_5pct: null, within_10pct: null, regression_direction_match_rate: null },
      },
    });
    render(<LiveForecastPerformance performance={performance} />);
    const panel5d = screen.getByTestId("live-performance-5d");
    expect(within(panel5d).getByText("3.8%")).toBeInTheDocument(); // average error
    expect(within(panel5d).getByText("59.0%")).toBeInTheDocument(); // direction match
    expect(within(panel5d).getByTestId("sample-size-notice")).toHaveAttribute("data-label", "LIMITED_LIVE_EVIDENCE");
  });

  it("sums resolved forecasts across all three horizons in the header", () => {
    const performance = makeStockLivePerformance({
      horizons: {
        "5d": { resolved_count: 10, average_absolute_percentage_error: 0.03, within_3pct: 0.5, within_5pct: 0.7, within_10pct: 0.9, regression_direction_match_rate: 0.6 },
        "10d": { resolved_count: 5, average_absolute_percentage_error: 0.04, within_3pct: 0.4, within_5pct: 0.6, within_10pct: 0.8, regression_direction_match_rate: 0.5 },
        "15d": { resolved_count: 0, average_absolute_percentage_error: null, within_3pct: null, within_5pct: null, within_10pct: null, regression_direction_match_rate: null },
      },
    });
    render(<LiveForecastPerformance performance={performance} />);
    expect(screen.getByText("15")).toBeInTheDocument(); // 10 + 5
  });
});
