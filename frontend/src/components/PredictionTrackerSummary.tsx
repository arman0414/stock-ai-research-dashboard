import type { PredictionHistoryRecord } from "@/lib/types";
import { summarizeHorizonAccuracy } from "@/lib/predictionGrouping";
import { formatPercent, horizonShortBadge } from "@/lib/format";

/**
 * Compact counts + per-horizon accuracy. Horizons with nothing resolved yet
 * say so explicitly instead of printing 0%, which would read as "the model
 * got everything wrong" rather than "nothing has finished yet".
 */
export default function PredictionTrackerSummary({ records, trackedCount }: { records: PredictionHistoryRecord[]; trackedCount: number }) {
  const resolved = records.filter((r) => r.outcome_status === "RESOLVED").length;
  const accuracy = summarizeHorizonAccuracy(records);

  return (
    <section data-testid="tracker-summary" className="rounded-xl border border-gray-200 bg-white p-4">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Stat label="Tracked Stocks" value={String(trackedCount)} />
        <Stat label="Predictions Saved" value={String(records.length)} />
        <Stat label="Resolved" value={String(resolved)} />
        <Stat label="Pending" value={String(records.length - resolved)} />
      </div>

      <div className="mt-4 grid grid-cols-1 gap-3 border-t border-gray-100 pt-3 sm:grid-cols-3">
        {accuracy.map((entry) => (
          <div key={entry.horizon} data-testid={`horizon-accuracy-${entry.horizon}`}>
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">{horizonShortBadge(entry.horizon)}</p>
            {entry.resolvedCount === 0 ? (
              <p className="mt-0.5 text-sm text-gray-400">No completed predictions yet</p>
            ) : (
              <div className="mt-0.5 space-y-0.5 text-sm text-gray-700">
                <p>
                  Within ±2%: <span className="font-semibold text-gray-900">{formatPercent(entry.withinTwoPctRate, 0)}</span>
                </p>
                <p>
                  Direction Correct: <span className="font-semibold text-gray-900">{formatPercent(entry.directionCorrectRate, 0)}</span>
                </p>
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-gray-400">{label}</p>
      <p className="mt-0.5 text-xl font-semibold text-gray-900">{value}</p>
    </div>
  );
}
