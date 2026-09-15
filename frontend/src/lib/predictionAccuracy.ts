/**
 * Frontend-only interpretation labels. These never feed back into the
 * model, training, or validation -- they exist purely to make resolved
 * live-forecast results and live-performance sample sizes easy to read.
 */

export type AccuracyLabel = "VERY_CLOSE" | "CLOSE" | "MODERATE_ERROR" | "LARGE_ERROR";

export const ACCURACY_LABEL_TEXT: Record<AccuracyLabel, string> = {
  VERY_CLOSE: "VERY CLOSE",
  CLOSE: "CLOSE",
  MODERATE_ERROR: "MODERATE ERROR",
  LARGE_ERROR: "LARGE ERROR",
};

export const ACCURACY_LABEL_STYLES: Record<AccuracyLabel, string> = {
  VERY_CLOSE: "bg-green-100 text-green-800 border-green-200",
  CLOSE: "bg-blue-50 text-blue-700 border-blue-200",
  MODERATE_ERROR: "bg-amber-50 text-amber-700 border-amber-200",
  LARGE_ERROR: "bg-red-50 text-red-700 border-red-200",
};

/** `absolutePercentageError` is a fraction (0.017 = 1.71%), matching the API. */
export function accuracyLabelFromError(absolutePercentageError: number): AccuracyLabel {
  if (absolutePercentageError <= 0.03) return "VERY_CLOSE";
  if (absolutePercentageError <= 0.05) return "CLOSE";
  if (absolutePercentageError <= 0.10) return "MODERATE_ERROR";
  return "LARGE_ERROR";
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
