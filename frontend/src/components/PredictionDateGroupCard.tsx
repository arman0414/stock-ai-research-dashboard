import type { PredictionHistoryRecord } from "@/lib/types";
import type { PredictionDateGroup } from "@/lib/predictionGrouping";
import { hasUniformSignal } from "@/lib/predictionGrouping";
import { formatCurrency, formatDate, formatPercent, formatSignedCurrency, formatSignedPercentPoints, horizonDayCount, horizonTradingDaysLabelUpper } from "@/lib/format";
import { ACCURACY_LABEL_STYLES, ACCURACY_LABEL_TEXT, accuracyLabelFromDifference } from "@/lib/predictionAccuracy";
import InfoTooltip from "./InfoTooltip";

const SIGNAL_TEXT: Record<string, string> = { BULLISH: "Bullish", BEARISH: "Bearish", NO_STRONG_SIGNAL: "No Strong Signal" };
const SIGNAL_OUTCOME_TEXT: Record<string, string> = { CORRECT: "Correct", INCORRECT: "Incorrect", NOT_APPLICABLE: "Not Applicable" };

const PENDING_TOOLTIP =
  "A prediction resolves on the exact Nth future trading session, which is not known in advance -- weekends and market holidays don't count, so the calendar date only becomes known once it happens.";

/**
 * One prediction snapshot (one stock, one date) with its 5D/10D/15D horizons
 * side by side. The date and start price are shown once for the whole group,
 * since every horizon of a snapshot shares them.
 */
export default function PredictionDateGroupCard({ group, isLatest = false }: { group: PredictionDateGroup; isLatest?: boolean }) {
  const uniformSignal = hasUniformSignal(group);
  const sharedSignal = group.horizons[0]?.record.signal_status;

  return (
    <article
      data-testid={`prediction-group-${group.ticker}-${group.predictionDate}`}
      data-prediction-date={group.predictionDate}
      className="rounded-xl border border-gray-200 bg-white p-4"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h3 className="text-sm font-semibold text-gray-900">Prediction made {formatDate(group.predictionDate)}</h3>
          {isLatest && (
            <span data-testid="latest-badge" className="rounded-full border border-gray-200 bg-gray-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-gray-500">
              Latest
            </span>
          )}
        </div>
        <p data-testid="group-start-price" className="text-sm text-gray-500">
          Start Price: <span className="font-medium text-gray-700">{formatCurrency(group.startPrice)}</span>
        </p>
      </header>

      {uniformSignal && sharedSignal && (
        <p className="mt-1 text-xs text-gray-400">Model View: {SIGNAL_TEXT[sharedSignal] ?? sharedSignal}</p>
      )}

      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
        {group.horizons.map(({ horizon, record }) => (
          <HorizonColumn key={horizon} record={record} showSignal={!uniformSignal} />
        ))}
      </div>

      <Details records={group.records} />
    </article>
  );
}

function HorizonColumn({ record, showSignal }: { record: PredictionHistoryRecord; showSignal: boolean }) {
  const resolved = record.outcome_status === "RESOLVED";
  return (
    <div data-testid={`horizon-column-${record.horizon}`} data-horizon={record.horizon} className="rounded-lg border border-gray-100 bg-gray-50/50 p-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">{horizonTradingDaysLabelUpper(record.horizon)}</p>

      <div className="mt-2">
        <p className="text-xs text-gray-400">Predicted</p>
        <p data-testid="predicted-price" className="text-lg font-bold text-gray-900">
          {formatCurrency(record.model_target_price)}
        </p>
      </div>

      <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-1 sm:gap-2">
        <div>
          <p className="text-xs text-gray-400">Final Day</p>
          <p className={`text-sm ${resolved ? "font-medium text-gray-900" : "text-gray-400"}`}>{resolved ? formatDate(record.final_day_date) : "Pending"}</p>
        </div>
        <div>
          <p className="text-xs text-gray-400">Final Price</p>
          <p data-testid="final-price" className={`text-sm ${resolved ? "font-semibold text-gray-900" : "text-gray-400"}`}>
            {resolved ? formatCurrency(record.actual_future_price) : "Pending"}
          </p>
        </div>
      </div>

      {!resolved && (
        <p className="mt-2 flex items-center text-[11px] text-gray-400">
          Waiting for {ordinal(horizonDayCount(record.horizon))} trading session
          <InfoTooltip text={PENDING_TOOLTIP} />
        </p>
      )}

      {resolved && record.absolute_prediction_difference_pct !== null && (
        <div className="mt-2 border-t border-gray-200 pt-2">
          <p className="text-xs text-gray-400">Actual vs Predicted</p>
          <p data-testid="signed-difference" className={`text-sm font-semibold ${differenceClass(record.absolute_prediction_difference_pct)}`}>
            {formatSignedCurrency(record.signed_price_difference)} ({formatSignedPercentPoints(record.signed_prediction_difference_pct)})
          </p>
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            <span
              data-testid="accuracy-badge"
              className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase ${ACCURACY_LABEL_STYLES[accuracyLabelFromDifference(record.absolute_prediction_difference_pct)]}`}
            >
              {ACCURACY_LABEL_TEXT[accuracyLabelFromDifference(record.absolute_prediction_difference_pct)]}
            </span>
            <span
              data-testid="direction-badge"
              className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase ${
                record.regression_direction_match ? "border-green-200 bg-green-100 text-green-800" : "border-red-200 bg-red-50 text-red-700"
              }`}
            >
              {record.regression_direction_match ? "Direction Correct" : "Direction Incorrect"}
            </span>
          </div>
        </div>
      )}

      {showSignal && (
        <p className="mt-2 text-[11px] text-gray-400">Model View: {SIGNAL_TEXT[record.signal_status] ?? record.signal_status}</p>
      )}
    </div>
  );
}

/** Only ±10%-or-worse misses get a warning colour; everything else stays
 * neutral so the card isn't a wall of red and green. */
function differenceClass(absolutePct: number): string {
  return absolutePct > 10 ? "text-red-700" : "text-gray-900";
}

function ordinal(value: number): string {
  const suffix = value % 10 === 1 && value % 100 !== 11 ? "st" : value % 10 === 2 && value % 100 !== 12 ? "nd" : value % 10 === 3 && value % 100 !== 13 ? "rd" : "th";
  return `${value}${suffix}`;
}

function Details({ records }: { records: PredictionHistoryRecord[] }) {
  return (
    <details data-testid="prediction-details" className="mt-3 rounded-md border border-gray-200 bg-gray-50 text-sm">
      <summary className="cursor-pointer select-none px-3 py-2 text-xs font-medium text-gray-600">Details</summary>
      <div className="space-y-3 px-3 pb-3 pt-1">
        {records.map((record) => (
          <dl key={record.id} className="grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-3">
            <DetailRow label="Horizon" value={record.horizon.toUpperCase()} />
            <DetailRow label="Calibrated probability" value={formatPercent(record.calibrated_probability)} />
            <DetailRow label="Validated signal" value={SIGNAL_TEXT[record.signal_status] ?? record.signal_status} />
            <DetailRow label="Confidence" value={record.confidence} />
            <DetailRow label="Signal outcome" value={record.signal_outcome ? SIGNAL_OUTCOME_TEXT[record.signal_outcome] ?? record.signal_outcome : "—"} />
            <DetailRow label="Prediction source" value={record.prediction_source} />
            <DetailRow label="Entry Setup" value={record.entry_setup_state ?? "—"} />
            <DetailRow label="Entry Setup version" value={record.entry_setup_version ?? "—"} />
            <DetailRow label="Model version" value={record.model_version} />
          </dl>
        ))}
      </div>
    </details>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-wide text-gray-400">{label}</dt>
      <dd className="break-words font-mono text-xs text-gray-700">{value}</dd>
    </div>
  );
}
