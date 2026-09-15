import type { HorizonPrediction, MarketContext, SentimentSummary, StockStructure } from "@/lib/types";
import { getResearchStrength } from "@/lib/researchStrength";
import { formatCurrency, formatPercent } from "@/lib/format";
import SignalBadge from "./SignalBadge";
import ResearchStrengthBadge from "./ResearchStrengthBadge";

const POSITIVE = "text-green-700";
const NEGATIVE = "text-red-700";
const NEUTRAL = "text-gray-500";

function chartSetupLabel(structure: StockStructure | null): { text: string; className: string } {
  if (!structure) return { text: "Unavailable", className: NEUTRAL };
  if (structure.market_structure === "BULLISH") return { text: "Positive", className: POSITIVE };
  if (structure.market_structure === "BEARISH") return { text: "Negative", className: NEGATIVE };
  return { text: "Neutral", className: NEUTRAL };
}

function marketContextLabel(context: MarketContext): { text: string; className: string } {
  if (context.stock_vs_market === "OUTPERFORMING" || context.stock_vs_sector === "OUTPERFORMING") return { text: "Positive", className: POSITIVE };
  if (context.stock_vs_market === "UNDERPERFORMING" && context.stock_vs_sector === "UNDERPERFORMING") return { text: "Negative", className: NEGATIVE };
  return { text: "Neutral", className: NEUTRAL };
}

function newsSentimentLabel(sentiment: SentimentSummary | null): { text: string; className: string } {
  if (!sentiment || sentiment.articles_7d === 0) return { text: "Unavailable", className: NEUTRAL };
  if (sentiment.sentiment_direction === "POSITIVE") return { text: "Positive", className: POSITIVE };
  if (sentiment.sentiment_direction === "NEGATIVE") return { text: "Negative", className: NEGATIVE };
  return { text: "Neutral", className: NEUTRAL };
}

export default function ResearchSummaryPanel({
  prediction,
  marketContext,
  sentiment,
  structure,
}: {
  prediction: HorizonPrediction;
  marketContext: MarketContext;
  sentiment: SentimentSummary | null;
  structure: StockStructure | null;
}) {
  const strength = getResearchStrength(prediction);
  const chartSetup = chartSetupLabel(structure);
  const marketLabel = marketContextLabel(marketContext);
  const newsLabel = newsSentimentLabel(sentiment);

  return (
    <div data-testid="research-summary-panel" className="rounded-xl border border-blue-200 bg-blue-50/40 p-4">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-600">Model Research Summary</h2>

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <SignalBadge status={prediction.classification.signal_status} size="lg" />
        <ResearchStrengthBadge level={strength} size="lg" />
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-3">
        <Row label="Calibrated Probability" value={formatPercent(prediction.classification.calibrated_probability)} />
        <Row
          label="Historical Success"
          value={prediction.classification.historical_signal_accuracy !== null ? formatPercent(prediction.classification.historical_signal_accuracy) : "Insufficient evidence"}
        />
        <Row label="Similar Historical Signals" value={prediction.classification.historical_signal_samples?.toString() ?? "—"} />
        <Row label="Model Target" value={formatCurrency(prediction.regression.model_target_price)} />
        <Row label="Expected Range" value={`${formatCurrency(prediction.regression.uncertainty_low)} – ${formatCurrency(prediction.regression.uncertainty_high)}`} />
        <Row label="Chart Setup" value={chartSetup.text} valueClassName={chartSetup.className} />
        <Row label="Market Context" value={marketLabel.text} valueClassName={marketLabel.className} />
        <Row label="News Sentiment" value={newsLabel.text} valueClassName={newsLabel.className} />
      </dl>
    </div>
  );
}

function Row({ label, value, valueClassName }: { label: string; value: string; valueClassName?: string }) {
  return (
    <div>
      <dt className="text-xs text-gray-400">{label}</dt>
      <dd className={`font-medium ${valueClassName ?? "text-gray-900"}`}>{value}</dd>
    </div>
  );
}
