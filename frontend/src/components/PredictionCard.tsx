import type { HorizonPrediction } from "@/lib/types";
import { formatCurrency, formatPercent, formatSignedPercent, horizonLabel } from "@/lib/format";
import { getResearchStrength } from "@/lib/researchStrength";
import SignalBadge from "./SignalBadge";
import ResearchStrengthBadge from "./ResearchStrengthBadge";
import AdvancedDetails from "./AdvancedDetails";

const BEARISH_TOOLTIP = "Bearish signal does not currently meet historical validation requirements.";

export default function PredictionCard({ prediction, emphasized = false }: { prediction: HorizonPrediction; emphasized?: boolean }) {
  const { classification, regression, model, horizon } = prediction;
  const isBearishSuppressed = classification.direction === "DOWN" && classification.signal_status === "NO_STRONG_SIGNAL";
  const strength = getResearchStrength(prediction);

  return (
    <div
      data-testid={`prediction-card-${prediction.horizon}`}
      className={`rounded-xl border p-4 ${emphasized ? "border-blue-300 bg-blue-50/40 shadow-sm" : "border-gray-200 bg-white"}`}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-500">{horizonLabel(prediction.horizon)}</h3>
          {model.is_primary_research_horizon && (
            <span className="rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-blue-700">Primary</span>
          )}
        </div>
        <SignalBadge status={classification.signal_status} />
      </div>

      <div className="mt-2">
        <ResearchStrengthBadge level={strength} size={emphasized ? "md" : "sm"} />
      </div>

      {horizon === "15d" && <p className="mt-1.5 text-xs text-gray-400">Lower historical reliability than 5D.</p>}

      {isBearishSuppressed && (
        <p data-testid="bearish-tooltip" className="mt-1 text-xs text-gray-400" title={BEARISH_TOOLTIP}>
          {BEARISH_TOOLTIP}
        </p>
      )}

      {classification.signal_status === "NO_STRONG_SIGNAL" && !isBearishSuppressed && (
        <p className="mt-1 text-xs text-gray-400">The current setup does not meet the model&apos;s validated confidence requirements.</p>
      )}

      <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
        <Metric label="Model confidence" value={formatPercent(classification.calibrated_probability)} />
        <Metric label="Predicted return" value={formatSignedPercent(regression.predicted_return)} />
        <Metric label="Model Target" value={formatCurrency(regression.model_target_price)} />
        <Metric
          label="Historical 80% Range"
          value={`${formatCurrency(regression.uncertainty_low)} – ${formatCurrency(regression.uncertainty_high)}`}
        />
      </div>

      <div className="mt-3 border-t border-gray-100 pt-3 text-sm">
        {classification.historical_signal_accuracy !== null ? (
          <p className="text-gray-600">
            Historical accuracy: <span className="font-medium text-gray-900">{formatPercent(classification.historical_signal_accuracy)}</span>{" "}
            <span className="text-gray-400">· based on {classification.historical_signal_samples} comparable signals</span>
          </p>
        ) : (
          <p className="text-gray-400">Insufficient historical evidence</p>
        )}
      </div>

      <AdvancedDetails prediction={prediction} />
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-gray-400">{label}</p>
      <p className="font-medium text-gray-900">{value}</p>
    </div>
  );
}
