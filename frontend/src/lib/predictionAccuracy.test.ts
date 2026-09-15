import { describe, expect, it } from "vitest";
import { accuracyLabelFromDifference, sampleSizeLabel } from "./predictionAccuracy";

describe("accuracyLabelFromDifference", () => {
  it("is WITHIN_2PCT at or below 2%", () => {
    expect(accuracyLabelFromDifference(1.5)).toBe("WITHIN_2PCT");
    expect(accuracyLabelFromDifference(2)).toBe("WITHIN_2PCT");
  });

  it("is WITHIN_5PCT between 2% and 5%", () => {
    expect(accuracyLabelFromDifference(3)).toBe("WITHIN_5PCT");
    expect(accuracyLabelFromDifference(5)).toBe("WITHIN_5PCT");
  });

  it("is WITHIN_10PCT between 5% and 10%", () => {
    expect(accuracyLabelFromDifference(7)).toBe("WITHIN_10PCT");
    expect(accuracyLabelFromDifference(10)).toBe("WITHIN_10PCT");
  });

  it("is MORE_THAN_10PCT_OFF above 10%", () => {
    expect(accuracyLabelFromDifference(15)).toBe("MORE_THAN_10PCT_OFF");
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
