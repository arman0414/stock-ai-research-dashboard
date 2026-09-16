"use client";

import Link from "next/link";
import type { EntrySetupState, QuoteResult, StockAnalysis } from "@/lib/types";
import { formatCurrency, formatDateTime, formatPercent, percentAbove, percentBelow } from "@/lib/format";
import PredictionCard from "./PredictionCard";
import CompactHorizonRow from "./CompactHorizonRow";
import CurrentPrice from "./CurrentPrice";
import EntrySetupBadge from "./EntrySetupBadge";
import InfoTooltip from "./InfoTooltip";
import { LoadingState, ErrorState } from "./StatusStates";

interface StockCardProps {
  ticker: string;
  analysis: StockAnalysis | null;
  loading: boolean;
  error: string | null;
  lastRefreshedAt: string | null;
  onRefresh: () => void;
  onRemove: () => void;
  refreshing?: boolean;
  quote?: QuoteResult;
  /** Compact-only on the Dashboard -- the full checklist belongs on the
   * forecast/detail pages. Omit entirely for stocks Entry Setup isn't
   * tracked for. */
  entrySetupState?: EntrySetupState;
}

export default function StockCard({ ticker, analysis, loading, error, lastRefreshedAt, onRefresh, onRemove, refreshing, quote, entrySetupState }: StockCardProps) {
  const primaryHorizon = analysis?.primary_research_horizon ?? "5d";
  const primary = analysis?.predictions[primaryHorizon as "5d"];
  const secondaryHorizons = (["10d", "15d"] as const).filter((horizon) => horizon !== primaryHorizon);

  return (
    <div data-testid={`stock-card-${ticker}`} className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between">
        <div>
          <Link href={`/stocks/${ticker}`} className="text-lg font-semibold text-gray-900 hover:underline">
            {ticker}
          </Link>
          <div className="mt-1">
            <CurrentPrice quote={quote} fallbackPrice={analysis?.current_price ?? null} size="sm" />
          </div>
          {entrySetupState && (
            <div className="mt-1.5 flex items-center gap-1.5">
              <span className="text-[10px] uppercase tracking-wide text-gray-400">Entry Setup:</span>
              <EntrySetupBadge state={entrySetupState} size="sm" />
            </div>
          )}
          <p className="text-xs text-gray-400">Refreshed data as of: {formatDateTime(lastRefreshedAt)}</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={onRefresh}
            disabled={refreshing}
            className="rounded-md border border-gray-200 px-2 py-1 text-xs font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-50"
          >
            {refreshing ? "Refreshing…" : "Refresh"}
          </button>
          <button onClick={onRemove} className="rounded-md border border-gray-200 px-2 py-1 text-xs font-medium text-red-500 hover:bg-red-50">
            Remove
          </button>
        </div>
      </div>

      {loading && <LoadingState label={`Loading ${ticker}…`} />}

      {!loading && error && <ErrorState message={`Unable to refresh ${ticker}. ${error}`} onRetry={onRefresh} />}

      {!loading && !error && analysis && primary && (
        <div className="mt-3 space-y-3">
          <PredictionCard prediction={primary} emphasized />

          <div className="grid grid-cols-3 gap-3 border-t border-gray-100 pt-3 text-sm">
            <div>
              <p className="text-xs text-gray-400">
                Buyer Pressure
                <InfoTooltip text="Buyer pressure is inferred from historical price and volume behavior. It is not direct Level 2/order-book data." />
              </p>
              <p className="font-medium text-gray-900">{primary.setup.buyer_pressure}</p>
            </div>
            <div>
              <p className="text-xs text-gray-400">Support</p>
              <p className="font-medium text-gray-900">{formatCurrency(primary.setup.support)}</p>
              {primary.setup.support !== null && (
                <p className="text-xs text-gray-400">
                  {formatPercent(analysis.structure?.distance_to_support ?? percentBelow(analysis.current_price, primary.setup.support))} below current price
                </p>
              )}
            </div>
            <div>
              <p className="text-xs text-gray-400">Resistance</p>
              <p className="font-medium text-gray-900">{formatCurrency(primary.setup.resistance)}</p>
              {primary.setup.resistance !== null && (
                <p className="text-xs text-gray-400">
                  {formatPercent(analysis.structure?.distance_to_resistance ?? percentAbove(analysis.current_price, primary.setup.resistance))} above current price
                </p>
              )}
            </div>
          </div>

          <div className="space-y-2 border-t border-gray-100 pt-3">
            {secondaryHorizons.map((horizon) => {
              const prediction = analysis.predictions[horizon];
              return prediction ? <CompactHorizonRow key={horizon} prediction={prediction} /> : null;
            })}
          </div>

          <Link
            href={`/stocks/${ticker}`}
            className="block w-full rounded-md border border-gray-300 py-1.5 text-center text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            Open Full Analysis
          </Link>
        </div>
      )}
    </div>
  );
}
