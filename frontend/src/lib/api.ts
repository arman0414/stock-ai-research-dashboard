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
  ClosedPosition,
  PortfolioSummary,
  Position,
  PositionInput,
  PositionTransaction,
  TradeInput,
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
  average_cost: string | number;
  total_cost_basis: string | number;
  purchase_date: string;
  my_target_price: string | number | null;
  stop_loss_price: string | number | null;
  notes: string | null;
  realized_pl: string | number;
  lifetime_realized_pl: string | number;
  cycle_index: number;
  is_open: boolean;
  closed_at: string | null;
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
    average_cost: toNumberOrNull(raw.average_cost) ?? toNumberOrNull(raw.purchase_price) ?? 0,
    total_cost_basis: toNumberOrNull(raw.total_cost_basis) ?? 0,
    my_target_price: toNumberOrNull(raw.my_target_price),
    stop_loss_price: toNumberOrNull(raw.stop_loss_price),
    realized_pl: toNumberOrNull(raw.realized_pl) ?? 0,
    lifetime_realized_pl: toNumberOrNull(raw.lifetime_realized_pl) ?? 0,
  };
}

// ---------------------------------------------------------------------------
// Position transactions -- buying/selling goes through the ledger so history
// and realized P/L are preserved. The backend is authoritative for all P/L.
// ---------------------------------------------------------------------------

type RawTransaction = Record<string, string | number | boolean | null>;

function normalizeTransaction(raw: RawTransaction): PositionTransaction {
  return {
    id: Number(raw.id),
    ticker: String(raw.ticker),
    transaction_type: String(raw.transaction_type) as PositionTransaction["transaction_type"],
    quantity: toNumberOrNull(raw.quantity as string | number) ?? 0,
    price_per_share: toNumberOrNull(raw.price_per_share as string | number) ?? 0,
    fees: toNumberOrNull(raw.fees as string | number) ?? 0,
    transaction_date: (raw.transaction_date as string | null) ?? null,
    notes: (raw.notes as string | null) ?? null,
    source: String(raw.source ?? "manual"),
    cycle_index: Number(raw.cycle_index ?? 1),
    cost_basis_per_share: toNumberOrNull(raw.cost_basis_per_share as string | number | null),
    cost_basis_total: toNumberOrNull(raw.cost_basis_total as string | number | null),
    sale_proceeds: toNumberOrNull(raw.sale_proceeds as string | number | null),
    realized_profit_loss: toNumberOrNull(raw.realized_profit_loss as string | number | null),
    realized_profit_loss_pct: toNumberOrNull(raw.realized_profit_loss_pct as string | number | null),
    created_at: (raw.created_at as string | null) ?? null,
  };
}

export async function buyShares(ticker: string, input: TradeInput): Promise<Position> {
  const raw = await request<RawPosition>(`/positions/${encodeURIComponent(ticker)}/buy`, { method: "POST", body: JSON.stringify(input) });
  return normalizePosition(raw);
}

export async function sellShares(ticker: string, input: TradeInput): Promise<Position> {
  const raw = await request<RawPosition>(`/positions/${encodeURIComponent(ticker)}/sell`, { method: "POST", body: JSON.stringify(input) });
  return normalizePosition(raw);
}

export async function listTransactions(params: { ticker?: string; transactionType?: string } = {}): Promise<PositionTransaction[]> {
  const query = new URLSearchParams();
  if (params.ticker) query.set("ticker", params.ticker);
  if (params.transactionType) query.set("transaction_type", params.transactionType);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  const raw = await request<RawTransaction[]>(`/positions/transactions${suffix}`);
  return raw.map(normalizeTransaction);
}

export async function listClosedPositions(): Promise<ClosedPosition[]> {
  const raw = await request<Record<string, string | number | null>[]>("/positions/closed");
  return raw.map((row) => ({
    ticker: String(row.ticker),
    cycle_index: Number(row.cycle_index ?? 1),
    total_shares_sold: toNumberOrNull(row.total_shares_sold as string | number) ?? 0,
    total_cost_basis: toNumberOrNull(row.total_cost_basis as string | number) ?? 0,
    total_proceeds: toNumberOrNull(row.total_proceeds as string | number) ?? 0,
    realized_profit_loss: toNumberOrNull(row.realized_profit_loss as string | number) ?? 0,
    return_pct: toNumberOrNull(row.return_pct as string | number) ?? 0,
    first_buy_date: (row.first_buy_date as string | null) ?? null,
    final_sell_date: (row.final_sell_date as string | null) ?? null,
  }));
}

export async function getPortfolioSummary(): Promise<PortfolioSummary> {
  const row = await request<Record<string, string | number>>("/positions/summary");
  return {
    portfolio_value: toNumberOrNull(row.portfolio_value) ?? 0,
    open_cost_basis: toNumberOrNull(row.open_cost_basis) ?? 0,
    unrealized_pl: toNumberOrNull(row.unrealized_pl) ?? 0,
    unrealized_pl_pct: toNumberOrNull(row.unrealized_pl_pct) ?? 0,
    realized_pl: toNumberOrNull(row.realized_pl) ?? 0,
    total_pl: toNumberOrNull(row.total_pl) ?? 0,
    open_position_count: Number(row.open_position_count ?? 0),
    priced_position_count: Number(row.priced_position_count ?? 0),
  };
}

export function deleteTransaction(id: number): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>(`/positions/transactions/${id}`, { method: "DELETE" });
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
