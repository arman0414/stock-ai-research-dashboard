import type { MarketContext } from "@/lib/types";

const TREND_COLOR: Record<string, string> = {
  BULLISH: "text-green-700",
  BEARISH: "text-red-700",
  NEUTRAL: "text-gray-600",
  OUTPERFORMING: "text-green-700",
  UNDERPERFORMING: "text-red-700",
};

export default function MarketContextPanel({ context }: { context: MarketContext }) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-900">Market Context</h3>
      <dl className="mt-2 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <Item label="SPY" value={context.spy_trend} />
        <Item label="QQQ" value={context.qqq_trend} />
        <Item label={context.sector_asset ? `Sector (${context.sector_asset})` : "Sector"} value={context.sector_trend} />
        <Item label="Stock vs Sector" value={context.stock_vs_sector} />
      </dl>
    </div>
  );
}

function Item({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-gray-400">{label}</dt>
      <dd className={`font-medium ${TREND_COLOR[value] ?? "text-gray-600"}`}>{value.replace("_", " ")}</dd>
    </div>
  );
}
