import { describe, expect, it } from "vitest";
import { directionArrow, directionArrowFromReturn, priceDirectionFromReturn } from "./priceDirection";

describe("priceDirectionFromReturn", () => {
  it("is HIGHER for a positive predicted return", () => {
    expect(priceDirectionFromReturn(0.02)).toBe("HIGHER");
  });

  it("is LOWER for a negative predicted return", () => {
    expect(priceDirectionFromReturn(-0.02)).toBe("LOWER");
  });

  it("is SIMILAR for a near-zero predicted return", () => {
    expect(priceDirectionFromReturn(0.0001)).toBe("SIMILAR");
    expect(priceDirectionFromReturn(0)).toBe("SIMILAR");
  });
});

describe("directionArrow / directionArrowFromReturn", () => {
  it("maps each direction to its arrow glyph", () => {
    expect(directionArrow("HIGHER")).toBe("↑");
    expect(directionArrow("LOWER")).toBe("↓");
    expect(directionArrow("SIMILAR")).toBe("≈");
  });

  it("derives the arrow directly from a predicted return", () => {
    expect(directionArrowFromReturn(0.05)).toBe("↑");
    expect(directionArrowFromReturn(-0.05)).toBe("↓");
  });
});
