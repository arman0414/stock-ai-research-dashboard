import type { HorizonPrediction } from "@/lib/types";
import { formatCurrency, formatSignedPercent, horizonTradingDaysLabel } from "@/lib/format";
import { directionArrowFromReturn } from "@/lib/priceDirection";
import SignalBadge from "./SignalBadge";

export default function CompactHorizonRow({ prediction }: { prediction: HorizonPrediction }) {
  const { classification, regression, horizon } = prediction;
  const arrow = directionArrowFromReturn(regression.predicted_return);
  return (
    <div data-testid={`compact-horizon-${horizon}`} data-horizon={horizon} className="flex items-center justify-between rounded-lg bg-gray-50 px-3 py-2 text-sm">
      <div>
        <p className="font-medium text-gray-700">{horizonTradingDaysLabel(horizon)}</p>
        <p className="text-gray-600">
          Predicted {formatCurrency(regression.model_target_price)} <span aria-hidden>{arrow}</span> {formatSignedPercent(regression.predicted_return)}
        </p>
        <p className="text-xs text-gray-400">
          Range {formatCurrency(regression.uncertainty_low)}–{formatCurrency(regression.uncertainty_high)}
        </p>
      </div>
      <SignalBadge status={classification.signal_status} size="sm" />
    </div>
  );
}
