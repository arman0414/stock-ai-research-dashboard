"use client";

import Link from "next/link";
import type { StockAnalysis } from "@/lib/types";
import { formatCurrency, formatDateTime, formatPercent } from "@/lib/format";
import { getResearchStrength } from "@/lib/researchStrength";
import SignalBadge from "./SignalBadge";
import ResearchStrengthBadge from "./ResearchStrengthBadge";
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
}

export default function StockCard({ ticker, analysis, loading, error, lastRefreshedAt, onRefresh, onRemove, refreshing }: StockCardProps) {
  const primaryHorizon = analysis?.primary_research_horizon ?? "5d";
  const primary = analysis?.predictions[primaryHorizon as "5d"];

  return (
    <div data-testid={`stock-card-${ticker}`} className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between">
        <div>
          <Link href={`/stocks/${ticker}`} className="text-lg font-semibold text-gray-900 hover:underline">
            {ticker}
          </Link>
          <p className="text-xs text-gray-400">Last updated: {formatDateTime(lastRefreshedAt)}</p>
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
          <div className="flex items-baseline justify-between">
            <p className="text-2xl font-semibold text-gray-900">{formatCurrency(analysis.current_price)}</p>
            <span className="rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-blue-700">
              5D Primary
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <SignalBadge status={primary.classification.signal_status} />
            <ResearchStrengthBadge level={getResearchStrength(primary)} />
          </div>

          <div className="grid grid-cols-3 gap-2">
            {(["5d", "10d", "15d"] as const).map((horizon) => {
              const prediction = analysis.predictions[horizon];
              return (
                <div key={horizon} className="rounded-lg bg-gray-50 p-2 text-center">
                  <p className="text-[10px] font-medium uppercase text-gray-400">{horizon}</p>
                  {prediction ? <SignalBadge status={prediction.classification.signal_status} size="sm" /> : <p className="text-xs text-gray-300">—</p>}
                </div>
              );
            })}
          </div>

          <div className="grid grid-cols-2 gap-3 border-t border-gray-100 pt-3 text-sm">
            <div>
              <p className="text-xs text-gray-400">Calibrated Probability</p>
              <p className="font-medium text-gray-900">{formatPercent(primary.classification.calibrated_probability)}</p>
            </div>
            <div>
              <p className="text-xs text-gray-400">Historical Success</p>
              <p className="font-medium text-gray-900">
                {primary.classification.historical_signal_accuracy !== null ? formatPercent(primary.classification.historical_signal_accuracy) : "Insufficient evidence"}
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-400">Historical Samples</p>
              <p className="font-medium text-gray-900">{primary.classification.historical_signal_samples ?? "—"}</p>
            </div>
            <div>
              <p className="text-xs text-gray-400">Buyer Pressure</p>
              <p className="font-medium text-gray-900">{primary.setup.buyer_pressure}</p>
            </div>
            <div>
              <p className="text-xs text-gray-400">5D Model Target</p>
              <p className="font-medium text-gray-900">{formatCurrency(primary.regression.model_target_price)}</p>
            </div>
            <div>
              <p className="text-xs text-gray-400">5D Range</p>
              <p className="font-medium text-gray-900">
                {formatCurrency(primary.regression.uncertainty_low)} – {formatCurrency(primary.regression.uncertainty_high)}
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-400">Nearest Support</p>
              <p className="font-medium text-gray-900">{formatCurrency(primary.setup.support)}</p>
            </div>
            <div>
              <p className="text-xs text-gray-400">Nearest Resistance</p>
              <p className="font-medium text-gray-900">{formatCurrency(primary.setup.resistance)}</p>
            </div>
          </div>

          <Link
            href={`/stocks/${ticker}`}
            className="block w-full rounded-md border border-gray-300 py-1.5 text-center text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            Open Analysis
          </Link>
        </div>
      )}
    </div>
  );
}
