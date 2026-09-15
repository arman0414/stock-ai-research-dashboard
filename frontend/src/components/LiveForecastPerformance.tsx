import type { StockLivePerformance } from "@/lib/types";
import { HORIZONS } from "@/lib/types";
import { formatPercent, formatPercentPoints, horizonTradingDaysLabelUpper } from "@/lib/format";
import SampleSizeNotice from "./SampleSizeNotice";

export default function LiveForecastPerformance({ performance }: { performance: StockLivePerformance }) {
  const totalResolved = HORIZONS.reduce((sum, horizon) => sum + (performance.horizons[horizon]?.resolved_count ?? 0), 0);

  return (
    <div data-testid="live-forecast-performance">
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">Live Forecast Performance</h2>
        <p className="text-xs text-gray-400">
          Resolved Forecasts: <span className="font-medium text-gray-700">{totalResolved}</span>
        </p>
      </div>

      <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-3">
        {HORIZONS.map((horizon) => {
          const stats = performance.horizons[horizon];
          const resolvedCount = stats?.resolved_count ?? 0;
          return (
            <div key={horizon} data-testid={`live-performance-${horizon}`} className="rounded-lg border border-gray-100 p-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">{horizonTradingDaysLabelUpper(horizon)}</p>
              <div className="mt-2">
                <SampleSizeNotice resolvedCount={resolvedCount} />
              </div>
              {resolvedCount > 0 && stats && (
                <dl className="mt-2 space-y-1 text-sm">
                  <Row label="Average Miss" value={formatPercentPoints(stats.average_miss_pct)} />
                  <Row label="Within ±2%" value={formatPercent(stats.within_2pct)} />
                  <Row label="Within ±5%" value={formatPercent(stats.within_5pct)} />
                  <Row label="Within ±10%" value={formatPercent(stats.within_10pct)} />
                  <Row label="More Than 10% Off" value={formatPercent(stats.more_than_10pct_off)} />
                  <Row label="Direction Correct" value={formatPercent(stats.direction_correct_rate)} />
                </dl>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-2">
      <dt className="text-gray-400">{label}</dt>
      <dd className="font-medium text-gray-900">{value}</dd>
    </div>
  );
}
