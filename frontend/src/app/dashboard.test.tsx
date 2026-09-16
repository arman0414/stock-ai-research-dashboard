import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import DashboardPage from "./page";
import * as api from "@/lib/api";
import { makeStockAnalysis, makeQuoteResult } from "@/lib/testFixtures";

describe("DashboardPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("splits the watchlist into Live Tracking and Watchlist, and only auto-polls quotes for the tracked five", async () => {
    vi.spyOn(api, "listWatchlist").mockResolvedValue([
      { id: 1, ticker: "NVDA", company_name: null, data_source: "twelve_data", created_at: null, updated_at: null, last_refreshed_at: null },
      { id: 2, ticker: "AAPL", company_name: null, data_source: "twelve_data", created_at: null, updated_at: null, last_refreshed_at: null },
    ]);
    vi.spyOn(api, "getStockAnalysis").mockImplementation(async (ticker: string) => makeStockAnalysis({ ticker }));
    vi.spyOn(api, "getDailyRunStatus").mockResolvedValue({
      status: "NEVER_RUN",
      tracked_tickers: ["NVDA", "AMD", "MU", "TSLA", "IREN"],
      tracked_ticker_count: 5,
      predictions_per_market_day: 15,
    });
    const quotesSpy = vi.spyOn(api, "getStockQuotes").mockResolvedValue({ NVDA: makeQuoteResult({ ticker: "NVDA" }) });

    render(<DashboardPage />);

    expect(await screen.findByText("Live Tracking")).toBeInTheDocument();
    expect(await screen.findByText("Watchlist")).toBeInTheDocument();

    // NVDA (tracked) renders under Live Tracking; AAPL (not tracked) stays
    // visible under Watchlist -- the normal watchlist is never deleted.
    await screen.findByTestId("stock-card-NVDA");
    await screen.findByTestId("stock-card-AAPL");

    await waitFor(() => expect(quotesSpy).toHaveBeenCalled());
    // Only the tracked ticker present on this watchlist (NVDA) is ever
    // requested automatically -- AAPL must never appear in a quote batch.
    for (const call of quotesSpy.mock.calls) {
      expect(call[0]).not.toContain("AAPL");
    }
  });

  it("renders the watchlist with per-stock predictions", async () => {
    vi.spyOn(api, "listWatchlist").mockResolvedValue([
      { id: 1, ticker: "NVDA", company_name: null, data_source: "twelve_data", created_at: null, updated_at: null, last_refreshed_at: "2026-09-11T00:00:00Z" },
    ]);
    vi.spyOn(api, "getStockAnalysis").mockResolvedValue(makeStockAnalysis());

    render(<DashboardPage />);

    expect(await screen.findByTestId("stock-card-NVDA")).toBeInTheDocument();
    const card = screen.getByTestId("stock-card-NVDA");
    // Current price legitimately appears more than once (card header + forecast detail).
    expect(within(card).getAllByText("$218.29").length).toBeGreaterThan(0);
    expect(within(card).getByText("Open Full Analysis")).toBeInTheDocument();
  });

  it("shows an empty state when the watchlist has no stocks", async () => {
    vi.spyOn(api, "listWatchlist").mockResolvedValue([]);
    render(<DashboardPage />);
    expect(await screen.findByTestId("empty-state")).toHaveTextContent("No stocks in your watchlist yet.");
  });

  it("adds a stock through the Add Stock modal", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "listWatchlist").mockResolvedValue([]);
    const addStockSpy = vi.spyOn(api, "addStock").mockResolvedValue({
      id: 2,
      ticker: "AAPL",
      company_name: null,
      data_source: "twelve_data",
      created_at: null,
      updated_at: null,
      last_refreshed_at: null,
    });

    render(<DashboardPage />);
    await screen.findByTestId("empty-state");

    await user.click(screen.getByText("+ Add Stock"));
    await user.type(screen.getByLabelText("Ticker symbol"), "aapl");
    await user.click(screen.getByRole("button", { name: "Add Stock" }));

    // the input uppercases as you type, so the call is made with "AAPL"
    await waitFor(() => expect(addStockSpy).toHaveBeenCalledWith("AAPL"));
  });

  it("shows a clear error and does not add the stock when the ticker is invalid", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "listWatchlist").mockResolvedValue([]);
    vi.spyOn(api, "addStock").mockRejectedValue(new api.ApiError('No price history found for "ZZZZZZ". Check the symbol and try again.', 422));

    render(<DashboardPage />);
    await screen.findByTestId("empty-state");

    await user.click(screen.getByText("+ Add Stock"));
    await user.type(screen.getByLabelText("Ticker symbol"), "zzzzzz");
    await user.click(screen.getByRole("button", { name: "Add Stock" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/No price history found/);
  });

  it("removes a stock after confirmation", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.spyOn(api, "listWatchlist").mockResolvedValue([
      { id: 1, ticker: "NVDA", company_name: null, data_source: "twelve_data", created_at: null, updated_at: null, last_refreshed_at: null },
    ]);
    vi.spyOn(api, "getStockAnalysis").mockResolvedValue(makeStockAnalysis());
    const removeSpy = vi.spyOn(api, "removeStock").mockResolvedValue(undefined);

    render(<DashboardPage />);
    const card = await screen.findByTestId("stock-card-NVDA");

    await user.click(within(card).getByText("Remove"));

    await waitFor(() => expect(removeSpy).toHaveBeenCalledWith("NVDA"));
  });

  it("does not remove a stock if the user cancels the confirmation", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(false);
    vi.spyOn(api, "listWatchlist").mockResolvedValue([
      { id: 1, ticker: "NVDA", company_name: null, data_source: "twelve_data", created_at: null, updated_at: null, last_refreshed_at: null },
    ]);
    vi.spyOn(api, "getStockAnalysis").mockResolvedValue(makeStockAnalysis());
    const removeSpy = vi.spyOn(api, "removeStock").mockResolvedValue(undefined);

    render(<DashboardPage />);
    const card = await screen.findByTestId("stock-card-NVDA");
    await user.click(within(card).getByText("Remove"));

    expect(removeSpy).not.toHaveBeenCalled();
  });

  it("shows a per-card error without blanking the rest of the dashboard when one stock fails", async () => {
    vi.spyOn(api, "listWatchlist").mockResolvedValue([
      { id: 1, ticker: "NVDA", company_name: null, data_source: "twelve_data", created_at: null, updated_at: null, last_refreshed_at: null },
      { id: 2, ticker: "AMD", company_name: null, data_source: "twelve_data", created_at: null, updated_at: null, last_refreshed_at: null },
    ]);
    vi.spyOn(api, "getStockAnalysis").mockImplementation(async (ticker: string) => {
      if (ticker === "NVDA") throw new api.ApiError("Champion models are not trained yet.", 503);
      return makeStockAnalysis({ ticker: "AMD" });
    });

    render(<DashboardPage />);

    const nvdaCard = await screen.findByTestId("stock-card-NVDA");
    expect(within(nvdaCard).getByTestId("error-state")).toHaveTextContent("Champion models are not trained yet.");

    const amdCard = await screen.findByTestId("stock-card-AMD");
    expect(within(amdCard).getByText("Open Full Analysis")).toBeInTheDocument();
  });
});
