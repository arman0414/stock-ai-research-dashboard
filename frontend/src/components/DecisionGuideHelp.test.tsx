import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import DecisionGuideHelp from "./DecisionGuideHelp";

describe("DecisionGuideHelp", () => {
  it("explains all four probability tiers and the non-trade-decision disclaimer", () => {
    render(<DecisionGuideHelp />);
    expect(screen.getByText("How to read model confidence")).toBeInTheDocument();
    expect(screen.getByText(/No Strong Signal/)).toBeInTheDocument();
    expect(screen.getByText(/Weak — monitor only/)).toBeInTheDocument();
    expect(screen.getByText(/Worth Watching/)).toBeInTheDocument();
    expect(screen.getByText(/Strong Research Signal/)).toBeInTheDocument();
    expect(screen.getByText(/Probability alone should not determine a trade/)).toBeInTheDocument();
  });
});
