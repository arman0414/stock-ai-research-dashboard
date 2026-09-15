/**
 * Direction arrow derived PURELY from the regression price forecast
 * (predicted_return). This is a distinct concept from the classification's
 * Validated Signal -- a stock can show "Predicted Price $220.27 ↑" while its
 * Validated Signal is still NO_STRONG_SIGNAL. Never derive this from
 * calibrated_probability or signal_status.
 */
export type PriceDirection = "HIGHER" | "LOWER" | "SIMILAR";

// A predicted move smaller than this is treated as "about the same" rather
// than flashing an arrow for statistical noise around zero.
const SIMILAR_THRESHOLD = 0.001;

export function priceDirectionFromReturn(predictedReturn: number): PriceDirection {
  if (predictedReturn > SIMILAR_THRESHOLD) return "HIGHER";
  if (predictedReturn < -SIMILAR_THRESHOLD) return "LOWER";
  return "SIMILAR";
}

export function directionArrow(direction: PriceDirection): string {
  if (direction === "HIGHER") return "↑";
  if (direction === "LOWER") return "↓";
  return "≈";
}

export function directionArrowFromReturn(predictedReturn: number): string {
  return directionArrow(priceDirectionFromReturn(predictedReturn));
}
