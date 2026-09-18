import type { ClosedPosition } from "@/lib/types";
import { formatCurrency, formatDate, formatSignedCurrency, formatSignedPercentPoints } from "@/lib/format";
import { EmptyState } from "./StatusStates";

/**
 * Completed position cycles. A ticker only appears here once its quantity has
 * returned to zero -- a partially sold holding stays under Open Positions even
 * though it already has realized P/L.
 */
export default function ClosedPositions({ positions }: { positions: ClosedPosition[] }) {
  if (positions.length === 0) {
    return <EmptyState title="No closed positions yet." hint="A position appears here once you've sold all of its shares." />;
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      {positions.map((row) => (
        <div key={`${row.ticker}-${row.cycle_index}`} data-testid={`closed-position-${row.ticker}`} className="rounded-xl border border-gray-200 bg-white p-4">
          <div className="flex items-start justify-between">
            <h3 className="text-lg font-semibold text-gray-900">{row.ticker}</h3>
            <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-semibold uppercase text-gray-600">Closed</span>
          </div>

          <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
            <Item label="Shares Sold" value={String(row.total_shares_sold)} />
            <Item label="Total Cost Basis" value={formatCurrency(row.total_cost_basis)} />
            <Item label="Total Proceeds" value={formatCurrency(row.total_proceeds)} />
            <Item
              label="Realized P/L"
              value={`${formatSignedCurrency(row.realized_profit_loss)} (${formatSignedPercentPoints(row.return_pct, 2)})`}
              tone={row.realized_profit_loss >= 0 ? "text-green-700" : "text-red-700"}
            />
            <Item label="First Buy" value={row.first_buy_date ? formatDate(row.first_buy_date) : "Unknown"} />
            <Item label="Closed" value={row.final_sell_date ? formatDate(row.final_sell_date) : "Unknown"} />
          </dl>
        </div>
      ))}
    </div>
  );
}

function Item({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div>
      <dt className="text-xs text-gray-400">{label}</dt>
      <dd className={`font-medium ${tone ?? "text-gray-900"}`}>{value}</dd>
    </div>
  );
}
