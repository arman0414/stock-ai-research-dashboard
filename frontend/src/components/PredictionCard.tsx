import type { HorizonPrediction } from "@/lib/types";
import { formatCurrency, formatPercent, formatSignedCurrency, formatSignedPercent, horizonShortBadge, horizonTradingDaysLabel, horizonTradingDaysLabelUpper, tradingDaysTooltip } from "@/lib/format";
import { directionArrowFromReturn } from "@/lib/priceDirection";
import { getResearchStrength } from "@/lib/researchStrength";
import { explainNoStrongSignal } from "@/lib/signalExplanation";
import SignalBadge from "./SignalBadge";
import ResearchStrengthBadge from "./ResearchStrengthBadge";
import InfoTooltip from "./InfoTooltip";
import AdvancedDetails from "./AdvancedDetails";

const PREDICTED_PRICE_TOOLTIP =
  "The model's estimated CLOSING price at the end of this horizon -- not the highest price reached, not an average, and not a price at some random point in between.";

export default function PredictionCard({ prediction, emphasized = false }: { prediction: HorizonPrediction; emphasized?: boolean }) {
  const { classification, regression, model, horizon, current_price: currentPrice } = prediction;
  const strength = getResearchStrength(prediction);
  const whyExplanation = explainNoStrongSignal(prediction);
  const horizonWords = horizonTradingDaysLabelUpper(horizon);
  const expectedChange = regression.model_target_price - currentPrice;
  const arrow = directionArrowFromReturn(regression.predicted_return);

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

      {/* Predicted price is the most prominent number on the card. */}
      <div className="mt-3 rounded-lg bg-white/60 p-3">
        <div className="flex items-baseline justify-between gap-3">
          <div>
            <p className="flex items-center gap-1 text-xs text-gray-400">
              Prediction Start Price
              <InfoTooltip text="The price when this prediction was made -- frozen, and never updated by a fresh live quote. The Current Price shown elsewhere on this page reflects today's latest price." />
            </p>
            <p className="text-lg font-medium text-gray-500">{formatCurrency(currentPrice)}</p>
          </div>
          <div className="text-right">
            <p className="flex items-center justify-end gap-1 text-xs text-gray-400">
              Predicted Closing Price
              <InfoTooltip text={PREDICTED_PRICE_TOOLTIP} />
            </p>
            <p data-testid="predicted-price" className="text-3xl font-bold text-gray-900">
              {formatCurrency(regression.model_target_price)} <span aria-hidden className="align-middle text-2xl text-gray-400">{arrow}</span>
            </p>
          </div>
        </div>
        <p className="mt-1 text-right text-sm text-gray-500">
          Expected Change: <span className="font-medium text-gray-700">{formatSignedCurrency(expectedChange)}</span> (
          {formatSignedPercent(regression.predicted_return)})
        </p>
      </div>

      <div className="mt-3">
        <p className="flex items-center text-xs text-gray-400">
          Historical 80% Error Range
          <InfoTooltip text="This range reflects the model's historical prediction error. It is an uncertainty range, not a guaranteed trading range." />
        </p>
        <p className="mt-0.5 font-medium text-gray-900">
          {formatCurrency(regression.uncertainty_low)} – {formatCurrency(regression.uncertainty_high)}
        </p>
      </div>

      <div className="mt-3 flex items-center justify-between border-t border-gray-100 pt-3">
        <span className="text-xs font-semibold uppercase tracking-wide text-gray-400">Validated Signal</span>
        <SignalBadge status={classification.signal_status} />
      </div>

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

      <p className="mt-2 text-[11px] text-gray-400">Model Estimate in {horizonTradingDaysLabel(horizon)}, as of the latest available market data.</p>

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
