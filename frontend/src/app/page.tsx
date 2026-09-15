"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, getStockAnalysis, listWatchlist, refreshAllStocks, refreshStock, removeStock } from "@/lib/api";
import type { StockAnalysis, WatchlistItem } from "@/lib/types";
import StockCard from "@/components/StockCard";
import AddStockModal from "@/components/AddStockModal";
import DecisionGuideHelp from "@/components/DecisionGuideHelp";
import { EmptyState, ErrorState, LoadingState } from "@/components/StatusStates";

interface CardState {
  analysis: StockAnalysis | null;
  loading: boolean;
  error: string | null;
  refreshing: boolean;
}

export default function DashboardPage() {
  const [watchlist, setWatchlist] = useState<WatchlistItem[] | null>(null);
  const [watchlistError, setWatchlistError] = useState<string | null>(null);
  const [cards, setCards] = useState<Record<string, CardState>>({});
  const [addOpen, setAddOpen] = useState(false);
  const [refreshingAll, setRefreshingAll] = useState(false);

  const loadCard = useCallback(async (ticker: string) => {
    setCards((prev) => ({ ...prev, [ticker]: { ...(prev[ticker] ?? { analysis: null, refreshing: false }), loading: true, error: null } }));
    try {
      const analysis = await getStockAnalysis(ticker);
      setCards((prev) => ({ ...prev, [ticker]: { analysis, loading: false, error: null, refreshing: false } }));
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Unable to load prediction.";
      setCards((prev) => ({ ...prev, [ticker]: { analysis: prev[ticker]?.analysis ?? null, loading: false, error: message, refreshing: false } }));
    }
  }, []);

  const loadWatchlist = useCallback(async () => {
    try {
      const items = await listWatchlist();
      setWatchlist(items);
      setWatchlistError(null);
      items.forEach((item) => loadCard(item.ticker));
    } catch (err) {
      setWatchlistError(err instanceof ApiError ? err.message : "Could not load your watchlist.");
    }
  }, [loadCard]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch-on-mount, setState happens after the await
    loadWatchlist();
  }, [loadWatchlist]);

  async function handleRefreshOne(ticker: string) {
    setCards((prev) => ({ ...prev, [ticker]: { ...prev[ticker], refreshing: true } }));
    try {
      await refreshStock(ticker);
    } catch {
      // Existing analysis stays visible even if the refresh call itself fails.
    }
    await loadCard(ticker);
    loadWatchlist();
  }

  async function handleRefreshAll() {
    setRefreshingAll(true);
    try {
      await refreshAllStocks();
    } finally {
      await loadWatchlist();
      setRefreshingAll(false);
    }
  }

  async function handleRemove(ticker: string) {
    if (!confirm(`Remove ${ticker} from your watchlist? Historical data is kept.`)) return;
    await removeStock(ticker);
    setCards((prev) => {
      const next = { ...prev };
      delete next[ticker];
      return next;
    });
    loadWatchlist();
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-900">My Stocks</h1>
        <div className="flex gap-2">
          <button
            onClick={handleRefreshAll}
            disabled={refreshingAll}
            className="rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            {refreshingAll ? "Refreshing All…" : "Refresh All"}
          </button>
          <button onClick={() => setAddOpen(true)} className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700">
            + Add Stock
          </button>
        </div>
      </div>

      <div className="mb-4">
        <DecisionGuideHelp />
      </div>

      {watchlist === null && !watchlistError && <LoadingState label="Loading your watchlist…" />}
      {watchlistError && <ErrorState message={watchlistError} onRetry={loadWatchlist} />}
      {watchlist !== null && watchlist.length === 0 && (
        <EmptyState title="No stocks in your watchlist yet." hint="Use + Add Stock to start tracking a ticker." />
      )}

      {watchlist !== null && watchlist.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {watchlist.map((item) => {
            const card = cards[item.ticker] ?? { analysis: null, loading: true, error: null, refreshing: false };
            return (
              <StockCard
                key={item.ticker}
                ticker={item.ticker}
                analysis={card.analysis}
                loading={card.loading}
                error={card.error}
                refreshing={card.refreshing}
                lastRefreshedAt={item.last_refreshed_at}
                onRefresh={() => handleRefreshOne(item.ticker)}
                onRemove={() => handleRemove(item.ticker)}
              />
            );
          })}
        </div>
      )}

      <AddStockModal open={addOpen} onClose={() => setAddOpen(false)} onAdded={loadWatchlist} />
    </div>
  );
}
