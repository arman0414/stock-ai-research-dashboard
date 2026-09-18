import type { PortfolioSummary } from "@/lib/types";
import { formatCurrency, formatSignedCurrency } from "@/lib/format";

/**
 * Portfolio totals. Realized and unrealized are shown side by side and never
 * combined except in the explicitly labelled Total P/L.
 */
export default function PortfolioSummaryBar({ summary }: { summary: PortfolioSummary }) {
  return (
    <dl className="grid grid-cols-2 gap-3 rounded-xl border border-gray-200 bg-white p-4 sm:grid-cols-5">
      <Item label="Portfolio Value" value={formatCurrency(summary.portfolio_value)} />
      <Item label="Open Cost Basis" value={formatCurrency(summary.open_cost_basis)} />
      <Item label="Unrealized P/L" value={formatSignedCurrency(summary.unrealized_pl)} tone={tone(summary.unrealized_pl)} />
      <Item label="Realized P/L" value={formatSignedCurrency(summary.realized_pl)} tone={tone(summary.realized_pl)} />
      <Item label="Total P/L" value={formatSignedCurrency(summary.total_pl)} tone={tone(summary.total_pl)} />
    </dl>
  );
}

function tone(value: number): string {
  if (value > 0) return "text-green-700";
  if (value < 0) return "text-red-700";
  return "text-gray-900";
}

function Item({ label, value, tone: toneClass }: { label: string; value: string; tone?: string }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-gray-500">{label}</dt>
      <dd className={`mt-1 text-lg font-semibold ${toneClass ?? "text-gray-900"}`}>{value}</dd>
    </div>
  );
}
