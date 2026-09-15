import { describe, expect, it } from "vitest";
import {
  buildResearchChecklist,
  getResearchStrength,
  overallSetupState,
  researchStrengthFromCalibratedProbability,
} from "./researchStrength";
import { makeHorizonPrediction } from "./testFixtures";
import type { MarketContext, SentimentSummary } from "./types";

const NEUTRAL_CONTEXT: MarketContext = {
  spy_trend: "NEUTRAL",
  qqq_trend: "NEUTRAL",
  sector_trend: "NEUTRAL",
  sector_asset: "SMH",
  stock_vs_market: "NEUTRAL",
  stock_vs_sector: "NEUTRAL",
};

describe("researchStrengthFromCalibratedProbability", () => {
  it("maps the exact boundaries from the spec", () => {
    expect(researchStrengthFromCalibratedProbability(0.59)).toBe("NO_STRONG_SIGNAL");
    expect(researchStrengthFromCalibratedProbability(0.60)).toBe("WEAK_SIGNAL");
    expect(researchStrengthFromCalibratedProbability(0.649)).toBe("WEAK_SIGNAL");
    expect(researchStrengthFromCalibratedProbability(0.65)).toBe("WORTH_WATCHING");
    expect(researchStrengthFromCalibratedProbability(0.699)).toBe("WORTH_WATCHING");
    expect(researchStrengthFromCalibratedProbability(0.70)).toBe("STRONG_RESEARCH_SIGNAL");
    expect(researchStrengthFromCalibratedProbability(0.95)).toBe("STRONG_RESEARCH_SIGNAL");
  });
});

describe("getResearchStrength", () => {
  it("uses calibrated probability, never raw probability", () => {
    const prediction = makeHorizonPrediction({
      classification: {
        direction: "UP",
        raw_probability: 0.95, // would be STRONG if (incorrectly) used
        calibrated_probability: 0.61, // should land as WEAK_SIGNAL
        calibrated_up_probability: 0.61,
        calibrated_down_probability: 0.1,
        signal_status: "BULLISH",
        confidence: "MEDIUM",
        gating_reason: "VALIDATED_BULLISH",
        historical_signal_accuracy: 0.55,
        historical_signal_samples: 60,
        historical_signal_precision: 0.55,
        bullish_threshold: 0.55,
        bearish_threshold: null,
      },
    });
    expect(getResearchStrength(prediction)).toBe("WEAK_SIGNAL");
  });

  it("the backend's NO_STRONG_SIGNAL overrides a high calibrated probability -- the core rule of this feature", () => {
    const prediction = makeHorizonPrediction({
      classification: {
        direction: "UP",
        raw_probability: 0.9,
        calibrated_probability: 0.72, // would be STRONG_RESEARCH_SIGNAL by percentage alone
        calibrated_up_probability: 0.72,
        calibrated_down_probability: 0.1,
        signal_status: "NO_STRONG_SIGNAL", // e.g. insufficient evidence
        confidence: "NO_STRONG_SIGNAL",
        gating_reason: "BULLISH_THRESHOLD_NOT_VALIDATED",
        historical_signal_accuracy: null,
        historical_signal_samples: null,
        historical_signal_precision: null,
        bullish_threshold: null,
        bearish_threshold: null,
      },
    });
    expect(getResearchStrength(prediction)).toBe("NO_STRONG_SIGNAL");
  });

  it("returns STRONG_RESEARCH_SIGNAL for a validated bullish call with high calibrated probability", () => {
    const prediction = makeHorizonPrediction(); // fixture: BULLISH, calibrated_probability 0.68
    expect(getResearchStrength({ ...prediction, classification: { ...prediction.classification, calibrated_probability: 0.75 } })).toBe(
      "STRONG_RESEARCH_SIGNAL"
    );
  });
});

describe("buildResearchChecklist", () => {
  it("flags insufficient historical evidence as a warning", () => {
    const prediction = makeHorizonPrediction({
      classification: {
        direction: "UP",
        raw_probability: 0.8,
        calibrated_probability: 0.75,
        calibrated_up_probability: 0.75,
        calibrated_down_probability: 0.1,
        signal_status: "BULLISH",
        confidence: "HIGH",
        gating_reason: "VALIDATED_BULLISH",
        historical_signal_accuracy: null,
        historical_signal_samples: null,
        historical_signal_precision: null,
        bullish_threshold: 0.55,
        bearish_threshold: null,
      },
    });
    const checklist = buildResearchChecklist(prediction, NEUTRAL_CONTEXT, null);
    const evidenceItem = checklist.find((item) => item.label === "Enough historical evidence");
    expect(evidenceItem?.status).toBe("WARNING");
  });

  it("flags nearby resistance as a warning", () => {
    const prediction = makeHorizonPrediction({ current_price: 100, setup: { quality: "STRONG", buyer_pressure: "STRONG", seller_pressure: "WEAK", support: 90, resistance: 101 } });
    const checklist = buildResearchChecklist(prediction, NEUTRAL_CONTEXT, null);
    const resistanceItem = checklist.find((item) => item.label === "Resistance nearby");
    expect(resistanceItem?.status).toBe("WARNING");
  });

  it("does not flag resistance far away", () => {
    const prediction = makeHorizonPrediction({ current_price: 100, setup: { quality: "STRONG", buyer_pressure: "STRONG", seller_pressure: "WEAK", support: 90, resistance: 140 } });
    const checklist = buildResearchChecklist(prediction, NEUTRAL_CONTEXT, null);
    const resistanceItem = checklist.find((item) => item.label === "Resistance nearby");
    expect(resistanceItem?.status).toBe("NEUTRAL");
  });

  it("reads news sentiment from the sentiment summary", () => {
    const prediction = makeHorizonPrediction();
    const positiveSentiment: SentimentSummary = { ticker: "NVDA", articles_7d: 5, positive: 4, neutral: 1, negative: 0, average_sentiment: 0.3, sentiment_direction: "POSITIVE", last_updated: null };
    const checklist = buildResearchChecklist(prediction, NEUTRAL_CONTEXT, positiveSentiment);
    expect(checklist.find((item) => item.label === "News sentiment positive")?.status).toBe("GOOD");
  });
});

describe("overallSetupState", () => {
  it("forces NO_STRONG_SIGNAL when strength is NO_STRONG_SIGNAL, regardless of checklist", () => {
    const checklist = buildResearchChecklist(makeHorizonPrediction(), NEUTRAL_CONTEXT, null);
    expect(overallSetupState("NO_STRONG_SIGNAL", checklist)).toBe("NO_STRONG_SIGNAL");
  });

  it("is STRONG_RESEARCH_SETUP only when strength is strong AND there are zero warnings", () => {
    const cleanChecklist = [
      { label: "a", status: "GOOD" as const },
      { label: "b", status: "GOOD" as const },
    ];
    expect(overallSetupState("STRONG_RESEARCH_SIGNAL", cleanChecklist)).toBe("STRONG_RESEARCH_SETUP");

    const oneWarning = [{ label: "a", status: "WARNING" as const }, { label: "b", status: "GOOD" as const }];
    expect(overallSetupState("STRONG_RESEARCH_SIGNAL", oneWarning)).toBe("WORTH_WATCHING");
  });

  it("is MIXED_SETUP when there are two or more warnings even with a validated signal", () => {
    const twoWarnings = [
      { label: "a", status: "WARNING" as const },
      { label: "b", status: "WARNING" as const },
      { label: "c", status: "GOOD" as const },
    ];
    expect(overallSetupState("WEAK_SIGNAL", twoWarnings)).toBe("MIXED_SETUP");
  });

  it("never returns a BUY/SELL/GUARANTEED style label", () => {
    const allStates: Array<ReturnType<typeof overallSetupState>> = [
      overallSetupState("NO_STRONG_SIGNAL", []),
      overallSetupState("WEAK_SIGNAL", []),
      overallSetupState("WORTH_WATCHING", []),
      overallSetupState("STRONG_RESEARCH_SIGNAL", []),
    ];
    for (const state of allStates) {
      expect(state).not.toMatch(/BUY|SELL|GUARANTEE/i);
    }
  });
});
