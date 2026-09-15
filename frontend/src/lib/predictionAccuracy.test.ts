import { describe, expect, it } from "vitest";
import { accuracyLabelFromError, sampleSizeLabel } from "./predictionAccuracy";

describe("accuracyLabelFromError", () => {
  it("is VERY_CLOSE at or below 3%", () => {
    expect(accuracyLabelFromError(0.0171)).toBe("VERY_CLOSE");
    expect(accuracyLabelFromError(0.03)).toBe("VERY_CLOSE");
  });

  it("is CLOSE between 3% and 5%", () => {
    expect(accuracyLabelFromError(0.04)).toBe("CLOSE");
    expect(accuracyLabelFromError(0.05)).toBe("CLOSE");
  });

  it("is MODERATE_ERROR between 5% and 10%", () => {
    expect(accuracyLabelFromError(0.07)).toBe("MODERATE_ERROR");
    expect(accuracyLabelFromError(0.10)).toBe("MODERATE_ERROR");
  });

  it("is LARGE_ERROR above 10%", () => {
    expect(accuracyLabelFromError(0.15)).toBe("LARGE_ERROR");
  });
});

describe("sampleSizeLabel", () => {
  it("is EARLY_RESULTS below 30", () => {
    expect(sampleSizeLabel(0)).toBe("EARLY_RESULTS");
    expect(sampleSizeLabel(8)).toBe("EARLY_RESULTS");
    expect(sampleSizeLabel(29)).toBe("EARLY_RESULTS");
  });

  it("is LIMITED_LIVE_EVIDENCE between 30 and 99", () => {
    expect(sampleSizeLabel(30)).toBe("LIMITED_LIVE_EVIDENCE");
    expect(sampleSizeLabel(99)).toBe("LIMITED_LIVE_EVIDENCE");
  });

  it("is MEANINGFUL_LIVE_SAMPLE at 100+", () => {
    expect(sampleSizeLabel(100)).toBe("MEANINGFUL_LIVE_SAMPLE");
    expect(sampleSizeLabel(127)).toBe("MEANINGFUL_LIVE_SAMPLE");
  });
});
