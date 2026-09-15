import type { HorizonPrediction } from "@/lib/types";
import { formatCurrency, formatPercent, horizonShortBadge, horizonTradingDaysLabel, horizonTradingDaysLabelUpper, tradingDaysTooltip } from "@/lib/format";
import { getResearchStrength } from "@/lib/researchStrength";
import { explainNoStrongSignal } from "@/lib/signalExplanation";
import SignalBadge from "./SignalBadge";
import ResearchStrengthBadge from "./ResearchStrengthBadge";
import InfoTooltip from "./InfoTooltip";
import AdvancedDetails from "./AdvancedDetails";

export default function PredictionCard({ prediction, emphasized = false }: { prediction: HorizonPrediction; emphasized?: boolean }) {
  const { classification, regression, model, horizon } = prediction;
  const strength = getResearchStrength(prediction);
  const whyExplanation = explainNoStrongSignal(prediction);
  const horizonWords = horizonTradingDaysLabelUpper(horizon);

  return (
    <div
      data-testid={`prediction-card-${horizon}`}
      data-horizon={horizon}
      className={`rounded-xl border p-4 ${emphasized ? "border-blue-300 bg-blue-50/40 shadow-sm" : "border-gray-200 bg-white"}`}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] font-semibold text-gray-500">{horizonShortBadge(horizon)}</span>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-700">{horizonWords}</h3>
          <InfoTooltip text={tradingDaysTooltip(horizon)} />
          {model.is_primary_research_horizon && (
            <span className="rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-blue-700">Primary</span>
          )}
        </div>
      </div>

      <div className="mt-2">
        <SignalBadge status={classification.signal_status} size="lg" />
      </div>

      <p className="mt-2 text-xs text-gray-400">Current Price: {formatCurrency(prediction.current_price)}</p>

      <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
        <Metric label="Model Lean" value={classification.direction} />
        <div>
          <p className="text-xs text-gray-400">Model Confidence</p>
          <div className="mt-0.5 flex items-center gap-2">
            <p className="font-medium text-gray-900">{formatPercent(classification.calibrated_probability)}</p>
            {/* Only shown for a validated signal -- when signal_status is
                already NO_STRONG_SIGNAL, this badge would say the exact same
                thing as the SignalBadge above it, duplicating "no strong
                signal" a second time in the same card. */}
            {classification.signal_status !== "NO_STRONG_SIGNAL" && <ResearchStrengthBadge level={strength} size="sm" />}
          </div>
        </div>
      </div>

      {whyExplanation && (
        <p data-testid="no-strong-signal-reason" className="mt-3 rounded-md bg-gray-50 p-2.5 text-xs text-gray-600">
          <span className="font-semibold text-gray-500">Why? </span>
          {whyExplanation}
        </p>
      )}

      <div className="mt-3 border-t border-gray-100 pt-3 text-sm">
        {classification.historical_signal_accuracy !== null ? (
          <div className="grid grid-cols-2 gap-3">
            <Metric label="Historical Success of Similar Signals" value={formatPercent(classification.historical_signal_accuracy)} />
            <Metric label="Historical Examples" value={String(classification.historical_signal_samples)} />
          </div>
        ) : (
          <Metric label="Historical Reliability" value="Not enough validated examples yet" />
        )}
      </div>

      <div className="mt-3 border-t border-gray-100 pt-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">Model Price Estimate — {horizonWords}</p>
        <div className="mt-2 grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
          <Metric label={`Model Estimate in ${horizonTradingDaysLabel(horizon)}`} value={formatCurrency(regression.model_target_price)} />
          <div>
            <p className="flex items-center text-xs text-gray-400">
              Historical 80% Error Range
              <InfoTooltip text="This range reflects the model's historical prediction error. It is an uncertainty range, not a guaranteed trading range." />
            </p>
            <p className="mt-0.5 font-medium text-gray-900">
              {formatCurrency(regression.uncertainty_low)} – {formatCurrency(regression.uncertainty_high)}
            </p>
          </div>
        </div>
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
