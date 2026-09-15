import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import SampleSizeNotice from "./SampleSizeNotice";

describe("SampleSizeNotice", () => {
  it("shows EARLY RESULTS with its caution message below 30", () => {
    render(<SampleSizeNotice resolvedCount={8} />);
    expect(screen.getByText("EARLY RESULTS")).toBeInTheDocument();
    expect(screen.getByText(/Not enough live predictions yet to judge model reliability/)).toBeInTheDocument();
  });

  it("shows LIMITED LIVE EVIDENCE between 30 and 99", () => {
    render(<SampleSizeNotice resolvedCount={45} />);
    expect(screen.getByText("LIMITED LIVE EVIDENCE")).toBeInTheDocument();
  });

  it("shows MEANINGFUL LIVE SAMPLE at 100+", () => {
    render(<SampleSizeNotice resolvedCount={127} />);
    expect(screen.getByText("MEANINGFUL LIVE SAMPLE")).toBeInTheDocument();
  });

  it("never claims statistical certainty", () => {
    const { container } = render(<SampleSizeNotice resolvedCount={200} />);
    expect(container.textContent).not.toMatch(/certain|guarantee|proven/i);
  });
});
