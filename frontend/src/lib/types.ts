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
  external_id: string;
  event_category: string | null;
  sentiment: NewsArticleSentiment | null;
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
}

export interface Position {
  id: number;
  ticker: string;
  shares: number;
  purchase_price: number;
  purchase_date: string;
  my_target_price: number | null;
  stop_loss_price: number | null;
  notes: string | null;
  created_at: string | null;
  updated_at: string | null;
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
