"use client";

import { useEffect, useMemo, useState } from "react";
import { getDailyRunStatus, getPredictionHistory } from "@/lib/api";
import type { Horizon, PredictionHistoryRecord } from "@/lib/types";
import { HORIZONS } from "@/lib/types";
import { applyFilters, groupByTicker, type DateFilter, type HorizonFilter, type StatusFilter, type TrackerFilters } from "@/lib/predictionGrouping";
import { formatCurrency, horizonShortBadge } from "@/lib/format";
import PredictionDateGroupCard from "@/components/PredictionDateGroupCard";
import PredictionHistoryTable from "@/components/PredictionHistoryTable";
import PredictionTrackerSummary from "@/components/PredictionTrackerSummary";
import ResolvedPredictionCharts from "@/components/ResolvedPredictionCharts";
import InfoTooltip from "@/components/InfoTooltip";
import { useQuotes } from "@/lib/useQuotes";
import { EmptyState, LoadingState } from "@/components/StatusStates";

type ViewMode = "GROUPED" | "TABLE";

const DIFFERENCE_TOOLTIP =
  "Difference is Final Day Price minus Predicted Price: + means the stock finished HIGHER than predicted, - means it finished LOWER.";

/**
 * PAST FORECAST RESULTS -- how officially-tracked predictions have actually
 * turned out, once resolved. Kept separate from the /forecast/* pages, which
 * show CURRENT forecasts only. Never mixed together.
 *
 * Everything on this page is a re-shaping of records the backend already
 * saved: no prediction, outcome, or accuracy value is computed here.
 */
export default function PredictionTrackerPage() {
  const [trackedTickers, setTrackedTickers] = useState<string[] | null>(null);
  const [records, setRecords] = useState<Record<string, PredictionHistoryRecord[]>>({});
  const [view, setView] = useState<ViewMode>("GROUPED");
  const [filters, setFilters] = useState<TrackerFilters>({ ticker: "ALL", horizon: "ALL", status: "ALL", date: "ALL" });

  useEffect(() => {
    let active = true;
    getDailyRunStatus()
      .then((status) => active && setTrackedTickers(status.tracked_tickers))
      .catch(() => active && setTrackedTickers([]));
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!trackedTickers) return;
    let active = true;
    // One request per tracked stock (five), all in flight together -- never
    // one request per prediction record.
    Promise.all(
      trackedTickers.map((ticker) =>
        getPredictionHistory(ticker, undefined, 200)
          .then((history) => [ticker, history] as const)
          .catch(() => [ticker, [] as PredictionHistoryRecord[]] as const)
      )
    ).then((entries) => {
      if (!active) return;
      setRecords(Object.fromEntries(entries));
    });
    return () => {
      active = false;
    };
  }, [trackedTickers]);

  const { quotes } = useQuotes(trackedTickers ?? []);

  const allRecords = useMemo(() => Object.values(records).flat(), [records]);
  const filtered = useMemo(() => applyFilters(allRecords, filters), [allRecords, filters]);
  const tickerGroups = useMemo(() => groupByTicker(filtered, trackedTickers ?? []), [filtered, trackedTickers]);

  const loadedTickerCount = Object.keys(records).length;
  if (!trackedTickers) return <LoadingState label="Loading prediction tracker…" />;

  const visibleGroups = filters.ticker === "ALL" ? tickerGroups : tickerGroups.filter((group) => group.ticker === filters.ticker);
  const nothingMatches = filtered.length === 0 && allRecords.length > 0;
  const noneResolved = allRecords.length > 0 && allRecords.every((record) => record.outcome_status === "PENDING");

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold text-gray-900">Live Prediction Tracker</h1>
        <p className="mt-1 flex flex-wrap items-center text-sm text-gray-500">
          Past official forecasts for your live-tracking stocks, with Final Day Date and Final Day Price once resolved.
          <InfoTooltip text={DIFFERENCE_TOOLTIP} />
        </p>
      </header>

      <PredictionTrackerSummary records={allRecords} trackedCount={trackedTickers.length} />

      <section className="space-y-3 rounded-xl border border-gray-200 bg-white p-4">
        <FilterRow label="Stock">
          <FilterButton active={filters.ticker === "ALL"} onClick={() => setFilters((f) => ({ ...f, ticker: "ALL" }))}>
            All
          </FilterButton>
          {trackedTickers.map((ticker) => (
            <FilterButton key={ticker} active={filters.ticker === ticker} onClick={() => setFilters((f) => ({ ...f, ticker }))}>
              {ticker}
            </FilterButton>
          ))}
        </FilterRow>

        <FilterRow label="Horizon">
          {(["ALL", ...HORIZONS] as HorizonFilter[]).map((horizon) => (
            <FilterButton key={horizon} active={filters.horizon === horizon} onClick={() => setFilters((f) => ({ ...f, horizon }))}>
              {horizon === "ALL" ? "All" : horizonShortBadge(horizon as Horizon)}
            </FilterButton>
          ))}
        </FilterRow>

        <FilterRow label="Status">
          {(["ALL", "PENDING", "RESOLVED"] as StatusFilter[]).map((status) => (
            <FilterButton key={status} active={filters.status === status} onClick={() => setFilters((f) => ({ ...f, status }))}>
              {status === "ALL" ? "All" : status.charAt(0) + status.slice(1).toLowerCase()}
            </FilterButton>
          ))}
        </FilterRow>

        <FilterRow label="Date">
          {(
            [
              ["7D", "Last 7 Days"],
              ["30D", "30 Days"],
              ["ALL", "All"],
            ] as [DateFilter, string][]
          ).map(([value, label]) => (
            <FilterButton key={value} active={filters.date === value} onClick={() => setFilters((f) => ({ ...f, date: value }))}>
              {label}
            </FilterButton>
          ))}
        </FilterRow>

        <div className="flex items-center gap-2 border-t border-gray-100 pt-3">
          <span className="w-16 shrink-0 text-xs font-medium uppercase tracking-wide text-gray-400">View</span>
          {(["GROUPED", "TABLE"] as ViewMode[]).map((mode) => (
            <FilterButton key={mode} active={view === mode} onClick={() => setView(mode)} testId={`view-toggle-${mode.toLowerCase()}`}>
              {mode}
            </FilterButton>
          ))}
        </div>
      </section>

      {loadedTickerCount === 0 ? (
        <LoadingState label="Loading saved predictions…" />
      ) : nothingMatches ? (
        <EmptyState title="No predictions match these filters." />
      ) : allRecords.length === 0 ? (
        <EmptyState title="No predictions saved yet." hint="Predictions are saved by the daily run and by Run New Analysis." />
      ) : view === "TABLE" ? (
        <PredictionHistoryTable records={filtered} />
      ) : (
        <div className="space-y-6">
          {noneResolved && (
            <p data-testid="none-resolved-note" className="rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-sm text-blue-800">
              Predictions are being collected. Results will appear after the required trading sessions pass.
            </p>
          )}

          {visibleGroups.map((group) => {
            const quote = quotes[group.ticker];
            return (
              <section key={group.ticker} data-testid={`ticker-section-${group.ticker}`} className="space-y-3">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <div className="flex flex-wrap items-baseline gap-2">
                    <h2 className="text-lg font-semibold text-gray-900">{group.ticker}</h2>
                    <span className="text-xs uppercase tracking-wide text-gray-400">Live Prediction History</span>
                  </div>
                  <p className="text-sm text-gray-500">
                    {quote?.price !== undefined && quote?.price !== null && (
                      <span className="mr-3">
                        Current: <span className="font-medium text-gray-700">{formatCurrency(quote.price)}</span>
                      </span>
                    )}
                    {group.resolvedCount} resolved · {group.pendingCount} pending
                  </p>
                </div>

                {filters.ticker === group.ticker && <ResolvedPredictionCharts ticker={group.ticker} records={filtered.filter((r) => r.ticker === group.ticker)} />}

                {group.dateGroups.length === 0 ? (
                  <EmptyState title={`No predictions saved for ${group.ticker} yet.`} />
                ) : (
                  <div className="space-y-3">
                    {group.dateGroups.map((dateGroup, index) => (
                      <PredictionDateGroupCard key={dateGroup.predictionDate} group={dateGroup} isLatest={index === 0} />
                    ))}
                  </div>
                )}
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}

function FilterRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="w-16 shrink-0 text-xs font-medium uppercase tracking-wide text-gray-400">{label}</span>
      {children}
    </div>
  );
}

function FilterButton({ active, onClick, children, testId }: { active: boolean; onClick: () => void; children: React.ReactNode; testId?: string }) {
  return (
    <button
      type="button"
      data-testid={testId}
      aria-pressed={active}
      onClick={onClick}
      className={`rounded-md px-2.5 py-1 text-xs font-medium ${active ? "bg-gray-900 text-white" : "border border-gray-200 text-gray-600 hover:bg-gray-100"}`}
    >
      {children}
    </button>
  );
}
