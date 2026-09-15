"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, getModelLivePerformance, getModelPerformance, getModelReviewStatus } from "@/lib/api";
import type { Horizon, ModelLivePerformance, ModelPerformanceSummary, ModelReviewStatus as ModelReviewStatusType } from "@/lib/types";
import { HORIZONS } from "@/lib/types";
import { formatCurrency, formatPercent, formatPercentPoints, horizonTradingDaysLabelUpper } from "@/lib/format";
import { ErrorState, LoadingState } from "@/components/StatusStates";
import SampleSizeNotice from "@/components/SampleSizeNotice";
import ModelReviewStatus from "@/components/ModelReviewStatus";
import Disclaimer from "@/components/Disclaimer";

export default function ModelPerformancePage() {
  const [summary, setSummary] = useState<ModelPerformanceSummary | null>(null);
  const [livePerformance, setLivePerformance] = useState<ModelLivePerformance | null>(null);
  const [reviewStatus, setReviewStatus] = useState<ModelReviewStatusType | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [backtest, live, review] = await Promise.all([getModelPerformance(), getModelLivePerformance(), getModelReviewStatus()]);
      setSummary(backtest);
      setLivePerformance(live);
      setReviewStatus(review);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load model performance.");
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch-on-mount, setState happens after the await
    load();
  }, [load]);

  if (!summary && !error) return <LoadingState label="Loading model performance…" />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!summary) return null;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-xl font-semibold text-gray-900">Model Performance</h1>
        <p className="mt-1 text-sm text-gray-500">
          Two different questions, kept deliberately separate: how the model has actually done on real predictions later checked against real
          future prices, and how it did on held-out historical data it never trained on.
        </p>
      </div>

      {reviewStatus && <ModelReviewStatus status={reviewStatus} />}

      {livePerformance && (
        <section>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-700">Live Model Results</h2>
          <p className="mt-1 text-xs text-gray-400">
            Grows over time as real predictions are made and later checked against real future prices. Never combined with the backtest numbers
            below.
          </p>
          <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-3">
            {HORIZONS.map((horizon) => (
              <LiveHorizonPerformanceCard key={horizon} horizon={horizon} livePerformance={livePerformance} />
            ))}
          </div>
        </section>
      )}

      <section>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-700">Historical Backtest Results</h2>
        <p className="mt-1 text-xs text-gray-400">Computed once, from a held-out test split during training. Never updates as new predictions resolve.</p>
        <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-3">
          {HORIZONS.map((horizon) => (
            <HorizonPerformanceCard key={horizon} horizon={horizon} summary={summary} />
          ))}
        </div>
      </section>

      <Disclaimer />
    </div>
  );
}

function LiveHorizonPerformanceCard({ horizon, livePerformance }: { horizon: Horizon; livePerformance: ModelLivePerformance }) {
  const stats = livePerformance.horizons[horizon];

  if (!stats || stats.status === "NOT_TRAINED") {
    return (
      <div data-testid={`live-forward-${horizon}`} className="rounded-xl border border-gray-200 bg-white p-4">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-500">{horizonTradingDaysLabelUpper(horizon)}</h3>
        <p className="mt-2 text-sm text-gray-400">Not trained yet.</p>
      </div>
    );
  }

  const resolvedCount = stats.resolved_count ?? 0;

  return (
    <div data-testid={`live-forward-${horizon}`} className="rounded-xl border border-gray-200 bg-white p-4">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-500">{horizonTradingDaysLabelUpper(horizon)}</h3>
      <p className="mt-1">
        Completed: <span className="font-medium text-gray-900">{resolvedCount}</span>
      </p>
      <div className="mt-2">
        <SampleSizeNotice resolvedCount={resolvedCount} />
      </div>
      {resolvedCount > 0 && (
        <dl className="mt-3 space-y-1.5 text-sm">
          <Row label="Within ±2%" value={formatPercent(stats.within_2pct)} />
          <Row label="Within ±5%" value={formatPercent(stats.within_5pct)} />
          <Row label="Within ±10%" value={formatPercent(stats.within_10pct)} />
          <Row label="Direction Correct" value={formatPercent(stats.direction_correct_rate)} />
          <Row label="Average Miss" value={formatPercentPoints(stats.average_miss_pct)} />
        </dl>
      )}
    </div>
  );
}

function HorizonPerformanceCard({ horizon, summary }: { horizon: Horizon; summary: ModelPerformanceSummary }) {
  const performance = summary.horizons[horizon];

  if (!performance || performance.status === "NOT_TRAINED") {
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">{horizon}</h2>
        <p className="mt-2 text-sm text-gray-400">Not trained yet.</p>
      </div>
    );
  }

  return (
    <div className={`rounded-xl border p-4 ${performance.is_primary_research_horizon ? "border-blue-300 bg-blue-50/40" : "border-gray-200 bg-white"}`}>
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">{horizon}</h2>
        {performance.is_primary_research_horizon && (
          <span className="rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-blue-700">Primary</span>
        )}
      </div>
      <p className="mt-1 text-sm font-medium text-gray-900">{performance.status_label}</p>
      <p className="text-xs text-gray-400">Signal: Experimental Research Model</p>

      <dl className="mt-3 space-y-1.5 text-sm">
        <Row label="Calibration method" value={performance.calibration_method ?? "—"} />
        <Row label="Model Target MAE" value={formatCurrency(performance.target_price_mae)} />
        <Row label="Within ±5% of actual price" value={formatPercent(performance.within_5pct)} />
        <Row label="Within ±10% of actual price" value={formatPercent(performance.within_10pct)} />
        <Row
          label="Bullish signal"
          value={
            performance.bullish_status === "VALIDATED"
              ? `${formatPercent(performance.bullish_test_precision)} precision (${performance.bullish_test_sample_count} samples)`
              : "Not currently validated"
          }
        />
        <Row
          label="Bearish signal"
          value={performance.bearish_status === "VALIDATED" ? `${formatPercent(performance.bearish_test_precision)} precision` : "Not currently validated"}
        />
        <Row
          label="Multi-seed stability"
          value={
            performance.multi_seed_balanced_accuracy_mean != null
              ? `${formatPercent(performance.multi_seed_balanced_accuracy_mean)} ± ${formatPercent(performance.multi_seed_balanced_accuracy_std, 2)}`
              : "—"
          }
        />
      </dl>

      {performance.reliability_test_calibrated && performance.reliability_test_calibrated.some((row) => row.count > 0) && (
        <div className="mt-3 border-t border-gray-100 pt-3">
          <p className="text-xs font-medium text-gray-500">Calibration reliability (test set)</p>
          <table className="mt-1 w-full text-xs">
            <thead>
              <tr className="text-gray-400">
                <th className="text-left font-normal">Confidence</th>
                <th className="text-right font-normal">Actual success</th>
                <th className="text-right font-normal">Samples</th>
              </tr>
            </thead>
            <tbody>
              {performance.reliability_test_calibrated
                .filter((row) => row.count > 0)
                .map((row) => (
                  <tr key={row.bucket}>
                    <td className="py-0.5 text-gray-600">{row.bucket}</td>
                    <td className="py-0.5 text-right text-gray-900">{formatPercent(row.actual_success_rate)}</td>
                    <td className="py-0.5 text-right text-gray-400">{row.count}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-2">
      <dt className="text-gray-400">{label}</dt>
      <dd className="text-right font-medium text-gray-900">{value}</dd>
    </div>
  );
}
