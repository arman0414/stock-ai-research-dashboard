import { formatPercent, horizonTradingDaysLabel } from "./format";
import type { HorizonPrediction } from "./types";

/**
 * Turns the backend's `gating_reason` into a plain-English sentence.
 *
 * This never invents a reason: every branch below corresponds exactly to a
 * gating_reason string produced by stock_ai/ml/signal_gate.py's decide_signal().
 * Numbers used (probability, threshold) come straight from the API response.
 * Unrecognized reasons fall back to a generic, still-truthful sentence rather
 * than guessing specifics.
 */
export function explainNoStrongSignal(prediction: HorizonPrediction): string | null {
  const { classification, horizon } = prediction;
  if (classification.signal_status !== "NO_STRONG_SIGNAL") return null;

  const horizonWords = horizonTradingDaysLabel(horizon);
  const probabilityPct = formatPercent(classification.calibrated_probability, 0);

  switch (classification.gating_reason) {
    case "PREDICTED_NEUTRAL":
      return "The model does not currently see a meaningful directional move.";

    case "BELOW_BULLISH_THRESHOLD": {
      const thresholdPct = classification.bullish_threshold !== null ? formatPercent(classification.bullish_threshold, 0) : null;
      return thresholdPct
        ? `Model leans UP, but confidence is ${probabilityPct}. ${horizonWords} bullish signals currently require at least ${thresholdPct} calibrated probability.`
        : `Model leans UP, but confidence is ${probabilityPct}, which is below the validated threshold for this horizon.`;
    }

    case "BELOW_BEARISH_THRESHOLD": {
      const thresholdPct = classification.bearish_threshold !== null ? formatPercent(classification.bearish_threshold, 0) : null;
      return thresholdPct
        ? `Model leans DOWN, but confidence is ${probabilityPct}. ${horizonWords} bearish signals currently require at least ${thresholdPct} calibrated probability.`
        : `Model leans DOWN, but confidence is ${probabilityPct}, which is below the validated threshold for this horizon.`;
    }

    case "BULLISH_THRESHOLD_NOT_VALIDATED":
      return "Model leans UP, but bullish signals for this horizon are not currently supported by enough historical evidence.";

    case "BEARISH_THRESHOLD_NOT_VALIDATED":
      return "Model leans DOWN, but bearish signals are not currently supported by enough historical evidence.";

    case "SETUP_QUALITY_TOO_WEAK":
      return "Model confidence passed the probability threshold, but the current technical setup does not meet the validated signal requirements.";

    case "UNSUPPORTED_REGIME":
      return "Current market conditions fall outside the model's validated setup for this horizon.";

    default:
      return "This setup does not currently meet the model's validated signal requirements.";
  }
}
