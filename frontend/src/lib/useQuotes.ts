"use client";

import { useCallback, useEffect, useState } from "react";
import { getStockQuotes } from "./api";
import type { QuoteResult } from "./types";

const POLL_INTERVAL_MS = 60_000;

/**
 * Fresh CURRENT PRICE quotes for a set of tickers -- one batched request,
 * refreshed periodically only while the tab is visible. This is
 * presentation-only: it never triggers a prediction, never touches stored
 * price history, and never overwrites a prediction's frozen start price.
 */
export function useQuotes(tickers: string[]): { quotes: Record<string, QuoteResult>; refreshing: boolean; refresh: () => void } {
  const [quotes, setQuotes] = useState<Record<string, QuoteResult>>({});
  const [refreshing, setRefreshing] = useState(false);
  const tickersKey = tickers.join(",");

  const refresh = useCallback(() => {
    // Reconstructed from tickersKey (not the `tickers` array reference)
    // so this callback stays stable across parent re-renders that don't
    // actually change the ticker set.
    const current = tickersKey ? tickersKey.split(",") : [];
    if (current.length === 0) return;
    setRefreshing(true);
    getStockQuotes(current)
      .then((result) => setQuotes((prev) => ({ ...prev, ...result })))
      .catch(() => undefined)
      .finally(() => setRefreshing(false));
  }, [tickersKey]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch-on-mount; this is the one legitimate "sync external data on mount" case
    refresh();

    const interval = setInterval(() => {
      if (document.visibilityState === "visible") refresh();
    }, POLL_INTERVAL_MS);

    function onVisibilityChange() {
      if (document.visibilityState === "visible") refresh();
    }
    document.addEventListener("visibilitychange", onVisibilityChange);

    return () => {
      clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tickersKey]);

  return { quotes, refreshing, refresh };
}
