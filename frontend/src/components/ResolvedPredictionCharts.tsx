import type { PredictionHistoryRecord } from "@/lib/types";
import { formatCurrency, formatDate, formatPercentPoints } from "@/lib/format";

/** Below this, a chart would be more suggestive than informative, so we say
 * so rather than drawing a line through one or two points. */
const MIN_RESOLVED_FOR_CHART = 3;

interface Point {
  date: string;
  predicted: number;
  final: number;
  missPct: number;
}

/**
 * Predicted vs Final Price (and miss %) for records that have ACTUALLY
 * resolved. Pending predictions are never plotted -- no interpolation, no
 * placeholder points. Plain SVG on purpose: these are a handful of points,
 * and it keeps the page free of imperative chart lifecycles.
 */
export default function ResolvedPredictionCharts({ ticker, records }: { ticker: string; records: PredictionHistoryRecord[] }) {
  const points: Point[] = records
    .filter((r) => r.outcome_status === "RESOLVED" && r.actual_future_price !== null && r.absolute_prediction_difference_pct !== null)
    .sort((a, b) => (a.prediction_date < b.prediction_date ? -1 : 1))
    .map((r) => ({
      date: r.prediction_date,
      predicted: r.model_target_price,
      final: r.actual_future_price as number,
      missPct: r.absolute_prediction_difference_pct as number,
    }));

  if (points.length < MIN_RESOLVED_FOR_CHART) {
    return (
      <p data-testid="chart-not-enough-data" className="rounded-lg border border-dashed border-gray-300 bg-gray-50 px-3 py-4 text-center text-sm text-gray-500">
        Not enough completed predictions for chart yet.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <div data-testid="predicted-vs-final-chart" className="rounded-lg border border-gray-200 bg-white p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-500">{ticker} · Predicted vs Final Price</h4>
          <div className="flex items-center gap-3 text-[11px] text-gray-500">
            <Legend color="#2563eb" label="Predicted" />
            <Legend color="#16a34a" label="Final" />
          </div>
        </div>
        <LineChart
          points={points}
          series={[
            { key: "predicted", color: "#2563eb" },
            { key: "final", color: "#16a34a" },
          ]}
          formatValue={(value) => formatCurrency(value)}
        />
      </div>

      <div data-testid="miss-pct-chart" className="rounded-lg border border-gray-200 bg-white p-3">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-500">{ticker} · Prediction Miss %</h4>
        <LineChart points={points} series={[{ key: "missPct", color: "#d97706" }]} formatValue={(value) => formatPercentPoints(value, 1)} />
      </div>
    </div>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span aria-hidden className="inline-block h-0.5 w-3 rounded" style={{ backgroundColor: color }} />
      {label}
    </span>
  );
}

const WIDTH = 600;
const HEIGHT = 140;
const PADDING = { top: 10, right: 8, bottom: 20, left: 48 };

function LineChart({
  points,
  series,
  formatValue,
}: {
  points: Point[];
  series: { key: keyof Omit<Point, "date">; color: string }[];
  formatValue: (value: number) => string;
}) {
  const values = points.flatMap((point) => series.map((s) => point[s.key]));
  const min = Math.min(...values);
  const max = Math.max(...values);
  // A flat series would otherwise divide by zero; give it a little headroom
  // so the line sits in the middle instead of on an edge.
  const span = max - min || Math.abs(max) * 0.1 || 1;
  const plotWidth = WIDTH - PADDING.left - PADDING.right;
  const plotHeight = HEIGHT - PADDING.top - PADDING.bottom;

  const x = (index: number) => PADDING.left + (points.length === 1 ? plotWidth / 2 : (index / (points.length - 1)) * plotWidth);
  const y = (value: number) => PADDING.top + plotHeight - ((value - min) / span) * plotHeight;

  return (
    <svg role="img" aria-label="Resolved prediction trend" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="mt-2 h-36 w-full">
      <line x1={PADDING.left} y1={PADDING.top} x2={PADDING.left} y2={PADDING.top + plotHeight} stroke="#e5e7eb" strokeWidth={1} />
      <line x1={PADDING.left} y1={PADDING.top + plotHeight} x2={WIDTH - PADDING.right} y2={PADDING.top + plotHeight} stroke="#e5e7eb" strokeWidth={1} />

      <text x={4} y={PADDING.top + 4} className="fill-gray-400 text-[10px]">
        {formatValue(max)}
      </text>
      <text x={4} y={PADDING.top + plotHeight} className="fill-gray-400 text-[10px]">
        {formatValue(min)}
      </text>

      {series.map((s) => (
        <polyline
          key={String(s.key)}
          fill="none"
          stroke={s.color}
          strokeWidth={1.75}
          points={points.map((point, index) => `${x(index)},${y(point[s.key])}`).join(" ")}
        />
      ))}

      {series.map((s) =>
        points.map((point, index) => <circle key={`${String(s.key)}-${point.date}`} cx={x(index)} cy={y(point[s.key])} r={2.5} fill={s.color} />)
      )}

      <text x={PADDING.left} y={HEIGHT - 4} className="fill-gray-400 text-[10px]">
        {formatDate(points[0]!.date)}
      </text>
      <text x={WIDTH - PADDING.right} y={HEIGHT - 4} textAnchor="end" className="fill-gray-400 text-[10px]">
        {formatDate(points[points.length - 1]!.date)}
      </text>
    </svg>
  );
}
