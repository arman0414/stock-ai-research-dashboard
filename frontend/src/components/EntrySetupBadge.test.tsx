import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import EntrySetupBadge from "./EntrySetupBadge";

describe("EntrySetupBadge", () => {
  it("renders GOOD SETUP", () => {
    render(<EntrySetupBadge state="GOOD_SETUP" />);
    expect(screen.getByText("GOOD SETUP")).toBeInTheDocument();
  });

  it("renders WATCH", () => {
    render(<EntrySetupBadge state="WATCH" />);
    expect(screen.getByText("WATCH")).toBeInTheDocument();
  });

  it("renders WAIT", () => {
    render(<EntrySetupBadge state="WAIT" />);
    expect(screen.getByText("WAIT")).toBeInTheDocument();
  });

  it("never renders BUY or SELL for any state", () => {
    const states = ["GOOD_SETUP", "WATCH", "WAIT", "INSUFFICIENT_DATA"] as const;
    for (const state of states) {
      const { container, unmount } = render(<EntrySetupBadge state={state} />);
      expect(container.textContent).not.toMatch(/\bBUY\b|\bSELL\b/);
      unmount();
    }
  });
});
