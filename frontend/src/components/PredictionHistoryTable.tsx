import type { PredictionHistoryRecord } from "@/lib/types";
import { sortForTable } from "@/lib/predictionGrouping";
import { formatCurrency, formatDate, formatSignedCurrency, formatSignedPercentPoints, horizonShortBadge } from "@/lib/format";
import { ACCURACY_LABEL_STYLES, ACCURACY_LABEL_TEXT, accuracyLabelFromDifference } from "@/lib/predictionAccuracy";
import { EmptyState } from "./StatusStates";

/** Flat, scannable view for working through many historical records at once --
 * the counterpart to the grouped cards, which are better for comparing one
 * snapshot's horizons. */
export default function PredictionHistoryTable({ records }: { records: PredictionHistoryRecord[] }) {
  if (records.length === 0) {
    return <EmptyState title="No predictions match these filters." />;
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white">
      <table data-testid="prediction-table" className="w-full min-w-[56rem] text-left text-sm">
        <thead className="border-b border-gray-200 bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
          <tr>
            <Th>Prediction Date</Th>
            <Th>Ticker</Th>
            <Th>Start Price</Th>
            <Th>Horizon</Th>
            <Th>Predicted Price</Th>
            <Th>Final Day Date</Th>
            <Th>Final Day Price</Th>
            <Th>Difference</Th>
            <Th>Accuracy</Th>
            <Th>Direction</Th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {sortForTable(records).map((record) => {
            const resolved = record.outcome_status === "RESOLVED";
            return (
              <tr key={record.id} data-testid={`prediction-row-${record.id}`} className="text-gray-700">
                <Td>{formatDate(record.prediction_date)}</Td>
                <Td className="font-medium text-gray-900">{record.ticker}</Td>
                <Td>{formatCurrency(record.current_price)}</Td>
                <Td>{horizonShortBadge(record.horizon)}</Td>
                <Td className="font-semibold text-gray-900">{formatCurrency(record.model_target_price)}</Td>
                <Td className={resolved ? undefined : "text-gray-400"}>{resolved ? formatDate(record.final_day_date) : "Pending"}</Td>
                <Td className={resolved ? "font-medium text-gray-900" : "text-gray-400"}>{resolved ? formatCurrency(record.actual_future_price) : "Pending"}</Td>
                <Td>
                  {resolved && record.signed_price_difference !== null
                    ? `${formatSignedCurrency(record.signed_price_difference)} (${formatSignedPercentPoints(record.signed_prediction_difference_pct)})`
                    : "—"}
                </Td>
                <Td>
                  {resolved && record.absolute_prediction_difference_pct !== null ? (
                    <span
                      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase ${ACCURACY_LABEL_STYLES[accuracyLabelFromDifference(record.absolute_prediction_difference_pct)]}`}
                    >
                      {ACCURACY_LABEL_TEXT[accuracyLabelFromDifference(record.absolute_prediction_difference_pct)]}
                    </span>
                  ) : (
                    "—"
                  )}
                </Td>
                <Td className={resolved ? (record.regression_direction_match ? "text-green-700" : "text-red-700") : "text-gray-400"}>
                  {resolved ? (record.regression_direction_match ? "Correct" : "Incorrect") : "—"}
                </Td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return <th className="whitespace-nowrap px-3 py-2 font-semibold">{children}</th>;
}

function Td({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <td className={`whitespace-nowrap px-3 py-2 ${className}`}>{children}</td>;
}
