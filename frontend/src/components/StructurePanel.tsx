import type { StockStructure } from "@/lib/types";
import { formatCurrency } from "@/lib/format";

const TREND_COLOR: Record<string, string> = { BULLISH: "text-green-700", BEARISH: "text-red-700", NEUTRAL: "text-gray-600" };
const BREAKOUT_LABEL: Record<string, string> = {
  BREAKOUT: "Breaking out above resistance",
  FAILED_BREAKOUT: "Failed breakout",
  BREAKDOWN: "Breaking down below support",
  APPROACHING_RESISTANCE: "Approaching resistance",
  NEAR_SUPPORT: "Near support",
  RANGE_BOUND: "Range bound",
};

export default function StructurePanel({ structure }: { structure: StockStructure | null }) {
  if (!structure) {
    return <p className="text-sm text-gray-400">Market structure is not available yet for this stock.</p>;
  }

  return (
    <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
      <Item label="Market Structure" value={structure.market_structure} className={TREND_COLOR[structure.market_structure]} />
      <Item label="Buyer Pressure" value={structure.buyer_pressure} />
      <Item label="Seller Pressure" value={structure.seller_pressure} />
      <Item label="Support" value={formatCurrency(structure.nearest_support)} />
      <Item label="Resistance" value={formatCurrency(structure.nearest_resistance)} />
      <Item label="Breakout Status" value={BREAKOUT_LABEL[structure.breakout_status] ?? structure.breakout_status} />
    </dl>
  );
}

function Item({ label, value, className }: { label: string; value: string; className?: string }) {
  return (
    <div>
      <dt className="text-xs text-gray-400">{label}</dt>
      <dd className={`font-medium ${className ?? "text-gray-900"}`}>{value}</dd>
    </div>
  );
}
