import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import StockDetailPage from "./[ticker]/page";
import * as api from "@/lib/api";
import { makePredictionHistoryRecord, makeStockAnalysis, makeStockLivePerformance } from "@/lib/testFixtures";

vi.mock("lightweight-charts", () => ({
  createChart: () => ({
    addSeries: () => ({ setData: () => {}, createPriceLine: () => ({}), removePriceLine: () => {} }),
    timeScale: () => ({ fitContent: () => {} }),
    applyOptions: () => {},
    remove: () => {},
  }),
  CandlestickSeries: {},
  ColorType: { Solid: "solid" },
}));

function renderPage(ticker = "NVDA") {
  return render(<StockDetailPage params={Promise.resolve({ ticker })} />);
}

describe("StockDetailPage", () => {
  it("loads and renders price, forecast cards, structure, news, and market context", async () => {
    vi.spyOn(api, "getStockDetail").mockResolvedValue({
      id: 1,
      ticker: "NVDA",
      company_name: "NVIDIA Corporation",
      data_source: "twelve_data",
      created_at: null,
      updated_at: null,
      last_refreshed_at: "2026-09-11T00:00:00Z",
      latest_price: 218.29,
      latest_price_date: "2026-09-11",
      price_history_count: 1200,
    });
    vi.spyOn(api, "getStockAnalysis").mockResolvedValue(makeStockAnalysis());
    vi.spyOn(api, "getNews").mockResolvedValue([]);
    vi.spyOn(api, "getSentimentSummary").mockResolvedValue({
      ticker: "NVDA",
      articles_7d: 0,
      positive: 0,
      neutral: 0,
      negative: 0,
      average_sentiment: 0,
      sentiment_direction: "NEUTRAL",
      last_updated: null,
    });
    vi.spyOn(api, "getPriceHistory").mockResolvedValue([]);
    vi.spyOn(api, "getPredictionHistory").mockResolvedValue([makePredictionHistoryRecord()]);
    vi.spyOn(api, "getPredictionPerformance").mockResolvedValue(makeStockLivePerformance());
    vi.spyOn(api, "getStockQuotes").mockResolvedValue({});

    renderPage();

    expect(await screen.findByRole("heading", { name: "NVDA" })).toBeInTheDocument();
    expect(await screen.findByText("NVIDIA Corporation")).toBeInTheDocument();
    expect(screen.getByTestId("prediction-card-5d")).toBeInTheDocument();
    expect(screen.getByTestId("prediction-card-10d")).toBeInTheDocument();
    expect(screen.getByTestId("prediction-card-15d")).toBeInTheDocument();
    expect(screen.getByText("Why The Model Sees This")).toBeInTheDocument();
    expect(screen.getAllByText("Market Context").length).toBeGreaterThan(0);
    expect(screen.getByText("Latest News")).toBeInTheDocument();
    expect(screen.getByText("Run New Analysis")).toBeInTheDocument();
    expect(screen.getByTestId("research-checklist")).toBeInTheDocument();
    expect(screen.getByTestId("what-does-this-mean")).toBeInTheDocument();
    expect(await screen.findByText("Prediction History")).toBeInTheDocument();
    expect(screen.getByTestId("live-forecast-performance")).toBeInTheDocument();
  });

  it("shows an error state instead of a blank page when the backend call fails", async () => {
    vi.spyOn(api, "getStockDetail").mockRejectedValue(new api.ApiError("Stock not found", 404));
    vi.spyOn(api, "getStockAnalysis").mockRejectedValue(new api.ApiError("Stock not found", 404));
    vi.spyOn(api, "getNews").mockResolvedValue([]);
    vi.spyOn(api, "getSentimentSummary").mockResolvedValue({
      ticker: "ZZZZ",
      articles_7d: 0,
      positive: 0,
      neutral: 0,
      negative: 0,
      average_sentiment: 0,
      sentiment_direction: "NEUTRAL",
      last_updated: null,
    });
    vi.spyOn(api, "getPriceHistory").mockResolvedValue([]);
    vi.spyOn(api, "getPredictionHistory").mockResolvedValue([]);
    vi.spyOn(api, "getPredictionPerformance").mockResolvedValue(makeStockLivePerformance({ ticker: "ZZZZ" }));
    vi.spyOn(api, "getStockQuotes").mockResolvedValue({});

    renderPage("ZZZZ");

    expect(await screen.findByTestId("error-state")).toHaveTextContent("Stock not found");
  });
});
