import type { HorizonPrediction, MarketContext, SentimentSummary } from "./types";

/**
 * Research Strength / Decision Guide.
 *
 * This is a frontend INTERPRETATION AID only -- it never decides whether a
 * signal fires. The backend's `signal_status` (BULLISH / BEARISH /
 * NO_STRONG_SIGNAL) is always authoritative: if the backend says
 * NO_STRONG_SIGNAL, that overrides the percentage-based guide below even
 * when the calibrated probability number looks high on its own. This
 * protects against insufficient evidence, unvalidated bearish signals,
 * setup-quality vetoes, and weaker horizons all being displayed as if they
 * were a confident call.
 */

export type ResearchStrengthLevel = "NO_STRONG_SIGNAL" | "WEAK_SIGNAL" | "WORTH_WATCHING" | "STRONG_RESEARCH_SIGNAL";

export const RESEARCH_STRENGTH_LABELS: Record<ResearchStrengthLevel, string> = {
  NO_STRONG_SIGNAL: "NO STRONG SIGNAL",
  WEAK_SIGNAL: "WEAK SIGNAL",
  WORTH_WATCHING: "WORTH WATCHING",
  STRONG_RESEARCH_SIGNAL: "STRONG RESEARCH SIGNAL",
};

export const RESEARCH_STRENGTH_STYLES: Record<ResearchStrengthLevel, string> = {
  NO_STRONG_SIGNAL: "bg-gray-100 text-gray-600 border-gray-200",
  WEAK_SIGNAL: "bg-amber-50 text-amber-700 border-amber-200",
  WORTH_WATCHING: "bg-blue-50 text-blue-700 border-blue-200",
  STRONG_RESEARCH_SIGNAL: "bg-green-100 text-green-800 border-green-200",
};

/** Calibrated-probability-only tiering. Never pass raw_probability here. */
export function researchStrengthFromCalibratedProbability(calibratedProbability: number): ResearchStrengthLevel {
  if (calibratedProbability >= 0.70) return "STRONG_RESEARCH_SIGNAL";
  if (calibratedProbability >= 0.65) return "WORTH_WATCHING";
  if (calibratedProbability >= 0.60) return "WEAK_SIGNAL";
  return "NO_STRONG_SIGNAL";
}

export function getResearchStrength(prediction: HorizonPrediction): ResearchStrengthLevel {
  // Backend gate wins, full stop -- see module docstring above.
  if (prediction.classification.signal_status === "NO_STRONG_SIGNAL") {
    return "NO_STRONG_SIGNAL";
  }
  return researchStrengthFromCalibratedProbability(prediction.classification.calibrated_probability);
}

// ---------------------------------------------------------------------------
// Research checklist + overall setup synthesis (Stock Detail page)
// ---------------------------------------------------------------------------

export type ChecklistStatus = "GOOD" | "WARNING" | "NEUTRAL";

export interface ChecklistItem {
  label: string;
  status: ChecklistStatus;
}

const RESISTANCE_NEARBY_THRESHOLD = 0.03; // matches backend's own APPROACHING_RESISTANCE convention
const MIN_HISTORICAL_EVIDENCE_SAMPLES = 50; // matches champion.py's DEFAULT_MIN_EVIDENCE

export function buildResearchChecklist(
  prediction: HorizonPrediction,
  marketContext: MarketContext,
  sentiment: SentimentSummary | null
): ChecklistItem[] {
  const { classification, setup, current_price: currentPrice } = prediction;

  const probabilityGood = classification.calibrated_probability >= 0.70;

  const buyerStatus: ChecklistStatus = setup.buyer_pressure === "STRONG" || setup.buyer_pressure === "MODERATE" ? "GOOD" : setup.buyer_pressure === "WEAK" ? "WARNING" : "NEUTRAL";

  const marketSupportive = marketContext.stock_vs_market === "OUTPERFORMING" || marketContext.stock_vs_sector === "OUTPERFORMING";
  const marketUnsupportive = marketContext.stock_vs_market === "UNDERPERFORMING" && marketContext.stock_vs_sector === "UNDERPERFORMING";
  const marketStatus: ChecklistStatus = marketSupportive ? "GOOD" : marketUnsupportive ? "WARNING" : "NEUTRAL";

  const hasEnoughEvidence = classification.historical_signal_samples !== null && classification.historical_signal_samples >= MIN_HISTORICAL_EVIDENCE_SAMPLES;
  const evidenceStatus: ChecklistStatus = classification.historical_signal_samples === null ? "WARNING" : hasEnoughEvidence ? "GOOD" : "NEUTRAL";

  const resistanceNearby = setup.resistance !== null && currentPrice > 0 && (setup.resistance - currentPrice) / currentPrice >= 0 && (setup.resistance - currentPrice) / currentPrice < RESISTANCE_NEARBY_THRESHOLD;
  const resistanceStatus: ChecklistStatus = resistanceNearby ? "WARNING" : "GOOD";

  const newsStatus: ChecklistStatus = !sentiment ? "NEUTRAL" : sentiment.sentiment_direction === "POSITIVE" ? "GOOD" : sentiment.sentiment_direction === "NEGATIVE" ? "WARNING" : "NEUTRAL";

  return [
    { label: "Calibrated probability above 70%", status: probabilityGood ? "GOOD" : "NEUTRAL" },
    { label: "Buyer pressure supportive", status: buyerStatus },
    { label: "Market/sector supportive", status: marketStatus },
    { label: "Enough historical evidence", status: evidenceStatus },
    { label: "Resistance nearby", status: resistanceStatus === "WARNING" ? "WARNING" : "NEUTRAL" },
    { label: "News sentiment positive", status: newsStatus },
  ];
}

export type OverallSetupState = "STRONG_RESEARCH_SETUP" | "WORTH_WATCHING" | "MIXED_SETUP" | "NO_STRONG_SIGNAL";

export const OVERALL_SETUP_LABELS: Record<OverallSetupState, string> = {
  STRONG_RESEARCH_SETUP: "STRONG RESEARCH SETUP",
  WORTH_WATCHING: "WORTH WATCHING",
  MIXED_SETUP: "MIXED SETUP",
  NO_STRONG_SIGNAL: "NO STRONG SIGNAL",
};

export function overallSetupState(strength: ResearchStrengthLevel, checklist: ChecklistItem[]): OverallSetupState {
  // Authoritative override, same rule as getResearchStrength.
  if (strength === "NO_STRONG_SIGNAL") return "NO_STRONG_SIGNAL";

  const warningCount = checklist.filter((item) => item.status === "WARNING").length;

  if (strength === "STRONG_RESEARCH_SIGNAL" && warningCount === 0) return "STRONG_RESEARCH_SETUP";
  if (warningCount >= 2) return "MIXED_SETUP";
  return "WORTH_WATCHING";
}
