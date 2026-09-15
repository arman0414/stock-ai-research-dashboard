import { describe, expect, it } from "vitest";
import { explainNoStrongSignal } from "./signalExplanation";
import { makeHorizonPrediction } from "./testFixtures";

function neutralClassificationOverrides(overrides: Record<string, unknown> = {}) {
  return {
    direction: "UP" as const,
    raw_probability: 0.5,
    calibrated_probability: 0.37,
    calibrated_up_probability: 0.37,
    calibrated_down_probability: 0.1,
    signal_status: "NO_STRONG_SIGNAL" as const,
    confidence: "NO_STRONG_SIGNAL" as const,
    gating_reason: "PREDICTED_NEUTRAL",
    historical_signal_accuracy: null,
    historical_signal_samples: null,
    historical_signal_precision: null,
    bullish_threshold: null,
    bearish_threshold: null,
    ...overrides,
  };
}

describe("explainNoStrongSignal", () => {
  it("returns null when the backend has a validated signal (no explanation needed)", () => {
    const prediction = makeHorizonPrediction(); // fixture default: BULLISH
    expect(explainNoStrongSignal(prediction)).toBeNull();
  });

  it("explains a below-threshold bullish lean with the real probability and real threshold", () => {
    const prediction = makeHorizonPrediction({
      horizon: "5d",
      classification: neutralClassificationOverrides({
        direction: "UP",
        calibrated_probability: 0.37,
        gating_reason: "BELOW_BULLISH_THRESHOLD",
        bullish_threshold: 0.5,
      }),
    });
    const explanation = explainNoStrongSignal(prediction);
    expect(explanation).toContain("Model leans UP");
    expect(explanation).toContain("37%");
    expect(explanation).toContain("5 Trading Days");
    expect(explanation).toContain("50%");
  });

  it("explains a below-threshold bearish lean with the real probability and real threshold", () => {
    const prediction = makeHorizonPrediction({
      classification: neutralClassificationOverrides({
        direction: "DOWN",
        calibrated_probability: 0.42,
        gating_reason: "BELOW_BEARISH_THRESHOLD",
        bearish_threshold: 0.6,
      }),
    });
    const explanation = explainNoStrongSignal(prediction);
    expect(explanation).toContain("Model leans DOWN");
    expect(explanation).toContain("42%");
    expect(explanation).toContain("60%");
  });

  it("explains the bearish-disabled case without inventing a specific number", () => {
    const prediction = makeHorizonPrediction({
      classification: neutralClassificationOverrides({
        direction: "DOWN",
        calibrated_probability: 0.72,
        gating_reason: "BEARISH_THRESHOLD_NOT_VALIDATED",
        bearish_threshold: null,
      }),
    });
    const explanation = explainNoStrongSignal(prediction);
    expect(explanation).toContain("Model leans DOWN");
    expect(explanation).toMatch(/not currently supported by enough historical evidence/);
    // Must not fabricate a percentage threshold that the backend never validated.
    expect(explanation).not.toMatch(/require at least \d/);
  });

  it("explains insufficient evidence for an unvalidated bullish lean", () => {
    const prediction = makeHorizonPrediction({
      classification: neutralClassificationOverrides({
        direction: "UP",
        gating_reason: "BULLISH_THRESHOLD_NOT_VALIDATED",
        bullish_threshold: null,
      }),
    });
    expect(explainNoStrongSignal(prediction)).toMatch(/not currently supported by enough historical evidence/);
  });

  it("explains a neutral prediction plainly", () => {
    const prediction = makeHorizonPrediction({ classification: neutralClassificationOverrides({ gating_reason: "PREDICTED_NEUTRAL" }) });
    expect(explainNoStrongSignal(prediction)).toBe("The model does not currently see a meaningful directional move.");
  });

  it("explains a setup-quality veto using the backend's own gating reason", () => {
    const prediction = makeHorizonPrediction({ classification: neutralClassificationOverrides({ gating_reason: "SETUP_QUALITY_TOO_WEAK" }) });
    expect(explainNoStrongSignal(prediction)).toMatch(/technical setup does not meet the validated signal requirements/);
  });

  it("falls back to a generic but truthful sentence for an unrecognized gating reason", () => {
    const prediction = makeHorizonPrediction({ classification: neutralClassificationOverrides({ gating_reason: "SOME_FUTURE_REASON" }) });
    expect(explainNoStrongSignal(prediction)).toMatch(/does not currently meet the model's validated signal requirements/);
  });
});
