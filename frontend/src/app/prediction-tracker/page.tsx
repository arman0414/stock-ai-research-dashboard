"use client";

import { useEffect, useState } from "react";
import { getDailyRunStatus, getPredictionHistory } from "@/lib/api";
import type { PredictionHistoryRecord } from "@/lib/types";
import PredictionHistoryList from "@/components/PredictionHistoryList";
import { LoadingState } from "@/components/StatusStates";

/**
 * PAST FORECAST RESULTS -- how officially-tracked predictions have actually
 * turned out, once resolved. Kept separate from the /forecast/* pages, which
 * show CURRENT forecasts only. Never mixed together.
 */
export default function PredictionTrackerPage() {
  const [trackedTickers, setTrackedTickers] = useState<string[] | null>(null);
  const [records, setRecords] = useState<Record<string, PredictionHistoryRecord[]>>({});

  useEffect(() => {
    getDailyRunStatus()
      .then((status) => setTrackedTickers(status.tracked_tickers))
      .catch(() => setTrackedTickers([]));
  }, []);

  useEffect(() => {
    if (!trackedTickers) return;
    trackedTickers.forEach((ticker) => {
      getPredictionHistory(ticker, undefined, 50)
        .then((history) => setRecords((prev) => ({ ...prev, [ticker]: history })))
        .catch(() => setRecords((prev) => ({ ...prev, [ticker]: [] })));
    });
  }, [trackedTickers]);

  if (!trackedTickers) return <LoadingState label="Loading prediction tracker…" />;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-gray-900">Prediction Tracker</h1>
        <p className="mt-1 text-sm text-gray-500">
          Past official forecasts for your live-tracking stocks, with Final Day Date and Final Day Price once resolved. For current forecasts, see the
          Forecasts pages instead.
        </p>
      </div>

      {trackedTickers.map((ticker) => (
        <section key={ticker} className="rounded-xl border border-gray-200 bg-white p-4">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-700">{ticker}</h2>
          {records[ticker] === undefined ? <LoadingState label={`Loading ${ticker}…`} /> : <PredictionHistoryList records={records[ticker]} />}
        </section>
      ))}
    </div>
  );
}
