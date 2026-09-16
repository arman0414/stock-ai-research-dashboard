import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import EntrySetupChecklist from "./EntrySetupChecklist";
import { makeEntrySetupResult, makeLiveEntrySetup } from "@/lib/testFixtures";

describe("EntrySetupChecklist", () => {
  it("shows the GOOD SETUP badge, reward/risk, and reveals the checklist behind Why?", async () => {
    const user = userEvent.setup();
    render(<EntrySetupChecklist liveEntrySetup={makeLiveEntrySetup()} />);

    expect(screen.getByText("GOOD SETUP")).toBeInTheDocument();
    expect(screen.getByText("2.0x")).toBeInTheDocument();

    const reasonsList = screen.getByTestId("entry-setup-reasons");
    expect(reasonsList).not.toBeVisible(); // collapsed inside <details> until opened

    await user.click(screen.getByText(/Why GOOD SETUP\?/));
    expect(screen.getByText("Validated bullish model signal")).toBeInTheDocument();
    expect(screen.getByText(/research aid/i)).toBeInTheDocument(); // the disclaimer
  });

  it("renders a WATCH state with its own reasons", () => {
    const liveEntrySetup = makeLiveEntrySetup({
      entry_setup: makeEntrySetupResult({
        state: "WATCH",
        reasons: [
          { symbol: "check", text: "Model predicts +4.0% vs current price" },
          { symbol: "warning", text: "Model View: NO_STRONG_SIGNAL" },
        ],
      }),
    });
    render(<EntrySetupChecklist liveEntrySetup={liveEntrySetup} />);
    expect(screen.getByText("WATCH")).toBeInTheDocument();
  });

  it("renders a WAIT state and never upgrades it based on price alone", () => {
    const liveEntrySetup = makeLiveEntrySetup({
      entry_setup: makeEntrySetupResult({
        state: "WAIT",
        research_reward_risk: null,
        reasons: [{ symbol: "cross", text: "No validated bullish model signal" }],
      }),
    });
    render(<EntrySetupChecklist liveEntrySetup={liveEntrySetup} />);
    expect(screen.getByText("WAIT")).toBeInTheDocument();
    expect(screen.queryByText(/x$/)).not.toBeInTheDocument(); // no reward/risk shown when null
  });

  it("shows an unavailable message instead of fabricating a setup when there is no current forecast", () => {
    render(<EntrySetupChecklist liveEntrySetup={{ ticker: "NVDA", horizon: "10d", available: false, reason: "No current 10-day forecast available." }} />);
    expect(screen.getByText("No current 10-day forecast available.")).toBeInTheDocument();
    expect(screen.queryByTestId("entry-setup-badge")).not.toBeInTheDocument();
  });

  it("never displays BUY or SELL language", () => {
    const { container } = render(<EntrySetupChecklist liveEntrySetup={makeLiveEntrySetup()} />);
    expect(container.textContent).not.toMatch(/\bBUY\b|\bSELL\b/);
  });
});
