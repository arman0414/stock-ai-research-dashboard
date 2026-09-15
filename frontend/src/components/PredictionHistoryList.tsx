import type { PredictionHistoryRecord } from "@/lib/types";
import { formatCurrency, formatDate, formatPercent, horizonTradingDaysLabel } from "@/lib/format";
import { ACCURACY_LABEL_STYLES, ACCURACY_LABEL_TEXT, accuracyLabelFromError } from "@/lib/predictionAccuracy";
import { EmptyState } from "./StatusStates";

const SIGNAL_OUTCOME_TEXT: Record<string, string> = { CORRECT: "Correct", INCORRECT: "Incorrect", NOT_APPLICABLE: "Not Applicable" };
const SIGNAL_TEXT: Record<string, string> = { BULLISH: "Bullish", BEARISH: "Bearish", NO_STRONG_SIGNAL: "No Strong Signal" };

export default function PredictionHistoryList({ records }: { records: PredictionHistoryRecord[] }) {
  if (records.length === 0) {
    return <EmptyState title="No prediction history yet." hint="Run New Analysis to start tracking forecasts for this stock." />;
  }

  // Newest first, by market date then horizon for a stable, readable order.
  const sorted = [...records].sort((a, b) => (a.prediction_date < b.prediction_date ? 1 : a.prediction_date > b.prediction_date ? -1 : a.horizon.localeCompare(b.horizon)));

  return (
    <ul className="space-y-3">
      {sorted.map((record) => (
        <li key={record.id} data-testid={`prediction-history-${record.id}`} className="rounded-lg border border-gray-100 p-3 text-sm">
          <div className="flex items-center justify-between">
            <p className="font-medium text-gray-800">
              {formatDate(record.prediction_date)} Prediction — {horizonTradingDaysLabel(record.horizon)}
            </p>
            <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase ${record.outcome_status === "RESOLVED" ? "border-gray-200 bg-gray-50 text-gray-600" : "border-blue-200 bg-blue-50 text-blue-700"}`}>
              {record.outcome_status}
            </span>
          </div>

          <div className="mt-2 grid grid-cols-2 gap-2 text-gray-600 sm:grid-cols-3">
            <Field label="Start Price" value={formatCurrency(record.current_price)} />
            <Field label="Predicted" value={formatCurrency(record.model_target_price)} />
            <Field
              label="Actual"
              value={record.outcome_status === "RESOLVED" ? formatCurrency(record.actual_future_price) : "Pending"}
            />
          </div>

          {record.outcome_status === "PENDING" && (
            <p className="mt-2 text-xs text-gray-400">Waiting for: {horizonTradingDaysLabel(record.horizon).toLowerCase()}</p>
          )}

          {record.outcome_status === "RESOLVED" && record.absolute_percentage_error !== null && (
            <div className="mt-2 grid grid-cols-2 gap-2 border-t border-gray-100 pt-2 text-gray-600 sm:grid-cols-3">
              <Field label="Error" value={formatPercent(record.absolute_percentage_error)} />
              <div>
                <p className="text-xs text-gray-400">Result</p>
                <span className={`mt-0.5 inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase ${ACCURACY_LABEL_STYLES[accuracyLabelFromError(record.absolute_percentage_error)]}`}>
                  {ACCURACY_LABEL_TEXT[accuracyLabelFromError(record.absolute_percentage_error)]}
                </span>
              </div>
              <Field label="Regression Direction" value={record.regression_direction_match ? "Correct" : "Incorrect"} />
            </div>
          )}

          <div className="mt-2 flex items-center gap-2 border-t border-gray-100 pt-2 text-xs text-gray-500">
            <span>Validated Signal: {SIGNAL_TEXT[record.signal_status] ?? record.signal_status}</span>
            {record.signal_outcome && <span>· Signal Outcome: {SIGNAL_OUTCOME_TEXT[record.signal_outcome] ?? record.signal_outcome}</span>}
          </div>
        </li>
      ))}
    </ul>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-gray-400">{label}</p>
      <p className="font-medium text-gray-900">{value}</p>
    </div>
  );
}
