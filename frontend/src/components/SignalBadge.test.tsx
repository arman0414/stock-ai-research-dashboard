import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import SignalBadge from "./SignalBadge";

describe("SignalBadge", () => {
  it("renders NO_STRONG_SIGNAL as a normal, non-error looking badge", () => {
    render(<SignalBadge status="NO_STRONG_SIGNAL" />);
    const badge = screen.getByTestId("signal-badge");
    expect(badge).toHaveTextContent("No Strong Signal");
    expect(badge.className).toContain("bg-gray-100");
    expect(badge.className).not.toContain("bg-red");
  });

  it("renders BULLISH in green", () => {
    render(<SignalBadge status="BULLISH" />);
    const badge = screen.getByTestId("signal-badge");
    expect(badge).toHaveTextContent("Bullish");
    expect(badge.className).toContain("bg-green-100");
  });

  it("renders BEARISH in red only when explicitly given that status", () => {
    render(<SignalBadge status="BEARISH" />);
    const badge = screen.getByTestId("signal-badge");
    expect(badge).toHaveTextContent("Bearish");
    expect(badge.className).toContain("bg-red-100");
  });
});
