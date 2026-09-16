import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ForecastHorizonPage from "./[horizon]/page";
import * as api from "@/lib/api";
import { makeEntrySetupResult, makeLiveEntrySetup, makePredictionHistoryRecord, makeQuoteResult } from "@/lib/testFixtures";
import type { SentimentSummary, StockStructure } from "@/lib/types";

const TRACKED = ["NVDA", "AMD", "MU", "TSLA", "IREN"];

const DAILY_RUN_STATUS = {
  status: "NEVER_RUN" as const,
  tracked_tickers: TRACKED,
  tracked_ticker_count: 5,
  predictions_per_market_day: 15,
};

function structureFor(ticker: string): StockStructure {
  return {
    ticker,
    date: "2026-09-15",
    current_price: 210.96,
    market_structure: "NEUTRAL",
    buyer_pressure: "MODERATE",
    seller_pressure: "MODERATE",
    nearest_support: 207.25,
    nearest_resistance: 234.76,
    distance_to_support: 0.02,
    distance_to_resistance: 0.11,
    support_strength: "MODERATE",
    resistance_strength: "MODERATE",
    breakout_status: "RANGE_BOUND",
    important_observations: [],
  };
}

function sentimentFor(ticker: string): SentimentSummary {
  return {
    ticker,
    articles_7d: 10,
    positive: 6,
    neutral: 3,
    negative: 1,
    average_sentiment: 0.2,
    sentiment_direction: "POSITIVE",
    last_updated: "2026-09-15T21:31:00Z",
  };
}

function makeParams(horizon: string) {
  return Promise.resolve({ horizon });
}

describe("ForecastHorizonPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(api, "getDailyRunStatus").mockResolvedValue(DAILY_RUN_STATUS);
    vi.spyOn(api, "getStockStructure").mockImplementation((ticker: string) => Promise.resolve(structureFor(ticker)));
    vi.spyOn(api, "getSentimentSummary").mockImplementation((ticker: string) => Promise.resolve(sentimentFor(ticker)));
    vi.spyOn(api, "getStockQuotes").mockResolvedValue(
      Object.fromEntries(TRACKED.map((ticker) => [ticker, makeQuoteResult({ ticker, price: 214.3 })]))
    );
    vi.spyOn(api, "getEntrySetup").mockImplementation((ticker: string) => Promise.resolve(makeLiveEntrySetup({ ticker })));
  });

  it("renders only 5D forecast data on the 5D page, for all five tracked stocks", async () => {
    vi.spyOn(api, "getPredictionHistory").mockImplementation((ticker: string, horizon) =>
      Promise.resolve([makePredictionHistoryRecord({ ticker, horizon: horizon ?? "5d", model_target_price: 213.0, current_price: 210.96 })])
    );

    render(<ForecastHorizonPage params={makeParams("5d")} />);

    for (const ticker of TRACKED) {
      expect(await screen.findByTestId(`forecast-card-${ticker}`)).toBeInTheDocument();
    }
    expect(screen.getByText("5-Day Stock Forecasts")).toBeInTheDocument();
    expect(screen.getAllByText("$213.00").length).toBe(TRACKED.length);
    expect(screen.getByText("Best Current Horizon")).toBeInTheDocument();
  });

  it("renders only 10D forecast data on the 10D page and never mixes in 5D values", async () => {
    vi.spyOn(api, "getPredictionHistory").mockImplementation((ticker: string, horizon) => {
      const price = horizon === "10d" ? 221.5 : 213.0; // 5D would be 213.00 -- must never leak in
      return Promise.resolve([makePredictionHistoryRecord({ ticker, horizon: horizon ?? "10d", model_target_price: price, current_price: 210.96 })]);
    });

    render(<ForecastHorizonPage params={makeParams("10d")} />);

    await screen.findByTestId("forecast-card-NVDA");
    expect(screen.getByText("10-Day Stock Forecasts")).toBeInTheDocument();
    expect(screen.getAllByText("$221.50").length).toBe(TRACKED.length);
    expect(screen.queryByText("$213.00")).not.toBeInTheDocument();
    expect(screen.queryByText("Best Current Horizon")).not.toBeInTheDocument();
  });

  it("shows the lower-reliability note on the 15D page, and hides the forecast for a ticker with none", async () => {
    vi.spyOn(api, "getPredictionHistory").mockImplementation((ticker: string, horizon) => {
      if (ticker === "IREN") return Promise.resolve([]); // no 15D forecast yet for IREN
      return Promise.resolve([makePredictionHistoryRecord({ ticker, horizon: horizon ?? "15d", model_target_price: 212.1, current_price: 210.96 })]);
    });

    render(<ForecastHorizonPage params={makeParams("15d")} />);

    await screen.findByTestId("forecast-card-NVDA");
    expect(screen.getByText(/15-day forecasts currently have lower historical reliability/)).toBeInTheDocument();

    const irenCard = screen.getByTestId("forecast-card-IREN");
    expect(within(irenCard).getByText("No current 15-day forecast available.")).toBeInTheDocument();
  });

  it("shows the fresh Current Price from the quote endpoint, not the frozen prediction start price", async () => {
    vi.spyOn(api, "getPredictionHistory").mockResolvedValue([
      makePredictionHistoryRecord({ ticker: "NVDA", horizon: "5d", prediction_date: "2026-09-15", current_price: 210.96, model_target_price: 213.0 }),
    ]);

    render(<ForecastHorizonPage params={makeParams("5d")} />);

    const card = await screen.findByTestId("forecast-card-NVDA");
    expect(await within(card).findByText("$214.30")).toBeInTheDocument(); // the live quote
    // The frozen start price and prediction date, unmodified by the live quote (text spans multiple nodes, so check textContent).
    expect(card.textContent).toMatch(/Sep 15, 2026 close at \$210\.96/);
  });

  it("keeps the page usable when one ticker's quote fails", async () => {
    vi.spyOn(api, "getPredictionHistory").mockResolvedValue([makePredictionHistoryRecord({ ticker: "NVDA", horizon: "5d" })]);
    vi.spyOn(api, "getStockQuotes").mockResolvedValue({
      NVDA: makeQuoteResult({ ticker: "NVDA", price: 214.3 }),
      // AMD, MU, TSLA, IREN missing entirely, simulating a partial provider failure
    });

    render(<ForecastHorizonPage params={makeParams("5d")} />);

    for (const ticker of TRACKED) {
      expect(await screen.findByTestId(`forecast-card-${ticker}`)).toBeInTheDocument();
    }
  });

  it("defaults to the configured tracking order, not an automatic best-stock ranking", async () => {
    vi.spyOn(api, "getPredictionHistory").mockImplementation((ticker: string, horizon) =>
      // Give AMD the biggest expected move -- if the page silently sorted by "best," AMD would jump to the top.
      Promise.resolve([makePredictionHistoryRecord({ ticker, horizon: horizon ?? "5d", predicted_return: ticker === "AMD" ? 0.5 : 0.01 })])
    );

    render(<ForecastHorizonPage params={makeParams("5d")} />);

    await screen.findByTestId("forecast-card-NVDA");
    const cards = screen.getAllByTestId(/forecast-card-/);
    expect(cards.map((card) => card.getAttribute("data-testid"))).toEqual(TRACKED.map((ticker) => `forecast-card-${ticker}`));
  });

  it("displays News Mood without implying a probability of the stock going up", async () => {
    vi.spyOn(api, "getPredictionHistory").mockResolvedValue([makePredictionHistoryRecord({ ticker: "NVDA", horizon: "5d" })]);

    render(<ForecastHorizonPage params={makeParams("5d")} />);

    const card = await screen.findByTestId("forecast-card-NVDA");
    expect(within(card).getByText("News Mood")).toBeInTheDocument();
    expect(within(card).getByText("Positive")).toBeInTheDocument();
    expect(within(card).getByText("6 of 10 recent articles positive")).toBeInTheDocument();
    expect(card.textContent).not.toMatch(/probability.*(goes|going) up/i);
  });

  it("shows GOOD SETUP, predicted upside, support/resistance distance, and reward/risk on the card", async () => {
    vi.spyOn(api, "getPredictionHistory").mockResolvedValue([makePredictionHistoryRecord({ ticker: "NVDA", horizon: "5d", current_price: 210.96, model_target_price: 213.0 })]);
    vi.spyOn(api, "getEntrySetup").mockResolvedValue(makeLiveEntrySetup({ ticker: "NVDA", entry_setup: makeEntrySetupResult({ state: "GOOD_SETUP" }) }));

    render(<ForecastHorizonPage params={makeParams("5d")} />);

    const card = await screen.findByTestId("forecast-card-NVDA");
    expect(within(card).getByText("GOOD SETUP")).toBeInTheDocument();
    expect(within(card).getByTestId("expected-upside")).toBeInTheDocument();
    // Support/resistance distance is computed on the card itself from the live quote ($214.30) and structure (support $207.25 / resistance $234.76).
    expect(within(card).getByText(/below current/)).toBeInTheDocument();
    expect(within(card).getByText(/above current/)).toBeInTheDocument();
    expect(within(card).getByText("2.0x")).toBeInTheDocument();
  });

  it("shows a WATCH entry setup on the card", async () => {
    vi.spyOn(api, "getPredictionHistory").mockResolvedValue([makePredictionHistoryRecord({ ticker: "NVDA", horizon: "5d" })]);
    vi.spyOn(api, "getEntrySetup").mockResolvedValue(makeLiveEntrySetup({ ticker: "NVDA", entry_setup: makeEntrySetupResult({ state: "WATCH" }) }));

    render(<ForecastHorizonPage params={makeParams("5d")} />);

    const card = await screen.findByTestId("forecast-card-NVDA");
    expect(within(card).getByText("WATCH")).toBeInTheDocument();
  });

  it("shows a WAIT entry setup on the card", async () => {
    vi.spyOn(api, "getPredictionHistory").mockResolvedValue([makePredictionHistoryRecord({ ticker: "NVDA", horizon: "5d" })]);
    vi.spyOn(api, "getEntrySetup").mockResolvedValue(makeLiveEntrySetup({ ticker: "NVDA", entry_setup: makeEntrySetupResult({ state: "WAIT" }) }));

    render(<ForecastHorizonPage params={makeParams("5d")} />);

    const card = await screen.findByTestId("forecast-card-NVDA");
    expect(within(card).getByText("WAIT")).toBeInTheDocument();
  });

  it("expands the plain-language Why? checklist on the forecast card", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "getPredictionHistory").mockResolvedValue([makePredictionHistoryRecord({ ticker: "NVDA", horizon: "5d" })]);
    vi.spyOn(api, "getEntrySetup").mockResolvedValue(
      makeLiveEntrySetup({ ticker: "NVDA", entry_setup: makeEntrySetupResult({ state: "GOOD_SETUP", reasons: [{ symbol: "check", text: "Bullish validated model signal" }] }) })
    );

    render(<ForecastHorizonPage params={makeParams("5d")} />);
    const card = await screen.findByTestId("forecast-card-NVDA");

    await user.click(within(card).getByText(/Why GOOD SETUP\?/));
    expect(within(card).getByText("Bullish validated model signal")).toBeInTheDocument();
  });

  it("never lets Entry Setup alter the displayed predicted price, return, or signal status", async () => {
    vi.spyOn(api, "getPredictionHistory").mockResolvedValue([
      makePredictionHistoryRecord({ ticker: "NVDA", horizon: "5d", model_target_price: 213.0, signal_status: "NO_STRONG_SIGNAL", predicted_return: 0.0097 }),
    ]);
    // A GOOD_SETUP entry setup response with a WILDLY different implied price -- must never leak into the card's own predicted price display.
    vi.spyOn(api, "getEntrySetup").mockResolvedValue(makeLiveEntrySetup({ ticker: "NVDA", predicted_price: 999.99, entry_setup: makeEntrySetupResult({ state: "GOOD_SETUP" }) }));

    render(<ForecastHorizonPage params={makeParams("5d")} />);

    const card = await screen.findByTestId("forecast-card-NVDA");
    expect(within(card).getByTestId("forecast-predicted-price")).toHaveTextContent("$213.00");
    expect(within(card).queryByText("$999.99")).not.toBeInTheDocument();
    expect(within(card).getByText("No Strong Signal")).toBeInTheDocument();
  });

  it("does not let News Mood alone determine the Entry Setup state", async () => {
    // Positive news, but the Entry Setup response is WAIT -- the card must
    // show both independently, never inferring GOOD SETUP from good news.
    vi.spyOn(api, "getPredictionHistory").mockResolvedValue([makePredictionHistoryRecord({ ticker: "NVDA", horizon: "5d" })]);
    vi.spyOn(api, "getSentimentSummary").mockResolvedValue({
      ticker: "NVDA",
      articles_7d: 10,
      positive: 9,
      neutral: 1,
      negative: 0,
      average_sentiment: 0.8,
      sentiment_direction: "POSITIVE",
      last_updated: "2026-09-15T21:31:00Z",
    });
    vi.spyOn(api, "getEntrySetup").mockResolvedValue(makeLiveEntrySetup({ ticker: "NVDA", entry_setup: makeEntrySetupResult({ state: "WAIT" }) }));

    render(<ForecastHorizonPage params={makeParams("5d")} />);

    const card = await screen.findByTestId("forecast-card-NVDA");
    expect(within(card).getByText("Positive")).toBeInTheDocument();
    expect(within(card).getByText("WAIT")).toBeInTheDocument();
    expect(within(card).queryByText("GOOD SETUP")).not.toBeInTheDocument();
  });
});
