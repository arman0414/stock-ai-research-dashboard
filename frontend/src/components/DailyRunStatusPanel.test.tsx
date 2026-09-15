import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import DailyRunStatusPanel from "./DailyRunStatusPanel";

describe("DailyRunStatusPanel", () => {
  it("shows a never-run message when the automated cycle has not run yet", () => {
    render(<DailyRunStatusPanel status={{ status: "NEVER_RUN" }} />);
    expect(screen.getByText(/has never run yet/)).toBeInTheDocument();
  });

  it("shows run counts and status for a successful run", () => {
    render(
      <DailyRunStatusPanel
        status={{
          id: 1,
          started_at: "2026-09-15T21:30:00Z",
          finished_at: "2026-09-15T21:32:00Z",
          latest_market_date: "2026-09-15",
          tickers_processed: 24,
          tickers_failed: 0,
          predictions_saved: 72,
          duplicates_skipped: 0,
          outcomes_resolved: 3,
          duration_seconds: 120,
          status: "SUCCESS",
          failures: [],
        }}
      />
    );
    expect(screen.getByText("SUCCESS")).toBeInTheDocument();
    expect(screen.getByText("72")).toBeInTheDocument();
    expect(screen.queryByText("Failures")).not.toBeInTheDocument();
  });

  it("lists per-ticker failures for a partial failure", () => {
    render(
      <DailyRunStatusPanel
        status={{
          id: 2,
          started_at: "2026-09-15T21:30:00Z",
          finished_at: "2026-09-15T21:32:00Z",
          latest_market_date: "2026-09-15",
          tickers_processed: 24,
          tickers_failed: 1,
          predictions_saved: 69,
          duplicates_skipped: 0,
          outcomes_resolved: 0,
          duration_seconds: 120,
          status: "PARTIAL_FAILURE",
          failures: [{ ticker: "NVDA", error: "market data provider error: Provider rate limit reached" }],
        }}
      />
    );
    expect(screen.getByText("PARTIAL FAILURE")).toBeInTheDocument();
    expect(screen.getByText(/NVDA: market data provider error/)).toBeInTheDocument();
  });
});
