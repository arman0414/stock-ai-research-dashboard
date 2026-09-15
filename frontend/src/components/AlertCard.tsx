import type { AlertStatus } from "@/lib/types";
import { ALERT_TYPES } from "@/lib/types";
import { formatCurrency, formatDateTime } from "@/lib/format";
import SignalBadge from "./SignalBadge";

export default function AlertCard({ status, onDelete }: { status: AlertStatus; onDelete: () => void }) {
  const { rule } = status;
  const typeLabel = ALERT_TYPES.find((option) => option.value === rule.alert_type)?.label ?? rule.alert_type;

  return (
    <div
      data-testid={`alert-card-${rule.id}`}
      className={`rounded-xl border p-4 ${status.is_triggered ? "border-amber-300 bg-amber-50" : "border-gray-200 bg-white"}`}
    >
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm font-semibold text-gray-900">{rule.ticker}</p>
          <p className="text-xs text-gray-500">{typeLabel}</p>
        </div>
        <button onClick={onDelete} className="text-xs font-medium text-red-500 hover:underline">
          Remove
        </button>
      </div>

      {status.is_triggered ? (
        <p className="mt-2 text-sm font-medium text-amber-800">{status.message}</p>
      ) : (
        <p className="mt-2 text-sm text-gray-400">Not triggered yet.</p>
      )}

      <div className="mt-3 grid grid-cols-2 gap-3 border-t border-gray-100 pt-3 text-sm">
        {rule.threshold_price !== null && (
          <div>
            <p className="text-xs text-gray-400">Your Threshold</p>
            <p className="font-medium text-gray-900">{formatCurrency(rule.threshold_price)}</p>
          </div>
        )}
        <div>
          <p className="text-xs text-gray-400">Current Price</p>
          <p className="font-medium text-gray-900">{formatCurrency(status.current_price)}</p>
        </div>
        <div>
          <p className="text-xs text-gray-400">Model 5D Signal</p>
          {status.model_5d_signal ? <SignalBadge status={status.model_5d_signal as "BULLISH" | "BEARISH" | "NO_STRONG_SIGNAL"} size="sm" /> : <p className="text-gray-400">—</p>}
        </div>
        {rule.last_triggered_at && (
          <div>
            <p className="text-xs text-gray-400">Last Triggered</p>
            <p className="font-medium text-gray-900">{formatDateTime(rule.last_triggered_at)}</p>
          </div>
        )}
      </div>
    </div>
  );
}
