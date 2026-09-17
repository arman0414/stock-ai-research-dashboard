import type { PredictionHistoryRecord } from "@/lib/types";
import { groupByPredictionDate } from "@/lib/predictionGrouping";
import PredictionDateGroupCard from "./PredictionDateGroupCard";
import { EmptyState } from "./StatusStates";

/**
 * One stock's saved prediction history, grouped into one card per prediction
 * date with its 5D/10D/15D horizons side by side -- the date and start price
 * belong to the snapshot, so they are shown once per group rather than
 * repeated for every horizon.
 */
export default function PredictionHistoryList({ records }: { records: PredictionHistoryRecord[] }) {
  if (records.length === 0) {
    return <EmptyState title="No prediction history yet." hint="Run New Analysis to start tracking forecasts for this stock." />;
  }

  const groups = groupByPredictionDate(records);

  return (
    <div className="space-y-3">
      {groups.map((group, index) => (
        <PredictionDateGroupCard key={group.predictionDate} group={group} isLatest={index === 0} />
      ))}
    </div>
  );
}
