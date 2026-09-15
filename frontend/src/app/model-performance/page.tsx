"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, getModelPerformance } from "@/lib/api";
import type { Horizon, ModelPerformanceSummary } from "@/lib/types";
import { HORIZONS } from "@/lib/types";
import { formatCurrency, formatPercent } from "@/lib/format";
import { ErrorState, LoadingState } from "@/components/StatusStates";
import Disclaimer from "@/components/Disclaimer";

export default function ModelPerformancePage() {
  const [summary, setSummary] = useState<ModelPerformanceSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setSummary(await getModelPerformance());
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
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-gray-900">Model Performance</h1>
        <p className="mt-1 text-sm text-gray-500">
          An honest look at how trustworthy each horizon currently is. Numbers come from a held-out test set the model never trained on.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {HORIZONS.map((horizon) => (
          <HorizonPerformanceCard key={horizon} horizon={horizon} summary={summary} />
        ))}
      </div>

      <Disclaimer />
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
