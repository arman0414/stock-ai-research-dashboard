export type SignalStatus = "BULLISH" | "BEARISH" | "NO_STRONG_SIGNAL";
export type Direction = "UP" | "DOWN" | "NEUTRAL";
export type ConfidenceLabel = "NO_STRONG_SIGNAL" | "LOW" | "MEDIUM" | "HIGH" | "VERY_HIGH";
export type QualityLevel = "WEAK" | "MODERATE" | "STRONG" | "UNKNOWN";
export type TrendLabel = "BULLISH" | "BEARISH" | "NEUTRAL";
export type RelativeLabel = "OUTPERFORMING" | "UNDERPERFORMING" | "NEUTRAL";
export type SentimentDirection = "POSITIVE" | "NEGATIVE" | "NEUTRAL";
export type Horizon = "5d" | "10d" | "15d";

export const HORIZONS: Horizon[] = ["5d", "10d", "15d"];

export interface Classification {
  direction: Direction;
  raw_probability: number;
  calibrated_probability: number;
  calibrated_up_probability: number;
  calibrated_down_probability: number;
  signal_status: SignalStatus;
  confidence: ConfidenceLabel;
  gating_reason: string;
  historical_signal_accuracy: number | null;
  historical_signal_samples: number | null;
  historical_signal_precision: number | null;
  /** The calibrated-probability threshold this class needed to clear to fire,
   * or null if that class's signal isn't currently validated (e.g. insufficient
   * historical evidence). Used only to explain gating_reason -- never to
   * re-derive a signal decision client-side. */
  bullish_threshold: number | null;
  bearish_threshold: number | null;
}

export interface RegressionForecast {
  predicted_return: number;
  model_target_price: number;
  uncertainty_low: number;
  uncertainty_high: number;
  p50_abs_error: number | null;
}

export interface Setup {
  quality: QualityLevel;
  buyer_pressure: QualityLevel;
  seller_pressure: QualityLevel;
  support: number | null;
  resistance: number | null;
}

export interface ModelInfo {
  classification_version: string;
  regression_version: string;
  calibration_method: string;
  is_primary_research_horizon: boolean;
}

export interface HorizonPrediction {
  ticker: string;
  as_of: string;
  horizon: Horizon;
  current_price: number;
  classification: Classification;
  regression: RegressionForecast;
  setup: Setup;
  model: ModelInfo;
}

export interface MarketContext {
  spy_trend: TrendLabel;
  qqq_trend: TrendLabel;
  sector_trend: TrendLabel;
  sector_asset: string | null;
  stock_vs_market: RelativeLabel;
  stock_vs_sector: RelativeLabel;
}

export interface MultiHorizonPrediction {
  ticker: string;
  as_of: string;
  current_price: number;
  primary_research_horizon: string;
  predictions: Partial<Record<Horizon, HorizonPrediction | null>>;
  market_context: MarketContext;
  generated_at: string;
}

export interface StockStructure {
  ticker: string;
  date: string;
  current_price: number;
  market_structure: TrendLabel;
  buyer_pressure: QualityLevel;
  seller_pressure: QualityLevel;
  nearest_support: number | null;
  nearest_resistance: number | null;
  distance_to_support: number | null;
  distance_to_resistance: number | null;
  support_strength: QualityLevel;
  resistance_strength: QualityLevel;
  breakout_status: string;
  important_observations: string[];
}

export interface Explanation {
  positives: string[];
  risks: string[];
}

export interface StockAnalysis extends MultiHorizonPrediction {
  structure: StockStructure | null;
  explanation: Explanation;
}

export interface WatchlistItem {
  id: number;
  ticker: string;
  company_name: string | null;
  data_source: string;
  created_at: string | null;
  updated_at: string | null;
  last_refreshed_at: string | null;
}

export interface StockDetail extends WatchlistItem {
  latest_price: number | null;
  latest_price_date: string | null;
  price_history_count: number;
}

export interface PriceBarPoint {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export type PriceRange = "1M" | "3M" | "6M" | "1Y" | "5Y";
export const PRICE_RANGES: PriceRange[] = ["1M", "3M", "6M", "1Y", "5Y"];

export interface NewsArticleSentiment {
  label: string;
  positive_probability: number;
  neutral_probability: number;
  negative_probability: number;
  sentiment_score: number;
  model: string;
  model_version: string;
  analyzed_at: string;
}

export interface NewsArticle {
  id: number;
  ticker: string;
  headline: string;
  summary: string | null;
  source: string;
  published_at: string;
  url: string | null;
  provider: string;
  provider_sources: string[];
  external_id: string;
  author: string | null;
  event_category: string | null;
  /** relevant | uncertain | not_relevant -- only `relevant` counts toward News Mood. */
  relevance: string;
  sentiment: NewsArticleSentiment | null;
}

export interface NewsProviderRefreshStatus {
  provider: string;
  available: boolean;
  status: string;
  articles_received: number;
  error: string | null;
}

export interface NewsRefreshResult {
  ticker: string;
  start_time: string;
  end_time: string;
  providers: NewsProviderRefreshStatus[];
  articles_received: number;
  unique_articles: number;
  articles_created: number;
  articles_stored: number;
  articles_analyzed: number;
  relevant_saved: number;
  uncertain_saved: number;
  not_relevant_saved: number;
  sentiment_error: string | null;
  duplicates_skipped: number;
  skipped_due_to_recent_cache: boolean;
}

export interface NewsProviderHealthStatus {
  provider: string;
  available: boolean;
  status: string;
  last_news_refresh: string | null;
  error: string | null;
}

export interface NewsProviderHealth {
  providers: NewsProviderHealthStatus[];
}

export interface SentimentSummary {
  ticker: string;
  articles_7d: number;
  positive: number;
  neutral: number;
  negative: number;
  average_sentiment: number;
  sentiment_direction: SentimentDirection;
  last_updated: string | null;
  /** Providers behind the counted articles, e.g. ["finnhub", "yahoo_rss"]. */
  providers: string[];
  /** Recent analyzed articles skipped as unrelated/uncertain for this ticker. */
  excluded_unrelated: number;
  last_news_refresh: string | null;
}

export interface Position {
  id: number;
  ticker: string;
  /** Current quantity held, derived from the transaction ledger. */
  shares: number;
  /** Weighted-average cost per share (same value as `average_cost`). */
  purchase_price: number;
  average_cost: number;
  total_cost_basis: number;
  purchase_date: string;
  my_target_price: number | null;
  stop_loss_price: number | null;
  notes: string | null;
  /** Realized P/L for the current open cycle. */
  realized_pl: number;
  /** Realized P/L across every cycle for this ticker. */
  lifetime_realized_pl: number;
  cycle_index: number;
  is_open: boolean;
  closed_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export type TransactionType = "BUY" | "SELL";

export interface PositionTransaction {
  id: number;
  ticker: string;
  transaction_type: TransactionType;
  quantity: number;
  price_per_share: number;
  fees: number;
  transaction_date: string | null;
  notes: string | null;
  source: string;
  cycle_index: number;
  cost_basis_per_share: number | null;
  cost_basis_total: number | null;
  sale_proceeds: number | null;
  realized_profit_loss: number | null;
  realized_profit_loss_pct: number | null;
  created_at: string | null;
}

export interface ClosedPosition {
  ticker: string;
  cycle_index: number;
  total_shares_sold: number;
  total_cost_basis: number;
  total_proceeds: number;
  realized_profit_loss: number;
  return_pct: number;
  first_buy_date: string | null;
  final_sell_date: string | null;
}

export interface PortfolioSummary {
  portfolio_value: number;
  open_cost_basis: number;
  unrealized_pl: number;
  unrealized_pl_pct: number;
  realized_pl: number;
  total_pl: number;
  open_position_count: number;
  priced_position_count: number;
}

export interface TradeInput {
  quantity: number;
  price_per_share: number;
  transaction_date?: string | null;
  fees?: number;
  notes?: string | null;
}

export interface SellPreview {
  ticker: string;
  shares_owned: number;
  quantity: number;
  cost_basis_per_share: number;
  cost_basis_total: number;
  sale_proceeds: number;
  realized_profit_loss: number;
  realized_profit_loss_pct: number;
  remaining_shares: number;
  exceeds_position: boolean;
}

export interface PositionInput {
  ticker: string;
  shares: number;
  purchase_price: number;
  purchase_date: string;
  my_target_price?: number | null;
  stop_loss_price?: number | null;
  notes?: string | null;
}

export type AlertType =
  | "MY_TARGET_PRICE"
  | "MY_STOP_LOSS"
  | "MODEL_SIGNAL_CHANGED"
  | "BULLISH_SIGNAL_APPEARED"
  | "MAJOR_POSITIVE_NEWS"
  | "MAJOR_NEGATIVE_NEWS"
  | "UNUSUAL_VOLUME"
  | "SUPPORT_BREAK"
  | "RESISTANCE_BREAKOUT";

export const ALERT_TYPES: { value: AlertType; label: string; needsThreshold: boolean }[] = [
  { value: "MY_TARGET_PRICE", label: "My target price reached", needsThreshold: true },
  { value: "MY_STOP_LOSS", label: "My stop loss hit", needsThreshold: true },
  { value: "MODEL_SIGNAL_CHANGED", label: "Model signal changed", needsThreshold: false },
  { value: "BULLISH_SIGNAL_APPEARED", label: "Bullish signal appeared", needsThreshold: false },
  { value: "MAJOR_POSITIVE_NEWS", label: "Major positive news", needsThreshold: false },
  { value: "MAJOR_NEGATIVE_NEWS", label: "Major negative news", needsThreshold: false },
  { value: "UNUSUAL_VOLUME", label: "Unusual volume", needsThreshold: false },
  { value: "SUPPORT_BREAK", label: "Support break", needsThreshold: false },
  { value: "RESISTANCE_BREAKOUT", label: "Resistance breakout", needsThreshold: false },
];

export interface AlertRule {
  id: number;
  ticker: string;
  alert_type: AlertType;
  threshold_price: number | null;
  is_active: boolean;
  last_triggered_at: string | null;
  last_triggered_message: string | null;
  created_at: string | null;
}

export interface AlertStatus {
  rule: AlertRule;
  is_triggered: boolean;
  message: string | null;
  current_price: number | null;
  model_5d_signal: string | null;
}

export interface RefreshResult {
  ticker: string;
  source: string;
  start_date: string;
  end_date: string;
  rows_received: number;
  rows_stored: number;
  latest_price: number | null;
  latest_price_date: string | null;
}

export interface RefreshAllResult {
  refreshed: RefreshResult[];
  failed: Record<string, string>;
}

export interface CalibrationSelectionMetric {
  balanced_accuracy: number;
  log_loss: number;
  macro_f1: number;
  multiclass_brier: number;
}

export interface ReliabilityBucket {
  bucket: string;
  count: number;
  average_predicted_probability: number | null;
  actual_success_rate: number | null;
  difference: number | null;
}

export interface HorizonPerformance {
  status?: "NOT_TRAINED";
  status_label?: string;
  is_primary_research_horizon?: boolean;
  calibration_method?: string | null;
  calibration_selection_metrics?: Record<string, CalibrationSelectionMetric>;
  bullish_threshold?: number | null;
  bullish_status?: string;
  bearish_threshold?: number | null;
  bearish_status?: string;
  bullish_test_precision?: number | null;
  bullish_test_sample_count?: number | null;
  bearish_test_precision?: number | null;
  bearish_test_sample_count?: number | null;
  target_price_mae?: number | null;
  regression_mae?: number | null;
  within_5pct?: number | null;
  within_10pct?: number | null;
  direction_accuracy?: number | null;
  reliability_test_calibrated?: ReliabilityBucket[];
  multi_seed_balanced_accuracy_mean?: number | null;
  multi_seed_balanced_accuracy_std?: number | null;
}

export interface ModelPerformanceSummary {
  horizons: Partial<Record<Horizon, HorizonPerformance>>;
}

// ---------------------------------------------------------------------------
// Live forward-evaluation: prediction history + performance
// ---------------------------------------------------------------------------

export type OutcomeStatus = "PENDING" | "RESOLVED";
export type SignalOutcome = "CORRECT" | "INCORRECT" | "NOT_APPLICABLE";
export type PredictionSource = "LIVE_DAILY" | "MANUAL_LIVE" | "BACKFILLED_REPLAY";

export interface PredictionHistoryRecord {
  id: number;
  ticker: string;
  horizon: Horizon;
  prediction_date: string;
  generated_at: string | null;
  model_version: string;
  prediction_source: PredictionSource;
  current_price: number;
  predicted_class: Direction;
  raw_probability: number;
  calibrated_probability: number;
  signal_status: SignalStatus;
  confidence: ConfidenceLabel;
  predicted_return: number;
  model_target_price: number;
  uncertainty_low: number;
  uncertainty_high: number;
  classification_version: string;
  regression_version: string;
  calibration_method: string;
  outcome_status: OutcomeStatus;
  /** Displayed to users as "Final Day Price" -- the closing price on the
   * exact Nth future trading session, not calendar days after prediction_date. */
  actual_future_price: number | null;
  /** Displayed to users as "Final Day Date" -- the exact PriceBar date used
   * to resolve this prediction. Null while PENDING; show "Pending" in the UI,
   * never a calendar-arithmetic guess. */
  final_day_date: string | null;
  actual_return: number | null;
  signed_price_error: number | null;
  absolute_price_error: number | null;
  absolute_percentage_error: number | null;
  /** actual - predicted, in dollars. Opposite sign convention from signed_price_error. */
  signed_price_difference: number | null;
  /** actual - predicted, as a percentage NUMBER (1.50 means 1.50%, not a fraction). */
  signed_prediction_difference_pct: number | null;
  /** abs() of signed_prediction_difference_pct -- drives the ±2/±5/±10% accuracy bands. */
  absolute_prediction_difference_pct: number | null;
  regression_direction_match: boolean | null;
  signal_outcome: SignalOutcome | null;
  outcome_evaluated_at: string | null;
  /** Frozen at snapshot creation time -- never recomputed after the fact.
   * See EntrySetupResult for the live, on-demand equivalent. */
  entry_setup_state: EntrySetupState | null;
  entry_setup_version: string | null;
  entry_setup_reasons: EntrySetupReason[];
}

// ---------------------------------------------------------------------------
// ENTRY SETUP: a research interpretation layer on top of existing model
// outputs. Never BUY/SELL, never a numeric score. See
// stock_ai/services/entry_setup.py for the authoritative rules.
// ---------------------------------------------------------------------------

export type EntrySetupState = "GOOD_SETUP" | "WATCH" | "WAIT" | "INSUFFICIENT_DATA";

export interface EntrySetupReason {
  symbol: "check" | "cross" | "warning";
  text: string;
}

export interface EntrySetupResult {
  state: EntrySetupState;
  version: string;
  reasons: EntrySetupReason[];
  summary: string;
  expected_upside_pct: number | null;
  support_distance_pct: number | null;
  resistance_room_pct: number | null;
  potential_reward: number | null;
  potential_risk: number | null;
  research_reward_risk: number | null;
  reward_target_price: number | null;
  resistance_below_target: boolean;
  disclaimer: string;
}

export interface LiveEntrySetup {
  ticker: string;
  horizon: Horizon;
  available: boolean;
  reason?: string;
  prediction_date?: string;
  prediction_start_price?: number;
  predicted_price?: number;
  model_expected_move_pct?: number | null;
  signal_status?: SignalStatus;
  current_quote?: QuoteResult;
  entry_setup?: EntrySetupResult;
}

export interface LivePerformanceStats {
  resolved_count: number;
  within_2pct: number | null;
  within_5pct: number | null;
  within_10pct: number | null;
  more_than_10pct_off: number | null;
  direction_correct_rate: number | null;
  average_miss_pct: number | null;
}

export interface StockLivePerformance {
  ticker: string;
  horizons: Partial<Record<Horizon, LivePerformanceStats>>;
}

export interface ModelLivePerformanceHorizon extends Partial<LivePerformanceStats> {
  model_version?: string;
  status?: "NOT_TRAINED";
}

export interface ModelLivePerformance {
  /** The current DAILY_TRACKING_TICKERS list this aggregate is scoped to --
   * results from tickers outside this list are never blended in. */
  tracked_tickers: string[];
  horizons: Partial<Record<Horizon, ModelLivePerformanceHorizon>>;
}

export interface ResolveOutcomesResult {
  updated: number;
  skipped_not_due: number;
  total_pending: number;
}

// ---------------------------------------------------------------------------
// Daily automation: scheduled run status + model review readiness
// ---------------------------------------------------------------------------

export type DailyRunStatusValue = "RUNNING" | "SUCCESS" | "WAITING_FOR_MARKET_DATA" | "PARTIAL_FAILURE" | "FAILURE";
export type TickerFreshnessStatus = "CURRENT" | "WAITING" | "FAILED";

export interface DailyRunFailure {
  ticker: string;
  /** Absent on older run records recorded before this field existed. */
  status?: TickerFreshnessStatus;
  error: string | null;
}

/** Live config snapshot -- always reflects the CURRENT DAILY_TRACKING_TICKERS
 * value, independent of whichever run the rest of the status describes. */
export interface DailyTrackingConfig {
  tracked_tickers: string[];
  tracked_ticker_count: number;
  predictions_per_market_day: number;
}

export interface DailyRunStatus extends DailyTrackingConfig {
  id: number;
  started_at: string | null;
  finished_at: string | null;
  latest_market_date: string | null;
  /** The NYSE trading session this run expected tracked tickers' data to
   * already reflect -- compare against latest_market_date to see staleness. */
  expected_market_session: string | null;
  tickers_processed: number;
  tickers_current: number;
  tickers_waiting: number;
  /** Permanent-ish failures only -- excludes tickers merely waiting on
   * fresh data or hit by a retryable provider error. */
  tickers_failed: number;
  predictions_attempted: number;
  predictions_saved: number;
  duplicates_skipped: number;
  predictions_failed_or_waiting: number;
  outcomes_resolved: number;
  duration_seconds: number | null;
  status: DailyRunStatusValue;
  failures: DailyRunFailure[];
}

export interface NeverRunStatus extends DailyTrackingConfig {
  status: "NEVER_RUN";
}

export type ModelReviewStatusValue = "NOT_TRAINED" | "COLLECTING_DATA" | "READY_FOR_MODEL_REVIEW";

export interface ModelReviewStatus {
  horizon: Horizon;
  model_version?: string;
  resolved_new_live_predictions: number;
  threshold: number;
  status: ModelReviewStatusValue;
}

// ---------------------------------------------------------------------------
// CURRENT PRICE: fresh/latest quotes -- separate from a completed daily
// PriceBar and from a prediction's frozen start price.
// ---------------------------------------------------------------------------

export type MarketStatus = "OPEN" | "CLOSED" | "UNKNOWN";
export type QuoteSource = "LIVE_QUOTE" | "CACHED_QUOTE" | "PERSISTED_QUOTE" | "LAST_STORED_PRICE" | "UNAVAILABLE";

export interface QuoteResult {
  ticker: string;
  price: number | null;
  /** The PROVIDER's own reported time for this price. */
  quote_timestamp: string | null;
  market_status: MarketStatus;
  is_stale: boolean;
  provider: string | null;
  source: QuoteSource;
  /** When WE last confirmed this value with the provider -- what survives a
   * page reload or backend restart. Null for LAST_STORED_PRICE/UNAVAILABLE. */
  saved_at: string | null;
}
