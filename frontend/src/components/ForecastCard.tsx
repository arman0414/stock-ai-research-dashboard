import Link from "next/link";
import type { Horizon, PredictionHistoryRecord, QuoteResult, SentimentSummary, StockStructure } from "@/lib/types";
import { formatCurrency, formatDate, formatSignedCurrency, formatSignedPercent, horizonDayCount } from "@/lib/format";
import CurrentPrice from "./CurrentPrice";
import SignalBadge from "./SignalBadge";
import { EmptyState } from "./StatusStates";

const SENTIMENT_TEXT: Record<string, string> = { POSITIVE: "Positive", NEGATIVE: "Negative", NEUTRAL: "Neutral" };

export default function ForecastCard({
  ticker,
  horizon,
  record,
  structure,
  sentiment,
  quote,
}: {
  ticker: string;
  horizon: Horizon;
  record: PredictionHistoryRecord | null;
  structure: StockStructure | null;
  sentiment: SentimentSummary | null;
  quote: QuoteResult | undefined;
}) {
  const days = horizonDayCount(horizon);

  if (!record) {
    return (
      <div data-testid={`forecast-card-${ticker}`} className="rounded-xl border border-gray-200 bg-white p-4">
        <h3 className="text-lg font-semibold text-gray-900">{ticker}</h3>
        <div className="mt-2">
          <EmptyState title={`No current ${days}-day forecast available.`} />
        </div>
        <Link href={`/stocks/${ticker}`} className="mt-3 block w-full rounded-md border border-gray-300 py-1.5 text-center text-sm font-medium text-gray-700 hover:bg-gray-50">
          Open {ticker}
        </Link>
      </div>
    );
  }

  const modelExpectedMove = record.model_target_price - record.current_price;
  const distanceFromCurrent = quote?.price != null ? record.model_target_price - quote.price : null;
  const distanceFromCurrentPct = quote?.price ? distanceFromCurrent! / quote.price : null;

  return (
    <div data-testid={`forecast-card-${ticker}`} className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between">
        <Link href={`/stocks/${ticker}`} className="text-lg font-semibold text-gray-900 hover:underline">
          {ticker}
        </Link>
      </div>

      <div className="mt-2">
        <p className="text-xs text-gray-400">Current Price</p>
        <CurrentPrice quote={quote} />
      </div>

      <p className="mt-2 text-xs text-gray-400">
        Prediction Based On: <span className="text-gray-600">{formatDate(record.prediction_date)} close at {formatCurrency(record.current_price)}</span>
      </p>

      <div className="mt-3 rounded-lg bg-gray-50 p-3">
        <p className="text-xs text-gray-400">{days}-Day Predicted Price</p>
        <p data-testid="forecast-predicted-price" className="text-2xl font-bold text-gray-900">
          {formatCurrency(record.model_target_price)}
        </p>
        <p className="mt-1 text-sm text-gray-500">
          Model Expected Move: <span className="font-medium text-gray-700">{formatSignedCurrency(modelExpectedMove)}</span> ({formatSignedPercent(record.predicted_return)})
        </p>
        {distanceFromCurrent !== null && (
          <p className="mt-0.5 text-xs text-gray-400">
            Distance From Current: <span className="font-medium text-gray-600">{formatSignedCurrency(distanceFromCurrent)}</span> ({formatSignedPercent(distanceFromCurrentPct)})
          </p>
        )}
      </div>

      <div className="mt-3 flex items-center justify-between border-t border-gray-100 pt-3">
        <span className="text-xs font-semibold uppercase tracking-wide text-gray-400">Model View</span>
        <SignalBadge status={record.signal_status} />
      </div>
      <p className="mt-1 text-xs text-gray-400">Model Confidence: {(record.calibrated_probability * 100).toFixed(0)}%</p>

      <div className="mt-3 border-t border-gray-100 pt-3 text-sm">
        <p className="text-xs text-gray-400">Historical Error Range</p>
        <p className="font-medium text-gray-900">
          {formatCurrency(record.uncertainty_low)} – {formatCurrency(record.uncertainty_high)}
        </p>
      </div>

      {structure && (
        <div className="mt-3 grid grid-cols-2 gap-3 border-t border-gray-100 pt-3 text-sm">
          <div>
            <p className="text-xs text-gray-400">Support</p>
            <p className="font-medium text-gray-900">{formatCurrency(structure.nearest_support)}</p>
          </div>
          <div>
            <p className="text-xs text-gray-400">Resistance</p>
            <p className="font-medium text-gray-900">{formatCurrency(structure.nearest_resistance)}</p>
          </div>
        </div>
      )}

      <div className="mt-3 border-t border-gray-100 pt-3 text-sm">
        <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">News Mood</p>
        {sentiment && sentiment.articles_7d > 0 ? (
          <>
            <p className="font-medium text-gray-900">{SENTIMENT_TEXT[sentiment.sentiment_direction] ?? sentiment.sentiment_direction}</p>
            <p className="text-xs text-gray-400">
              {sentiment.positive} of {sentiment.articles_7d} recent articles positive
            </p>
          </>
        ) : (
          <p className="text-xs text-gray-400">No recent news.</p>
        )}
      </div>

      <Link href={`/stocks/${ticker}`} className="mt-3 block w-full rounded-md border border-gray-300 py-1.5 text-center text-sm font-medium text-gray-700 hover:bg-gray-50">
        Open {ticker}
      </Link>
    </div>
  );
}
