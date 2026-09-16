import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import CurrentPrice from "./CurrentPrice";
import { makeQuoteResult } from "@/lib/testFixtures";

describe("CurrentPrice", () => {
  it("shows the fallback/cached price immediately while the quote is still loading", () => {
    render(<CurrentPrice quote={undefined} fallbackPrice={210.96} />);
    expect(screen.getByText("$210.96")).toBeInTheDocument();
    expect(screen.getByText("Updating…")).toBeInTheDocument();
  });

  it("shows an Updating state with no fallback price, never $0", () => {
    render(<CurrentPrice quote={undefined} fallbackPrice={null} />);
    expect(screen.getByText("Updating…")).toBeInTheDocument();
    expect(screen.queryByText("$0.00")).not.toBeInTheDocument();
  });

  it("shows the fresh quote price and a recency label once it arrives", () => {
    const quote = makeQuoteResult({ price: 214.3, quote_timestamp: new Date().toISOString(), is_stale: false, market_status: "OPEN" });
    render(<CurrentPrice quote={quote} />);
    expect(screen.getByText("$214.30")).toBeInTheDocument();
    expect(screen.getByTestId("current-price-freshness").textContent).toMatch(/Updated/);
  });

  it("shows a Market Closed label instead of implying a moving live quote", () => {
    const quote = makeQuoteResult({ price: 214.3, market_status: "CLOSED" });
    render(<CurrentPrice quote={quote} />);
    expect(screen.getByText(/Market Closed/)).toBeInTheDocument();
  });

  it("shows a stale-price warning, not a blanked price, on provider fallback", () => {
    const quote = makeQuoteResult({ price: 213.9, is_stale: true, source: "LAST_STORED_PRICE" });
    render(<CurrentPrice quote={quote} />);
    expect(screen.getByText("$213.90")).toBeInTheDocument();
    expect(screen.getByText(/Price may be outdated/)).toBeInTheDocument();
  });

  it("never labels the price REAL-TIME", () => {
    const quote = makeQuoteResult({ price: 214.3 });
    const { container } = render(<CurrentPrice quote={quote} />);
    expect(container.textContent).not.toMatch(/real.?time/i);
  });

  it("renders a persisted price immediately, labeled by when it was saved", () => {
    const persisted = makeQuoteResult({ price: 216.02, source: "CACHED_QUOTE", saved_at: "2026-09-15T10:30:00Z", quote_timestamp: "2026-09-15T10:30:00Z" });
    render(<CurrentPrice quote={persisted} />);
    expect(screen.getByText("$216.02")).toBeInTheDocument();
  });

  it("shows an Updating suffix while a background refresh is in flight for a stale/persisted value", () => {
    const staleQuote = makeQuoteResult({ price: 216.02, source: "PERSISTED_QUOTE", is_stale: true, saved_at: "2026-09-15T10:30:00Z" });
    render(<CurrentPrice quote={staleQuote} refreshing />);
    const freshness = screen.getByTestId("current-price-freshness");
    expect(freshness.textContent).toMatch(/Last saved/);
    expect(freshness.textContent).toMatch(/Updating…/);
  });

  it("does not show an Updating suffix once the value is already confirmed fresh this cycle", () => {
    const freshQuote = makeQuoteResult({ price: 217.4, source: "LIVE_QUOTE", is_stale: false });
    render(<CurrentPrice quote={freshQuote} refreshing />);
    expect(screen.getByTestId("current-price-freshness").textContent).not.toMatch(/Updating…/);
  });

  it("replaces a persisted value with the fresh quote once the refresh resolves", () => {
    const persisted = makeQuoteResult({ price: 216.02, source: "PERSISTED_QUOTE", is_stale: true, saved_at: "2026-09-15T10:30:00Z" });
    const { rerender } = render(<CurrentPrice quote={persisted} refreshing />);
    expect(screen.getByText("$216.02")).toBeInTheDocument();

    const fresh = makeQuoteResult({ price: 217.4, source: "LIVE_QUOTE", is_stale: false, quote_timestamp: new Date().toISOString() });
    rerender(<CurrentPrice quote={fresh} refreshing={false} />);

    expect(screen.getByText("$217.40")).toBeInTheDocument();
    expect(screen.queryByText("$216.02")).not.toBeInTheDocument();
    expect(screen.getByTestId("current-price-freshness").textContent).toMatch(/Updated/);
  });

  it("shows a distinct stale warning for a PERSISTED_QUOTE fallback, using when it was saved", () => {
    const quote = makeQuoteResult({ price: 216.02, source: "PERSISTED_QUOTE", is_stale: true, saved_at: "2026-09-15T10:30:00Z" });
    render(<CurrentPrice quote={quote} />);
    expect(screen.getByText(/Price may be outdated/)).toBeInTheDocument();
    expect(screen.getByText(/Last saved/)).toBeInTheDocument();
  });

  it("retains the last saved price when a refresh fails (quote stays PERSISTED_QUOTE across rerenders)", () => {
    const fresh = makeQuoteResult({ price: 217.4, source: "LIVE_QUOTE" });
    const { rerender } = render(<CurrentPrice quote={fresh} />);
    expect(screen.getByText("$217.40")).toBeInTheDocument();

    // A subsequent poll fails -- the hook falls back to PERSISTED_QUOTE
    // rather than losing the value or showing $0/blank.
    const fallback = makeQuoteResult({ price: 217.4, source: "PERSISTED_QUOTE", is_stale: true, saved_at: "2026-09-15T10:30:00Z" });
    rerender(<CurrentPrice quote={fallback} />);

    expect(screen.getByText("$217.40")).toBeInTheDocument();
    expect(screen.getByText(/Price may be outdated/)).toBeInTheDocument();
  });
});
