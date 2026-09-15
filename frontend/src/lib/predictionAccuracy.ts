/**
 * Frontend-only interpretation labels. These never feed back into the
 * model, training, or validation -- they exist purely to make resolved
 * live-forecast results and live-performance sample sizes easy to read.
 */

export type AccuracyLabel = "WITHIN_2PCT" | "WITHIN_5PCT" | "WITHIN_10PCT" | "MORE_THAN_10PCT_OFF";

export const ACCURACY_LABEL_TEXT: Record<AccuracyLabel, string> = {
  WITHIN_2PCT: "WITHIN ±2%",
  WITHIN_5PCT: "WITHIN ±5%",
  WITHIN_10PCT: "WITHIN ±10%",
  MORE_THAN_10PCT_OFF: "MORE THAN 10% OFF",
};

export const ACCURACY_LABEL_STYLES: Record<AccuracyLabel, string> = {
  WITHIN_2PCT: "bg-green-100 text-green-800 border-green-200",
  WITHIN_5PCT: "bg-blue-50 text-blue-700 border-blue-200",
  WITHIN_10PCT: "bg-amber-50 text-amber-700 border-amber-200",
  MORE_THAN_10PCT_OFF: "bg-red-50 text-red-700 border-red-200",
};

/**
 * `absolutePredictionDifferencePct` is a percentage NUMBER (1.50 means
 * 1.50%), matching `absolute_prediction_difference_pct` from the API --
 * NOT a fraction like the old (removed) absolute_percentage_error convention.
 */
export function accuracyLabelFromDifference(absolutePredictionDifferencePct: number): AccuracyLabel {
  if (absolutePredictionDifferencePct <= 2) return "WITHIN_2PCT";
  if (absolutePredictionDifferencePct <= 5) return "WITHIN_5PCT";
  if (absolutePredictionDifferencePct <= 10) return "WITHIN_10PCT";
  return "MORE_THAN_10PCT_OFF";
}

export type SampleSizeLabel = "EARLY_RESULTS" | "LIMITED_LIVE_EVIDENCE" | "MEANINGFUL_LIVE_SAMPLE";

export const SAMPLE_SIZE_TEXT: Record<SampleSizeLabel, string> = {
  EARLY_RESULTS: "EARLY RESULTS",
  LIMITED_LIVE_EVIDENCE: "LIMITED LIVE EVIDENCE",
  MEANINGFUL_LIVE_SAMPLE: "MEANINGFUL LIVE SAMPLE",
};

export const SAMPLE_SIZE_DESCRIPTION: Record<SampleSizeLabel, string> = {
  EARLY_RESULTS: "Not enough live predictions yet to judge model reliability.",
  LIMITED_LIVE_EVIDENCE: "Live results are accumulating, but the sample is still limited.",
  MEANINGFUL_LIVE_SAMPLE: "Enough resolved predictions exist to meaningfully gauge live performance.",
};

export function sampleSizeLabel(resolvedCount: number): SampleSizeLabel {
  if (resolvedCount < 30) return "EARLY_RESULTS";
  if (resolvedCount < 100) return "LIMITED_LIVE_EVIDENCE";
  return "MEANINGFUL_LIVE_SAMPLE";
}
