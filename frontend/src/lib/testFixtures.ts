import type { HorizonPrediction, MultiHorizonPrediction, Position, PredictionHistoryRecord, StockAnalysis, StockLivePerformance } from "./types";

export function makeHorizonPrediction(overrides: Partial<HorizonPrediction> = {}): HorizonPrediction {
  return {
    ticker: "NVDA",
    as_of: "2026-09-11",
    horizon: "5d",
    current_price: 218.29,
    classification: {
      direction: "UP",
      raw_probability: 0.8,
      calibrated_probability: 0.68,
      calibrated_up_probability: 0.68,
      calibrated_down_probability: 0.1,
      signal_status: "BULLISH",
      confidence: "MEDIUM",
      gating_reason: "VALIDATED_BULLISH",
      historical_signal_accuracy: 0.61,
      historical_signal_samples: 143,
      historical_signal_precision: 0.61,
      bullish_threshold: 0.55,
      bearish_threshold: null,
      ...overrides.classification,
    },
    regression: {
      predicted_return: 0.036,
      model_target_price: 225.0,
      uncertainty_low: 205.0,
      uncertainty_high: 245.0,
      p50_abs_error: 0.03,
      ...overrides.regression,
    },
    setup: {
      quality: "STRONG",
      buyer_pressure: "STRONG",
      seller_pressure: "MODERATE",
      support: 207.25,
      resistance: 234.76,
      ...overrides.setup,
    },
    model: {
      classification_version: "random_forest_5d_seed42",
      regression_version: "random_forest_raw_5d",
      calibration_method: "sigmoid",
      is_primary_research_horizon: true,
      ...overrides.model,
    },
    ...overrides,
  };
}

export function makeMultiHorizonPrediction(overrides: Partial<MultiHorizonPrediction> = {}): MultiHorizonPrediction {
  return {
    ticker: "NVDA",
    as_of: "2026-09-11",
    current_price: 218.29,
    primary_research_horizon: "5d",
    predictions: {
      "5d": makeHorizonPrediction(),
      "10d": makeHorizonPrediction({ horizon: "10d", model: { classification_version: "x", regression_version: "y", calibration_method: "sigmoid", is_primary_research_horizon: false } }),
      "15d": makeHorizonPrediction({ horizon: "15d", model: { classification_version: "x", regression_version: "y", calibration_method: "sigmoid", is_primary_research_horizon: false } }),
    },
    market_context: {
      spy_trend: "NEUTRAL",
      qqq_trend: "NEUTRAL",
      sector_trend: "NEUTRAL",
      sector_asset: "SMH",
      stock_vs_market: "NEUTRAL",
      stock_vs_sector: "NEUTRAL",
    },
    generated_at: "2026-09-15T00:00:00Z",
    ...overrides,
  };
}

export function makeStockAnalysis(overrides: Partial<StockAnalysis> = {}): StockAnalysis {
  return {
    ...makeMultiHorizonPrediction(),
    structure: {
      ticker: "NVDA",
      date: "2026-09-11",
      current_price: 218.29,
      market_structure: "BULLISH",
      buyer_pressure: "STRONG",
      seller_pressure: "MODERATE",
      nearest_support: 207.25,
      nearest_resistance: 234.76,
      distance_to_support: 0.05,
      distance_to_resistance: 0.07,
      support_strength: "STRONG",
      resistance_strength: "MODERATE",
      breakout_status: "RANGE_BOUND",
      important_observations: ["Price/volume behavior suggests buyers recently defended the support area."],
    },
    explanation: { positives: ["Price is above its 20-day average"], risks: ["Resistance is nearby"] },
    ...overrides,
  };
}

export function makePredictionHistoryRecord(overrides: Partial<PredictionHistoryRecord> = {}): PredictionHistoryRecord {
  return {
    id: 1,
    ticker: "NVDA",
    horizon: "5d",
    prediction_date: "2026-09-11",
    generated_at: "2026-09-11T16:00:00Z",
    model_version: "random_forest_5d_seed42__random_forest_raw_5d__sigmoid",
    prediction_source: "LIVE_DAILY",
    current_price: 218.29,
    predicted_class: "UP",
    raw_probability: 0.8,
    calibrated_probability: 0.68,
    signal_status: "BULLISH",
    confidence: "MEDIUM",
    predicted_return: 0.036,
    model_target_price: 225.0,
    uncertainty_low: 205.0,
    uncertainty_high: 245.0,
    classification_version: "random_forest_5d_seed42",
    regression_version: "random_forest_raw_5d",
    calibration_method: "sigmoid",
    outcome_status: "PENDING",
    actual_future_price: null,
    final_day_date: null,
    actual_return: null,
    signed_price_error: null,
    absolute_price_error: null,
    absolute_percentage_error: null,
    signed_price_difference: null,
    signed_prediction_difference_pct: null,
    absolute_prediction_difference_pct: null,
    regression_direction_match: null,
    signal_outcome: null,
    outcome_evaluated_at: null,
    ...overrides,
  };
}

export function makeStockLivePerformance(overrides: Partial<StockLivePerformance> = {}): StockLivePerformance {
  return {
    ticker: "NVDA",
    horizons: {
      "5d": { resolved_count: 0, within_2pct: null, within_5pct: null, within_10pct: null, more_than_10pct_off: null, direction_correct_rate: null, average_miss_pct: null },
      "10d": { resolved_count: 0, within_2pct: null, within_5pct: null, within_10pct: null, more_than_10pct_off: null, direction_correct_rate: null, average_miss_pct: null },
      "15d": { resolved_count: 0, within_2pct: null, within_5pct: null, within_10pct: null, more_than_10pct_off: null, direction_correct_rate: null, average_miss_pct: null },
    },
    ...overrides,
  };
}

export function makePosition(overrides: Partial<Position> = {}): Position {
  return {
    id: 1,
    ticker: "NVDA",
    shares: 20,
    purchase_price: 190,
    purchase_date: "2026-01-05",
    my_target_price: 240,
    stop_loss_price: 180,
    notes: null,
    created_at: "2026-01-05T00:00:00Z",
    updated_at: "2026-01-05T00:00:00Z",
    ...overrides,
  };
}
