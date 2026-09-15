import type { HorizonPrediction } from "@/lib/types";
import { formatCurrency, horizonTradingDaysLabel } from "@/lib/format";
import SignalBadge from "./SignalBadge";

export default function CompactHorizonRow({ prediction }: { prediction: HorizonPrediction }) {
  const { classification, regression, horizon } = prediction;
  return (
    <div data-testid={`compact-horizon-${horizon}`} data-horizon={horizon} className="flex items-center justify-between rounded-lg bg-gray-50 px-3 py-2 text-sm">
      <div>
        <p className="font-medium text-gray-700">{horizonTradingDaysLabel(horizon)}</p>
        <p className="text-xs text-gray-400">
          Target {formatCurrency(regression.model_target_price, 0)} · Range {formatCurrency(regression.uncertainty_low, 0)}–{formatCurrency(regression.uncertainty_high, 0)}
        </p>
      </div>
      <SignalBadge status={classification.signal_status} size="sm" />
    </div>
  );
}
