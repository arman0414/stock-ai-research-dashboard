import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import PredictionTrackerPage from "./page";
import * as api from "@/lib/api";
import { makePredictionHistoryRecord } from "@/lib/testFixtures";
import type { PredictionHistoryRecord } from "@/lib/types";

const TRACKED = ["NVDA", "AMD", "MU", "TSLA", "IREN"];

function snapshot(ticker: string, date: string, overrides: Partial<PredictionHistoryRecord> = {}, idBase = 0): PredictionHistoryRecord[] {
  return (["5d", "10d", "15d"] as const).map((horizon, index) =>
    makePredictionHistoryRecord({
      id: idBase + index + 1,
      ticker,
      horizon,
      prediction_date: date,
      current_price: 504.2,
      model_target_price: 508.91 + index,
      signal_status: "NO_STRONG_SIGNAL",
      ...overrides,
    })
  );
}

function mockApi(records: Record<string, PredictionHistoryRecord[]>) {
  vi.spyOn(api, "getDailyRunStatus").mockResolvedValue({ tracked_tickers: TRACKED } as never);
  vi.spyOn(api, "getPredictionHistory").mockImplementation((ticker: string) => Promise.resolve(records[ticker] ?? []));
  vi.spyOn(api, "getStockQuotes").mockResolvedValue({});
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("PredictionTrackerPage", () => {
  it("groups each stock's predictions by date with one start price and 5D/10D/15D together", async () => {
    mockApi({ AMD: snapshot("AMD", "2026-09-15") });
    render(<PredictionTrackerPage />);

    const amd = await screen.findByTestId("ticker-section-AMD");
    const card = within(amd).getByTestId("prediction-group-AMD-2026-09-15");
    expect(within(card).getAllByTestId("group-start-price")).toHaveLength(1);
    expect(within(card).getAllByTestId(/horizon-column-/).map((c) => c.getAttribute("data-horizon"))).toEqual(["5d", "10d", "15d"]);
  });

  it("orders prediction dates newest first and badges only the newest", async () => {
    mockApi({ AMD: [...snapshot("AMD", "2026-09-14", {}, 0), ...snapshot("AMD", "2026-09-16", {}, 10)] });
    render(<PredictionTrackerPage />);

    const amd = await screen.findByTestId("ticker-section-AMD");
    const cards = within(amd).getAllByTestId(/prediction-group-AMD-/);
    expect(cards[0]).toHaveAttribute("data-prediction-date", "2026-09-16");
    expect(cards[1]).toHaveAttribute("data-prediction-date", "2026-09-14");
    expect(within(cards[0]!).getByTestId("latest-badge")).toBeInTheDocument();
    expect(within(cards[1]!).queryByTestId("latest-badge")).not.toBeInTheDocument();
  });

  it("keeps stocks in the configured tracking order", async () => {
    mockApi({ NVDA: snapshot("NVDA", "2026-09-15"), AMD: snapshot("AMD", "2026-09-15", {}, 10) });
    render(<PredictionTrackerPage />);

    await screen.findByTestId("ticker-section-NVDA");
    const sections = screen.getAllByTestId(/ticker-section-/);
    expect(sections.map((s) => s.getAttribute("data-testid"))).toEqual(TRACKED.map((t) => `ticker-section-${t}`));
  });

  it("says no completed predictions yet instead of showing 0% accuracy", async () => {
    mockApi({ AMD: snapshot("AMD", "2026-09-15") });
    render(<PredictionTrackerPage />);

    const summary = await screen.findByTestId("tracker-summary");
    expect(within(summary).getAllByText("No completed predictions yet")).toHaveLength(3);
    expect(within(summary).queryByText("0%")).not.toBeInTheDocument();
  });

  it("shows resolved accuracy rates once results exist", async () => {
    mockApi({
      AMD: snapshot("AMD", "2026-09-15", {
        outcome_status: "RESOLVED",
        actual_future_price: 512.1,
        final_day_date: "2026-09-22",
        signed_price_difference: 3.19,
        signed_prediction_difference_pct: 0.63,
        absolute_prediction_difference_pct: 0.63,
        regression_direction_match: true,
      }),
    });
    render(<PredictionTrackerPage />);

    await screen.findByTestId("ticker-section-AMD");
    const summary = screen.getByTestId("tracker-summary");
    expect(within(summary).getByTestId("horizon-accuracy-5d")).toHaveTextContent("Within ±2%: 100%");
    expect(within(summary).getByTestId("horizon-accuracy-5d")).toHaveTextContent("Direction Correct: 100%");
  });

  it("filters by stock", async () => {
    const user = userEvent.setup();
    mockApi({ NVDA: snapshot("NVDA", "2026-09-15"), AMD: snapshot("AMD", "2026-09-15", {}, 10) });
    render(<PredictionTrackerPage />);
    await screen.findByTestId("ticker-section-NVDA");

    await user.click(screen.getByRole("button", { name: "AMD" }));

    expect(screen.queryByTestId("ticker-section-NVDA")).not.toBeInTheDocument();
    expect(screen.getByTestId("ticker-section-AMD")).toBeInTheDocument();
  });

  it("filters by horizon so only that horizon's column remains", async () => {
    const user = userEvent.setup();
    mockApi({ AMD: snapshot("AMD", "2026-09-15") });
    render(<PredictionTrackerPage />);
    await screen.findByTestId("ticker-section-AMD");

    await user.click(screen.getByRole("button", { name: "10D" }));

    const columns = screen.getAllByTestId(/horizon-column-/);
    expect(columns).toHaveLength(1);
    expect(columns[0]).toHaveAttribute("data-horizon", "10d");
  });

  it("filters by status", async () => {
    const user = userEvent.setup();
    mockApi({
      AMD: [
        ...snapshot("AMD", "2026-09-15"),
        ...snapshot("AMD", "2026-09-10", { outcome_status: "RESOLVED", actual_future_price: 512.1, final_day_date: "2026-09-17", absolute_prediction_difference_pct: 1.0, signed_price_difference: 3.19, signed_prediction_difference_pct: 0.63, regression_direction_match: true }, 10),
      ],
    });
    render(<PredictionTrackerPage />);
    await screen.findByTestId("ticker-section-AMD");

    await user.click(screen.getByRole("button", { name: "Resolved" }));

    const cards = screen.getAllByTestId(/prediction-group-AMD-/);
    expect(cards).toHaveLength(1);
    expect(cards[0]).toHaveAttribute("data-prediction-date", "2026-09-10");
  });

  it("toggles between GROUPED and TABLE views, defaulting to GROUPED", async () => {
    const user = userEvent.setup();
    mockApi({ AMD: snapshot("AMD", "2026-09-15") });
    render(<PredictionTrackerPage />);
    await screen.findByTestId("ticker-section-AMD");

    expect(screen.getByTestId("view-toggle-grouped")).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByTestId("prediction-table")).not.toBeInTheDocument();

    await user.click(screen.getByTestId("view-toggle-table"));

    expect(screen.getByTestId("prediction-table")).toBeInTheDocument();
    expect(screen.queryByTestId("ticker-section-AMD")).not.toBeInTheDocument();
  });

  it("tells the user when filters match nothing", async () => {
    const user = userEvent.setup();
    mockApi({ AMD: snapshot("AMD", "2026-09-15") });
    render(<PredictionTrackerPage />);
    await screen.findByTestId("ticker-section-AMD");

    await user.click(screen.getByRole("button", { name: "Resolved" }));

    expect(screen.getByTestId("empty-state")).toHaveTextContent("No predictions match these filters.");
  });

  it("notes that results are still being collected while everything is pending", async () => {
    mockApi({ AMD: snapshot("AMD", "2026-09-15") });
    render(<PredictionTrackerPage />);
    expect(await screen.findByTestId("none-resolved-note")).toHaveTextContent("Results will appear after the required trading sessions pass.");
  });

  it("shows a per-stock empty state for a tracked stock with no saved predictions", async () => {
    mockApi({ AMD: snapshot("AMD", "2026-09-15") });
    render(<PredictionTrackerPage />);
    const nvda = await screen.findByTestId("ticker-section-NVDA");
    expect(within(nvda).getByTestId("empty-state")).toHaveTextContent("No predictions saved for NVDA yet.");
  });

  it("fetches history once per tracked stock, never once per record", async () => {
    mockApi({ AMD: snapshot("AMD", "2026-09-15") });
    render(<PredictionTrackerPage />);
    await screen.findByTestId("ticker-section-AMD");
    expect(vi.mocked(api.getPredictionHistory)).toHaveBeenCalledTimes(TRACKED.length);
  });
});
