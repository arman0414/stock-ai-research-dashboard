"use client";

import { useEffect, useMemo, useState } from "react";
import { notFound } from "next/navigation";
import Link from "next/link";
import { getDailyRunStatus, getEntrySetup, getPredictionHistory, getSentimentSummary, getStockStructure } from "@/lib/api";
import type { EntrySetupState, Horizon, LiveEntrySetup, PredictionHistoryRecord, SentimentSummary, StockStructure } from "@/lib/types";
import { HORIZONS } from "@/lib/types";
import { useQuotes } from "@/lib/useQuotes";
import ForecastCard from "@/components/ForecastCard";
import ForecastNav from "@/components/ForecastNav";
import InfoTooltip from "@/components/InfoTooltip";
import { LoadingState } from "@/components/StatusStates";

const TITLES: Record<Horizon, string> = { "5d": "5-Day Stock Forecasts", "10d": "10-Day Stock Forecasts", "15d": "15-Day Stock Forecasts" };

const SUBTITLES: Record<Horizon, string> = {
  "5d": "Estimated closing prices approximately 5 trading sessions from the latest completed market session.",
  "10d": "Estimated closing prices approximately 10 trading sessions from the latest completed market session.",
  "15d": "Estimated closing prices approximately 15 trading sessions from the latest completed market session.",
};

const MEANING_TOOLTIP: Record<Horizon, string> = {
  "5d": "Predicted Price is the model's estimated closing price approximately 5 future trading sessions after the prediction date. Trading sessions, not calendar days.",
  "10d": "Predicted Price is the model's estimated closing price approximately 10 future trading sessions after the prediction date. Trading sessions, not calendar days.",
  "15d": "Predicted Price is the model's estimated closing price approximately 15 future trading sessions after the prediction date. Trading sessions, not calendar days.",
};

type SortKey = "ticker" | "change" | "confidence" | "price" | "entrySetup" | "rewardRisk";

const ENTRY_SETUP_SORT_RANK: Record<EntrySetupState, number> = { GOOD_SETUP: 0, WATCH: 1, WAIT: 2, INSUFFICIENT_DATA: 3 };

interface TickerData {
  ticker: string;
  record: PredictionHistoryRecord | null;
  structure: StockStructure | null;
  sentiment: SentimentSummary | null;
  entrySetup: LiveEntrySetup | null;
}

function isHorizon(value: string): value is Horizon {
  return (HORIZONS as string[]).includes(value);
}

export default function ForecastHorizonPage({ params }: { params: Promise<{ horizon: string }> }) {
  const [horizon, setHorizon] = useState<Horizon | null>(null);
  const [invalid, setInvalid] = useState(false);
  const [trackedTickers, setTrackedTickers] = useState<string[] | null>(null);
  const [data, setData] = useState<Record<string, TickerData>>({});
  const [sortKey, setSortKey] = useState<SortKey>("ticker");

  useEffect(() => {
    params.then((resolved) => {
      if (isHorizon(resolved.horizon)) {
        setHorizon(resolved.horizon);
      } else {
        setInvalid(true);
      }
    });
  }, [params]);

  useEffect(() => {
    getDailyRunStatus()
      .then((status) => setTrackedTickers(status.tracked_tickers))
      .catch(() => setTrackedTickers([]));
  }, []);

  useEffect(() => {
    if (!horizon || !trackedTickers) return;
    trackedTickers.forEach((ticker) => {
      Promise.all([
        getPredictionHistory(ticker, horizon, 1).catch(() => [] as PredictionHistoryRecord[]),
        getStockStructure(ticker).catch(() => null),
        getSentimentSummary(ticker).catch(() => null),
        getEntrySetup(ticker, horizon).catch(() => null),
      ]).then(([history, structure, sentiment, entrySetup]) => {
        setData((prev) => ({ ...prev, [ticker]: { ticker, record: history[0] ?? null, structure, sentiment, entrySetup } }));
      });
    });
  }, [horizon, trackedTickers]);

  const { quotes } = useQuotes(trackedTickers ?? []);

  const sorted = useMemo(() => {
    const tickers = trackedTickers ?? [];
    const rows = tickers.map((ticker) => data[ticker]).filter((row): row is TickerData => row !== undefined);
    if (rows.length !== tickers.length) return null; // still loading some tickers

    const sortedRows = [...rows];
    if (sortKey === "change") {
      sortedRows.sort((a, b) => (b.record?.predicted_return ?? -Infinity) - (a.record?.predicted_return ?? -Infinity));
    } else if (sortKey === "confidence") {
      sortedRows.sort((a, b) => (b.record?.calibrated_probability ?? -Infinity) - (a.record?.calibrated_probability ?? -Infinity));
    } else if (sortKey === "price") {
      sortedRows.sort((a, b) => (quotes[b.ticker]?.price ?? -Infinity) - (quotes[a.ticker]?.price ?? -Infinity));
    } else if (sortKey === "entrySetup") {
      // Sort by Entry Setup: GOOD SETUP, then WATCH, then WAIT -- an
      // ordering aid, never presented as "Best Stocks To Buy."
      sortedRows.sort((a, b) => {
        const aState = a.entrySetup?.entry_setup?.state;
        const bState = b.entrySetup?.entry_setup?.state;
        return (aState ? ENTRY_SETUP_SORT_RANK[aState] : 4) - (bState ? ENTRY_SETUP_SORT_RANK[bState] : 4);
      });
    } else if (sortKey === "rewardRisk") {
      sortedRows.sort((a, b) => (b.entrySetup?.entry_setup?.research_reward_risk ?? -Infinity) - (a.entrySetup?.entry_setup?.research_reward_risk ?? -Infinity));
    }
    // "ticker" keeps the configured tracking order -- never auto-sorted by "best stock."
    return sortedRows;
  }, [data, trackedTickers, sortKey, quotes]);

  if (invalid) {
    notFound();
  }

  if (!horizon || !trackedTickers) {
    return <LoadingState label="Loading forecasts…" />;
  }

  return (
    <div className="space-y-4">
      <ForecastNav current={horizon} />

      <div>
        <h1 className="flex items-center gap-2 text-xl font-semibold text-gray-900">
          {TITLES[horizon]}
          <InfoTooltip text={MEANING_TOOLTIP[horizon]} />
          {horizon === "5d" && (
            <span className="rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-blue-700">Best Current Horizon</span>
          )}
          {horizon === "10d" && (
            <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-gray-500">Secondary Horizon</span>
          )}
        </h1>
        <p className="mt-1 text-sm text-gray-500">{SUBTITLES[horizon]}</p>
        {horizon === "15d" && (
          <p className="mt-1 text-xs text-amber-600">15-day forecasts currently have lower historical reliability than the 5-day model.</p>
        )}
      </div>

      <div className="flex items-center justify-between">
        <p className="text-xs text-gray-400">Comparing your {trackedTickers.length} live-tracking stocks</p>
        <label className="flex items-center gap-2 text-xs text-gray-500">
          Sort by:
          <select
            value={sortKey}
            onChange={(event) => setSortKey(event.target.value as SortKey)}
            className="rounded-md border border-gray-200 px-2 py-1 text-xs"
          >
            <option value="ticker">Ticker</option>
            <option value="change">Expected Change %</option>
            <option value="confidence">Model Confidence</option>
            <option value="price">Current Price</option>
            <option value="entrySetup">Entry Setup</option>
            <option value="rewardRisk">Reward/Risk</option>
          </select>
        </label>
      </div>

      {sorted === null ? (
        <LoadingState label="Loading forecasts…" />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {sorted.map((row) => (
            <ForecastCard
              key={row.ticker}
              ticker={row.ticker}
              horizon={horizon}
              record={row.record}
              structure={row.structure}
              sentiment={row.sentiment}
              quote={quotes[row.ticker]}
              liveEntrySetup={row.entrySetup}
            />
          ))}
        </div>
      )}

      <p className="text-xs text-gray-400">
        Looking for past results instead of current forecasts? See the{" "}
        <Link href="/prediction-tracker" className="underline">
          Prediction Tracker
        </Link>
        .
      </p>
    </div>
  );
}
