import type { ClosedPosition, EntrySetupResult, HorizonPrediction, LiveEntrySetup, MultiHorizonPrediction, PortfolioSummary, Position, PositionTransaction, PredictionHistoryRecord, QuoteResult, StockAnalysis, StockLivePerformance } from "./types";

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
    entry_setup_state: null,
    entry_setup_version: null,
    entry_setup_reasons: [],
    ...overrides,
  };
}

export function makeEntrySetupResult(overrides: Partial<EntrySetupResult> = {}): EntrySetupResult {
  return {
    state: "GOOD_SETUP",
    version: "entry-v1",
    reasons: [
      { symbol: "check", text: "Validated bullish model signal" },
      { symbol: "check", text: "Model target is +4.8% vs current price" },
      { symbol: "check", text: "Price is 1.9% above support" },
      { symbol: "check", text: "7.1% room before resistance" },
      { symbol: "check", text: "Buyer pressure is strong" },
    ],
    summary: "Validated bullish signal, meaningful upside, and healthy room to resistance all line up.",
    expected_upside_pct: 4.76,
    support_distance_pct: 1.9,
    resistance_room_pct: 7.14,
    potential_reward: 10,
    potential_risk: 5,
    research_reward_risk: 2.0,
    reward_target_price: 220,
    resistance_below_target: false,
    disclaimer: "Entry Setup is a research aid based on the current model forecast and technical context. Its performance as an entry strategy has not been separately validated and is still being evaluated.",
    ...overrides,
  };
}

export function makeLiveEntrySetup(overrides: Partial<LiveEntrySetup> = {}): LiveEntrySetup {
  return {
    ticker: "NVDA",
    horizon: "5d",
    available: true,
    prediction_date: "2026-09-15",
    prediction_start_price: 210.96,
    predicted_price: 213.0,
    model_expected_move_pct: 0.97,
    signal_status: "BULLISH",
    current_quote: makeQuoteResult(),
    entry_setup: makeEntrySetupResult(),
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

export function makeQuoteResult(overrides: Partial<QuoteResult> = {}): QuoteResult {
  return {
    ticker: "NVDA",
    price: 214.3,
    quote_timestamp: "2026-09-15T18:48:00Z",
    market_status: "OPEN",
    is_stale: false,
    provider: "twelve_data",
    source: "LIVE_QUOTE",
    saved_at: "2026-09-15T18:48:00Z",
    ...overrides,
  };
}

export function makePosition(overrides: Partial<Position> = {}): Position {
  return {
    id: 1,
    ticker: "NVDA",
    shares: 20,
    purchase_price: 190,
    average_cost: 190,
    total_cost_basis: 3800,
    purchase_date: "2026-01-05",
    my_target_price: 240,
    stop_loss_price: 180,
    notes: null,
    realized_pl: 0,
    lifetime_realized_pl: 0,
    cycle_index: 1,
    is_open: true,
    closed_at: null,
    created_at: "2026-01-05T00:00:00Z",
    updated_at: "2026-01-05T00:00:00Z",
    ...overrides,
  };
}

export function makeTransaction(overrides: Partial<PositionTransaction> = {}): PositionTransaction {
  return {
    id: 1,
    ticker: "IREN",
    transaction_type: "BUY",
    quantity: 150,
    price_per_share: 32,
    fees: 0,
    transaction_date: "2026-09-02T00:00:00Z",
    notes: null,
    source: "manual",
    cycle_index: 1,
    cost_basis_per_share: null,
    cost_basis_total: null,
    sale_proceeds: null,
    realized_profit_loss: null,
    realized_profit_loss_pct: null,
    created_at: "2026-09-02T00:00:00Z",
    ...overrides,
  };
}

export function makeClosedPosition(overrides: Partial<ClosedPosition> = {}): ClosedPosition {
  return {
    ticker: "IREN",
    cycle_index: 1,
    total_shares_sold: 150,
    total_cost_basis: 4800,
    total_proceeds: 6750,
    realized_profit_loss: 1950,
    return_pct: 40.625,
    first_buy_date: "2026-09-02T00:00:00Z",
    final_sell_date: "2026-09-18T00:00:00Z",
    ...overrides,
  };
}

export function makePortfolioSummary(overrides: Partial<PortfolioSummary> = {}): PortfolioSummary {
  return {
    portfolio_value: 4500,
    open_cost_basis: 3200,
    unrealized_pl: 1300,
    unrealized_pl_pct: 40.625,
    realized_pl: 650,
    total_pl: 1950,
    open_position_count: 1,
    priced_position_count: 1,
    ...overrides,
  };
}
