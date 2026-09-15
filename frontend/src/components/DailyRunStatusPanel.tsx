import type { DailyRunStatus, NeverRunStatus } from "@/lib/types";
import { formatDateTime } from "@/lib/format";

const STATUS_TEXT: Record<DailyRunStatus["status"], string> = {
  RUNNING: "RUNNING",
  SUCCESS: "SUCCESS",
  PARTIAL_FAILURE: "PARTIAL FAILURE",
  FAILURE: "FAILURE",
};

const STATUS_STYLES: Record<DailyRunStatus["status"], string> = {
  RUNNING: "bg-blue-50 text-blue-700 border-blue-200",
  SUCCESS: "bg-green-100 text-green-800 border-green-200",
  PARTIAL_FAILURE: "bg-amber-50 text-amber-700 border-amber-200",
  FAILURE: "bg-red-50 text-red-700 border-red-200",
};

function isNeverRun(status: DailyRunStatus | NeverRunStatus): status is NeverRunStatus {
  return status.status === "NEVER_RUN";
}

export default function DailyRunStatusPanel({ status }: { status: DailyRunStatus | NeverRunStatus }) {
  if (isNeverRun(status)) {
    return (
      <div data-testid="daily-run-status" className="rounded-xl border border-gray-200 bg-white p-4">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-500">Daily Automation</h3>
        <p className="mt-2 text-sm text-gray-400">The automated daily prediction run has never run yet.</p>
      </div>
    );
  }

  return (
    <div data-testid="daily-run-status" className="rounded-xl border border-gray-200 bg-white p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-500">Daily Automation</h3>
        <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${STATUS_STYLES[status.status]}`}>
          {STATUS_TEXT[status.status]}
        </span>
      </div>
      <dl className="mt-3 space-y-1.5 text-sm">
        <Row label="Last run" value={formatDateTime(status.finished_at ?? status.started_at)} />
        <Row label="As of market date" value={status.latest_market_date ?? "—"} />
        <Row label="Tickers processed" value={String(status.tickers_processed)} />
        <Row label="Tickers failed" value={String(status.tickers_failed)} />
        <Row label="Predictions saved" value={String(status.predictions_saved)} />
        <Row label="Outcomes resolved" value={String(status.outcomes_resolved)} />
      </dl>
      {status.failures.length > 0 && (
        <div className="mt-3 border-t border-gray-100 pt-2">
          <p className="text-xs font-medium text-gray-500">Failures</p>
          <ul className="mt-1 space-y-0.5 text-xs text-gray-500">
            {status.failures.map((failure) => (
              <li key={failure.ticker}>
                {failure.ticker}: {failure.error}
              </li>
            ))}
          </ul>
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
