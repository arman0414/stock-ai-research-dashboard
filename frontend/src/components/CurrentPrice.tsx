"use client";

import { useEffect, useState } from "react";
import type { QuoteResult } from "@/lib/types";
import { formatCurrency, formatDateTime } from "@/lib/format";

function relativeAge(iso: string | null): string | null {
  if (!iso) return null;
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 0 || ms > 60 * 60 * 1000) return null; // fall back to a clock time once it's over an hour old
  if (ms < 60_000) return `${Math.max(1, Math.round(ms / 1000))} sec ago`;
  return `${Math.round(ms / 60_000)} min ago`;
}

/**
 * The single CURRENT PRICE display used across the Dashboard, forecast
 * pages, stock detail page, and positions -- never the frozen prediction
 * start price. Shows a cached/fallback price immediately (never blanks or
 * shows $0) and labels freshness honestly: never "Real-Time" unless the
 * provider guarantees it.
 */
export default function CurrentPrice({
  quote,
  fallbackPrice = null,
  size = "lg",
  refreshing = false,
}: {
  quote: QuoteResult | undefined;
  fallbackPrice?: number | null;
  size?: "lg" | "sm";
  /** True while a background refresh is in flight -- appends "Updating…" to
   * an already-displayed persisted/stale value so the user knows a check
   * for a fresher price is happening, without blocking what's shown. */
  refreshing?: boolean;
}) {
  // Re-render periodically so "Updated N sec ago" keeps counting up.
  const [, forceTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => forceTick((n) => n + 1), 15_000);
    return () => clearInterval(id);
  }, []);

  const priceClass = size === "lg" ? "text-2xl font-semibold text-gray-900" : "text-base font-semibold text-gray-900";
  const price = quote?.price ?? fallbackPrice;

  if (price === null || price === undefined) {
    return (
      <div data-testid="current-price">
        <p className={`${priceClass} text-gray-300`}>{quote === undefined ? "Updating…" : "—"}</p>
      </div>
    );
  }

  let freshnessLabel = "Updating…";
  let freshnessClass = "text-gray-400";
  if (quote) {
    if (quote.source === "PERSISTED_QUOTE") {
      // A live refresh just failed -- we're showing the last value we
      // successfully saved, not a fresh provider response.
      freshnessLabel = `Price may be outdated · Last saved ${formatDateTime(quote.saved_at)}`;
      freshnessClass = "text-amber-600";
    } else if (quote.market_status === "CLOSED") {
      freshnessLabel = `Market Closed · Last Updated ${formatDateTime(quote.quote_timestamp)}`;
    } else if (quote.is_stale) {
      freshnessLabel = `Price may be outdated · Last updated ${formatDateTime(quote.quote_timestamp)}`;
      freshnessClass = "text-amber-600";
    } else {
      const age = relativeAge(quote.quote_timestamp);
      freshnessLabel = `Updated ${age ?? formatDateTime(quote.quote_timestamp)}`;
    }

    // A background refresh is checking for a fresher value than the one
    // we're already showing -- only worth mentioning when what we're
    // showing isn't already confirmed-fresh from this cycle.
    if (refreshing && quote.source !== "LIVE_QUOTE" && quote.source !== "CACHED_QUOTE") {
      freshnessLabel = `${freshnessLabel} · Updating…`;
    }
  }

  return (
    <div data-testid="current-price">
      <p className={priceClass}>{formatCurrency(price)}</p>
      <p data-testid="current-price-freshness" className={`text-xs ${freshnessClass}`}>
        {freshnessLabel}
      </p>
    </div>
  );
}
