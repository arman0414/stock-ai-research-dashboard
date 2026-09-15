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
});
