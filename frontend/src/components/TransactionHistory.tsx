"use client";

import { useMemo, useState } from "react";
import type { PositionTransaction } from "@/lib/types";
import { formatCurrency, formatDate, formatSignedCurrency, formatSignedPercentPoints } from "@/lib/format";
import { EmptyState } from "./StatusStates";

type TypeFilter = "ALL" | "BUY" | "SELL";

export default function TransactionHistory({ transactions, onDelete }: { transactions: PositionTransaction[]; onDelete?: (id: number) => Promise<void> }) {
  const [deleting, setDeleting] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  async function remove(id: number) {
    setDeleting(id);
    setError(null);
    try { await onDelete?.(id); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not delete transaction."); }
    finally { setDeleting(null); }
  }
  const [typeFilter, setTypeFilter] = useState<TypeFilter>("ALL");
  const [tickerFilter, setTickerFilter] = useState("ALL");

  const tickers = useMemo(() => [...new Set(transactions.map((t) => t.ticker))].sort(), [transactions]);

  const visible = useMemo(
    () =>
      transactions.filter(
        (t) => (typeFilter === "ALL" || t.transaction_type === typeFilter) && (tickerFilter === "ALL" || t.ticker === tickerFilter),
      ),
    [transactions, typeFilter, tickerFilter],
  );

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex gap-1" role="group" aria-label="Filter by type">
          {(["ALL", "BUY", "SELL"] as TypeFilter[]).map((option) => (
            <button
              key={option}
              onClick={() => setTypeFilter(option)}
              aria-pressed={typeFilter === option}
              className={`rounded-md px-2.5 py-1 text-xs font-medium ${
                typeFilter === option ? "bg-gray-900 text-white" : "border border-gray-300 text-gray-700 hover:bg-gray-50"
              }`}
            >
              {option === "ALL" ? "All" : option === "BUY" ? "Buys" : "Sells"}
            </button>
          ))}
        </div>
        <label className="text-xs text-gray-600">
          <span className="sr-only">Filter by stock</span>
          <select
            value={tickerFilter}
            onChange={(e) => setTickerFilter(e.target.value)}
            aria-label="Filter by stock"
            className="rounded-md border border-gray-300 px-2 py-1 text-xs"
          >
            <option value="ALL">All stocks</option>
            {tickers.map((ticker) => (
              <option key={ticker} value={ticker}>
                {ticker}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && <p role="alert" className="mt-3 text-sm text-red-600">{error}</p>}
      {visible.length === 0 ? (
        <div className="mt-3">
          <EmptyState title="No transactions yet." hint="Buying or selling a position records it here." />
        </div>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-xs uppercase tracking-wide text-gray-500">
                <th scope="col" className="py-2 pr-3 font-medium">Date</th>
                <th scope="col" className="py-2 pr-3 font-medium">Ticker</th>
                <th scope="col" className="py-2 pr-3 font-medium">Type</th>
                <th scope="col" className="py-2 pr-3 font-medium">Quantity</th>
                <th scope="col" className="py-2 pr-3 font-medium">Price</th>
                <th scope="col" className="py-2 pr-3 font-medium">Fees</th>
                <th scope="col" className="py-2 pr-3 font-medium">Realized P/L</th>
                <th scope="col" className="py-2 font-medium">Notes</th>
                {onDelete && <th scope="col" className="py-2 font-medium">Correction</th>}
              </tr>
            </thead>
            <tbody>
              {visible.map((entry) => (
                <tr key={entry.id} data-testid={`transaction-${entry.id}`} className="border-b border-gray-100">
                  <td className="py-2 pr-3 text-gray-600">{entry.transaction_date ? formatDate(entry.transaction_date) : "Unknown"}</td>
                  <td className="py-2 pr-3 font-medium text-gray-900">{entry.ticker}</td>
                  <td className="py-2 pr-3">
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${entry.transaction_type === "BUY" ? "bg-gray-100 text-gray-700" : "bg-blue-50 text-blue-700"}`}>
                      {entry.transaction_type}
                    </span>
                  </td>
                  <td className="py-2 pr-3 text-gray-900">{entry.quantity}</td>
                  <td className="py-2 pr-3 text-gray-900">{formatCurrency(entry.price_per_share)}</td>
                  <td className="py-2 pr-3 text-gray-600">{formatCurrency(entry.fees)}</td>
                  <td className="py-2 pr-3">
                    {entry.realized_profit_loss === null ? (
                      <span className="text-gray-400">—</span>
                    ) : (
                      <span className={entry.realized_profit_loss >= 0 ? "font-medium text-green-700" : "font-medium text-red-700"}>
                        {formatSignedCurrency(entry.realized_profit_loss)}
                        {entry.realized_profit_loss_pct !== null && ` (${formatSignedPercentPoints(entry.realized_profit_loss_pct, 2)})`}
                      </span>
                    )}
                  </td>
                  <td className="py-2 text-xs text-gray-500">{entry.notes ?? "—"}</td>
                  {onDelete && <td className="py-2 pl-3"><button disabled={deleting !== null}
                    aria-label={`Delete transaction ${entry.id}`} onClick={() => remove(entry.id)}
                    className="text-xs text-red-600 disabled:opacity-50">{deleting === entry.id ? "Deleting…" : "Delete"}</button></td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

