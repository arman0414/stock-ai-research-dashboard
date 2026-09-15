import type { ModelReviewStatus as ModelReviewStatusType } from "@/lib/types";

const STATUS_TEXT: Record<ModelReviewStatusType["status"], string> = {
  NOT_TRAINED: "NOT TRAINED YET",
  COLLECTING_DATA: "COLLECTING DATA",
  READY_FOR_MODEL_REVIEW: "READY FOR MODEL REVIEW",
};

const STATUS_STYLES: Record<ModelReviewStatusType["status"], string> = {
  NOT_TRAINED: "bg-gray-100 text-gray-600 border-gray-200",
  COLLECTING_DATA: "bg-amber-50 text-amber-700 border-amber-200",
  READY_FOR_MODEL_REVIEW: "bg-green-100 text-green-800 border-green-200",
};

const STATUS_DESCRIPTION: Record<ModelReviewStatusType["status"], string> = {
  NOT_TRAINED: "No champion model has been trained for this horizon yet.",
  COLLECTING_DATA: "Not enough fresh live results yet to meaningfully review this model. It keeps serving predictions unchanged in the meantime.",
  READY_FOR_MODEL_REVIEW: "Enough fresh live results have accumulated for a human to review whether this model should be reviewed. Nothing retrains or changes automatically.",
};

export default function ModelReviewStatus({ status }: { status: ModelReviewStatusType }) {
  const pct = status.threshold > 0 ? Math.min(100, (status.resolved_new_live_predictions / status.threshold) * 100) : 0;

  return (
    <div data-testid="model-review-status" className="rounded-xl border border-gray-200 bg-white p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-500">Model Review Readiness</h3>
        <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${STATUS_STYLES[status.status]}`}>
          {STATUS_TEXT[status.status]}
        </span>
      </div>
      <p className="mt-2 text-xs text-gray-500">{STATUS_DESCRIPTION[status.status]}</p>
      {status.status !== "NOT_TRAINED" && (
        <>
          <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-gray-100">
            <div className="h-full rounded-full bg-blue-500" style={{ width: `${pct}%` }} />
          </div>
          <p className="mt-1 text-xs text-gray-400">
            {status.resolved_new_live_predictions} of {status.threshold} new resolved {status.horizon} live forecasts since this model was trained.
          </p>
        </>
      )}
      <p className="mt-3 border-t border-gray-100 pt-2 text-[11px] text-gray-400">
        This is informational only. Reaching readiness never retrains or promotes a new model automatically -- that always requires a manual review.
      </p>
    </div>
  );
}
