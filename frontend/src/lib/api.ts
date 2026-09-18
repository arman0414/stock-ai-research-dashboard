import type {
  AlertRule,
  AlertStatus,
  AlertType,
  DailyRunStatus,
  Horizon,
  LiveEntrySetup,
  ModelLivePerformance,
  ModelPerformanceSummary,
  ModelReviewStatus,
  MultiHorizonPrediction,
  NeverRunStatus,
  NewsArticle,
  NewsProviderHealth,
  NewsRefreshResult,
  Position,
  PositionInput,
  PredictionHistoryRecord,
  PriceBarPoint,
  PriceRange,
  QuoteResult,
  RefreshAllResult,
  RefreshResult,
  ResolveOutcomesResult,
  SentimentSummary,
  StockAnalysis,
  StockDetail,
  StockLivePerformance,
  StockStructure,
  WatchlistItem,
} from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
    });
  } catch {
    throw new ApiError(`Could not reach the backend at ${API_BASE_URL}. Is it running?`, 0);
  }

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      // response body wasn't JSON; keep statusText
    }
    throw new ApiError(detail, response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

// ---------------------------------------------------------------------------
// Watchlist
// ---------------------------------------------------------------------------

export function listWatchlist(): Promise<WatchlistItem[]> {
  return request<WatchlistItem[]>("/stocks");
}

export function getStockDetail(ticker: string): Promise<StockDetail> {
  return request<StockDetail>(`/stocks/${encodeURIComponent(ticker)}`);
}

export async function addStock(ticker: string): Promise<WatchlistItem> {
  const normalized = ticker.trim().toUpperCase();
  const created = await request<WatchlistItem>("/stocks", {
    method: "POST",
    body: JSON.stringify({ ticker: normalized }),
  });

  try {
    await request<RefreshResult>(`/stocks/${encodeURIComponent(normalized)}/refresh?years=5`, { method: "POST" });
    const detail = await getStockDetail(normalized);
    if (detail.price_history_count === 0) {
      throw new Error("no history");
    }
  } catch {
    // Whatever failed underneath (provider error, no rows, etc.), a non-technical
    // user just needs to know the symbol didn't work -- not the raw backend detail.
    await removeStock(normalized).catch(() => undefined);
    throw new ApiError(`Could not fetch data for "${normalized}". Check the symbol and try again.`, 422);
  }

  return created;
}

export function removeStock(ticker: string): Promise<void> {
  return request<void>(`/stocks/${encodeURIComponent(ticker)}`, { method: "DELETE" });
}

export function refreshStock(ticker: string, years = 5): Promise<RefreshResult> {
  return request<RefreshResult>(`/stocks/${encodeURIComponent(ticker)}/refresh?years=${years}`, { method: "POST" });
}

export function refreshAllStocks(years = 5): Promise<RefreshAllResult> {
  return request<RefreshAllResult>(`/refresh/all?years=${years}`, { method: "POST" });
}

// ---------------------------------------------------------------------------
// Predictions / analysis
// ---------------------------------------------------------------------------

export function getStockAnalysis(ticker: string, store = false): Promise<StockAnalysis> {
  return request<StockAnalysis>(`/stocks/${encodeURIComponent(ticker)}/analysis${store ? "?store=true" : ""}`);
}

export function getPrediction(ticker: string, store = false): Promise<MultiHorizonPrediction> {
  return request<MultiHorizonPrediction>(`/stocks/${encodeURIComponent(ticker)}/prediction${store ? "?store=true" : ""}`);
}

export function getStockStructure(ticker: string): Promise<StockStructure> {
  return request<StockStructure>(`/stocks/${encodeURIComponent(ticker)}/structure`);
}

export function getPriceHistory(ticker: string, range: PriceRange = "6M"): Promise<PriceBarPoint[]> {
  return request<PriceBarPoint[]>(`/stocks/${encodeURIComponent(ticker)}/prices?range=${range}`);
}

// ---------------------------------------------------------------------------
// News
// ---------------------------------------------------------------------------

export function getNews(ticker: string, limit = 20): Promise<NewsArticle[]> {
  return request<NewsArticle[]>(`/stocks/${encodeURIComponent(ticker)}/news?limit=${limit}`);
}

export function refreshNews(ticker: string, days = 3, analyzeSentiment = true): Promise<NewsRefreshResult> {
  return request<NewsRefreshResult>(`/stocks/${encodeURIComponent(ticker)}/news/refresh?days=${days}&analyze_sentiment=${analyzeSentiment}`, { method: "POST" });
}

export function getSentimentSummary(ticker: string): Promise<SentimentSummary> {
  return request<SentimentSummary>(`/stocks/${encodeURIComponent(ticker)}/sentiment`);
}

export function getNewsProviderStatus(): Promise<NewsProviderHealth> {
  return request<NewsProviderHealth>("/news/providers/status");
}

// ---------------------------------------------------------------------------
// Positions -- backend returns Decimal fields as JSON strings; normalize here
// so every component downstream only ever sees plain numbers.
// ---------------------------------------------------------------------------

interface RawPosition {
  id: number;
  ticker: string;
  shares: string | number;
  purchase_price: string | number;
  purchase_date: string;
  my_target_price: string | number | null;
  stop_loss_price: string | number | null;
  notes: string | null;
  created_at: string | null;
  updated_at: string | null;
}

function toNumberOrNull(value: string | number | null): number | null {
  if (value === null || value === undefined) return null;
  const parsed = typeof value === "number" ? value : parseFloat(value);
  return Number.isNaN(parsed) ? null : parsed;
}

function normalizePosition(raw: RawPosition): Position {
  return {
    ...raw,
    shares: toNumberOrNull(raw.shares) ?? 0,
    purchase_price: toNumberOrNull(raw.purchase_price) ?? 0,
    my_target_price: toNumberOrNull(raw.my_target_price),
    stop_loss_price: toNumberOrNull(raw.stop_loss_price),
  };
}

export async function listPositions(): Promise<Position[]> {
  const raw = await request<RawPosition[]>("/positions");
  return raw.map(normalizePosition);
}

export async function createPosition(input: PositionInput): Promise<Position> {
  const raw = await request<RawPosition>("/positions", { method: "POST", body: JSON.stringify(input) });
  return normalizePosition(raw);
}

export async function updatePosition(id: number, input: Partial<PositionInput>): Promise<Position> {
  const raw = await request<RawPosition>(`/positions/${id}`, { method: "PATCH", body: JSON.stringify(input) });
  return normalizePosition(raw);
}

export function deletePosition(id: number): Promise<void> {
  return request<void>(`/positions/${id}`, { method: "DELETE" });
}

export async function getPositionCurrentPrice(id: number): Promise<number | null> {
  const result = await request<{ ticker: string; current_price: string | number | null }>(`/positions/${id}/current-price`);
  return toNumberOrNull(result.current_price);
}

// ---------------------------------------------------------------------------
// Alerts
// ---------------------------------------------------------------------------

interface RawAlertRule {
  id: number;
  ticker: string;
  alert_type: AlertType;
  threshold_price: string | number | null;
  is_active: boolean;
  last_triggered_at: string | null;
  last_triggered_message: string | null;
  created_at: string | null;
}

function normalizeAlertRule(raw: RawAlertRule): AlertRule {
  return { ...raw, threshold_price: toNumberOrNull(raw.threshold_price) };
}

export async function listAlerts(ticker?: string): Promise<AlertRule[]> {
  const raw = await request<RawAlertRule[]>(`/alerts${ticker ? `?ticker=${encodeURIComponent(ticker)}` : ""}`);
  return raw.map(normalizeAlertRule);
}

export async function createAlert(ticker: string, alertType: AlertType, thresholdPrice?: number | null): Promise<AlertRule> {
  const raw = await request<RawAlertRule>("/alerts", {
    method: "POST",
    body: JSON.stringify({ ticker, alert_type: alertType, threshold_price: thresholdPrice ?? null }),
  });
  return normalizeAlertRule(raw);
}

export function deleteAlert(id: number): Promise<void> {
  return request<void>(`/alerts/${id}`, { method: "DELETE" });
}

export async function checkAlerts(ticker?: string): Promise<AlertStatus[]> {
  interface RawAlertStatus {
    rule: RawAlertRule;
    is_triggered: boolean;
    message: string | null;
    current_price: string | number | null;
    model_5d_signal: string | null;
  }
  const raw = await request<RawAlertStatus[]>(`/alerts/check${ticker ? `?ticker=${encodeURIComponent(ticker)}` : ""}`);
  return raw.map((item) => ({
    rule: normalizeAlertRule(item.rule),
    is_triggered: item.is_triggered,
    message: item.message,
    current_price: toNumberOrNull(item.current_price),
    model_5d_signal: item.model_5d_signal,
  }));
}

// ---------------------------------------------------------------------------
// Model performance
// ---------------------------------------------------------------------------

export function getModelPerformance(): Promise<ModelPerformanceSummary> {
  return request<ModelPerformanceSummary>("/models/performance");
}

export function getHealth(): Promise<{ status: string }> {
  return request<{ status: string }>("/health");
}

// ---------------------------------------------------------------------------
// Live forward-evaluation: prediction history + performance
// ---------------------------------------------------------------------------

export function getPredictionHistory(ticker: string, horizon?: Horizon, limit = 50): Promise<PredictionHistoryRecord[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (horizon) params.set("horizon", horizon);
  return request<PredictionHistoryRecord[]>(`/stocks/${encodeURIComponent(ticker)}/predictions/history?${params.toString()}`);
}

export function getPredictionPerformance(ticker: string): Promise<StockLivePerformance> {
  return request<StockLivePerformance>(`/stocks/${encodeURIComponent(ticker)}/predictions/performance`);
}

export function getModelLivePerformance(): Promise<ModelLivePerformance> {
  return request<ModelLivePerformance>("/models/live-performance");
}

export function resolvePredictionOutcomes(ticker?: string): Promise<ResolveOutcomesResult> {
  return request<ResolveOutcomesResult>(`/predictions/resolve-outcomes${ticker ? `?ticker=${encodeURIComponent(ticker)}` : ""}`, { method: "POST" });
}

// ---------------------------------------------------------------------------
// Daily automation: scheduled run status + model review readiness
// ---------------------------------------------------------------------------

export function getDailyRunStatus(): Promise<DailyRunStatus | NeverRunStatus> {
  return request<DailyRunStatus | NeverRunStatus>("/system/daily-run-status");
}

export function getModelReviewStatus(): Promise<ModelReviewStatus> {
  return request<ModelReviewStatus>("/models/review-status");
}

// ---------------------------------------------------------------------------
// CURRENT PRICE: fresh/latest quotes
// ---------------------------------------------------------------------------

export function getStockQuote(ticker: string): Promise<QuoteResult> {
  return request<QuoteResult>(`/stocks/${encodeURIComponent(ticker)}/quote`);
}

export function getStockQuotes(tickers: string[]): Promise<Record<string, QuoteResult>> {
  if (tickers.length === 0) return Promise.resolve({});
  const params = new URLSearchParams({ tickers: tickers.join(",") });
  return request<{ quotes: Record<string, QuoteResult> }>(`/quotes?${params.toString()}`).then((response) => response.quotes);
}

// ---------------------------------------------------------------------------
// ENTRY SETUP: live, on-demand research interpretation (never persisted)
// ---------------------------------------------------------------------------

export function getEntrySetup(ticker: string, horizon: Horizon = "5d"): Promise<LiveEntrySetup> {
  return request<LiveEntrySetup>(`/stocks/${encodeURIComponent(ticker)}/entry-setup?horizon=${horizon}`);
}

export { API_BASE_URL };
