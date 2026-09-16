import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import DailyRunStatusPanel from "./DailyRunStatusPanel";

const TRACKING_CONFIG = {
  tracked_tickers: ["NVDA", "AMD", "MU", "TSLA", "IREN"],
  tracked_ticker_count: 5,
  predictions_per_market_day: 15,
};

const BASE_RUN = {
  ...TRACKING_CONFIG,
  id: 1,
  started_at: "2026-09-15T21:30:00Z",
  finished_at: "2026-09-15T23:07:00Z",
  expected_market_session: "2026-09-15",
  latest_market_date: "2026-09-15",
  tickers_processed: 5,
  tickers_current: 5,
  tickers_waiting: 0,
  tickers_failed: 0,
  predictions_attempted: 15,
  predictions_saved: 15,
  duplicates_skipped: 0,
  predictions_failed_or_waiting: 0,
  outcomes_resolved: 0,
  duration_seconds: 120,
  status: "SUCCESS" as const,
  failures: [],
};

describe("DailyRunStatusPanel", () => {
  it("shows a never-run message when the automated cycle has not run yet, but still shows tracking config", () => {
    render(<DailyRunStatusPanel status={{ status: "NEVER_RUN", ...TRACKING_CONFIG }} />);
    expect(screen.getByText(/has never run yet/)).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText("NVDA, AMD, MU, TSLA, IREN")).toBeInTheDocument();
    expect(screen.getByText("15")).toBeInTheDocument();
  });

  it("shows run counts, status, and tracking config for a successful run", () => {
    render(<DailyRunStatusPanel status={BASE_RUN} />);

    expect(screen.getByText("SUCCESS")).toBeInTheDocument();
    expect(screen.getByText("NVDA, AMD, MU, TSLA, IREN")).toBeInTheDocument();
    expect(screen.getByText("5/5 current")).toBeInTheDocument();
    expect(screen.getAllByText("2026-09-15").length).toBeGreaterThanOrEqual(2); // expected session + latest data session
    expect(screen.queryByText("Failures")).not.toBeInTheDocument();
    expect(screen.queryByText("Waiting for market data (will retry automatically)")).not.toBeInTheDocument();
  });

  it("clearly separates predictions expected / new saved / duplicate / failed-or-waiting", () => {
    render(
      <DailyRunStatusPanel
        status={{
          ...BASE_RUN,
          predictions_attempted: 15,
          predictions_saved: 6,
          duplicates_skipped: 3,
          predictions_failed_or_waiting: 6,
        }}
      />
    );

    expect(screen.getByText("Predictions Expected")).toBeInTheDocument();
    expect(screen.getByText("New Predictions Saved")).toBeInTheDocument();
    expect(screen.getByText("Already Existing (Duplicate)")).toBeInTheDocument();
    expect(screen.getByText("Failed / Waiting")).toBeInTheDocument();
    // Every count renders next to its own distinct, unambiguous label.
    expect(screen.getAllByText("15").length).toBeGreaterThanOrEqual(1); // predictions per market day + expected
    expect(screen.getAllByText("6").length).toBeGreaterThanOrEqual(1); // saved + failed-or-waiting
    expect(screen.getByText("3")).toBeInTheDocument(); // duplicates
  });

  it("shows WAITING FOR LATEST MARKET DATA and a mismatched expected/latest session, not a hard failure", () => {
    render(
      <DailyRunStatusPanel
        status={{
          ...BASE_RUN,
          expected_market_session: "2026-09-15",
          latest_market_date: "2026-09-14",
          tickers_current: 3,
          tickers_waiting: 2,
          tickers_failed: 0,
          predictions_saved: 9,
          predictions_failed_or_waiting: 6,
          status: "WAITING_FOR_MARKET_DATA",
          failures: [
            { ticker: "NVDA", status: "WAITING", error: "latest stored data is 2026-09-14, expected 2026-09-15" },
            { ticker: "AMD", status: "WAITING", error: "market data provider error: Provider rate limit reached" },
          ],
        }}
      />
    );

    expect(screen.getByText("WAITING FOR LATEST MARKET DATA")).toBeInTheDocument();
    expect(screen.getByText("3/5 current, 2 waiting")).toBeInTheDocument();
    expect(screen.getByText("Waiting for market data (will retry automatically)")).toBeInTheDocument();
    expect(screen.getByText(/NVDA: latest stored data is 2026-09-14/)).toBeInTheDocument();
    expect(screen.queryByText("Failures")).not.toBeInTheDocument(); // waiting is not the same as a hard failure
  });

  it("lists per-ticker hard failures separately from waiting tickers", () => {
    render(
      <DailyRunStatusPanel
        status={{
          ...BASE_RUN,
          tickers_current: 4,
          tickers_waiting: 0,
          tickers_failed: 1,
          predictions_saved: 12,
          predictions_failed_or_waiting: 3,
          status: "PARTIAL_FAILURE",
          failures: [{ ticker: "PONY", status: "FAILED", error: "no feature-ready price history" }],
        }}
      />
    );
    expect(screen.getByText("PARTIAL FAILURE")).toBeInTheDocument();
    expect(screen.getByText("Failures")).toBeInTheDocument();
    expect(screen.getByText(/PONY: no feature-ready price history/)).toBeInTheDocument();
  });
});
