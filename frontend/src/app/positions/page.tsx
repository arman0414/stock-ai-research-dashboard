"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  buyShares,
  createPosition,
  deletePosition,
  deleteTransaction,
  getPortfolioSummary,
  listClosedPositions,
  listPositions,
  listTransactions,
  sellShares,
  updatePosition,
} from "@/lib/api";
import type { ClosedPosition, PortfolioSummary, Position, PositionInput, PositionTransaction, PositionUpdateInput, TradeInput } from "@/lib/types";
import { useQuotes } from "@/lib/useQuotes";
import PositionCard from "@/components/PositionCard";
import PositionForm from "@/components/PositionForm";
import PortfolioSummaryBar from "@/components/PortfolioSummaryBar";
import TradeModal from "@/components/TradeModal";
import TransactionHistory from "@/components/TransactionHistory";
import ClosedPositions from "@/components/ClosedPositions";
import { EmptyState, ErrorState, LoadingState } from "@/components/StatusStates";

const TABS = ["OVERVIEW", "OPEN POSITIONS", "HISTORY", "CLOSED"] as const;
type Tab = (typeof TABS)[number];

export default function PositionsPage() {
  const [tab, setTab] = useState<Tab>("OVERVIEW");
  const [positions, setPositions] = useState<Position[] | null>(null);
  const [transactions, setTransactions] = useState<PositionTransaction[]>([]);
  const [closed, setClosed] = useState<ClosedPosition[]>([]);
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Position | null>(null);
  const [trading, setTrading] = useState<{ mode: "BUY" | "SELL"; position: Position } | null>(null);

  const tickers = useMemo(() => [...new Set(positions?.map((p) => p.ticker) ?? [])], [positions]);
  const { quotes, refreshing: quotesRefreshing } = useQuotes(tickers);

  const loadVersion = useRef(0);
  const load = useCallback(async () => {
    const version = ++loadVersion.current;
    const failures: string[] = [];
    async function panel<T>(label: string, fetcher: () => Promise<T>, setter: (value: T) => void) {
      try {
        const result = await fetcher();
        if (version === loadVersion.current) setter(result);
      } catch (err) {
        failures.push(`${label}: ${err instanceof ApiError ? err.message : "Could not refresh."}`);
      }
    }
    await Promise.all([
      panel("Positions", listPositions, setPositions),
      panel("History", listTransactions, setTransactions),
      panel("Closed positions", listClosedPositions, setClosed),
      panel("Summary", getPortfolioSummary, setSummary),
    ]);
    if (version === loadVersion.current) setError(failures.length ? failures.join(" ") : null);
  }, []);

  function applyPosition(position: Position) {
    setPositions(rows => [...(rows ?? []).filter(row => row.id !== position.id), ...(position.is_open ? [position] : [])]
      .sort((a, b) => a.ticker.localeCompare(b.ticker)));
    setSummary(null);
  }

  useEffect(() => {
    void load();
  }, [load]);

  async function handleCreate(input: PositionInput) {
    applyPosition(await createPosition(input));
    setShowForm(false);
    await load();
  }

  async function handleUpdate(input: PositionUpdateInput) {
    if (!editing) return;
    applyPosition(await updatePosition(editing.id, input));
    setEditing(null);
    await load();
  }

  async function handleDelete(position: Position) {
    if (!confirm(`Hide ${position.ticker} from tracking? Your shares, notes and history are kept. Recording another buy resumes tracking the full holding.`)) return;
    try {
      await deletePosition(position.id);
      setPositions(rows => rows?.filter(row => row.id !== position.id) ?? []);
      setSummary(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not stop tracking.");
    }
  }

  async function handleTrade(input: TradeInput) {
    if (!trading) return;
    if (trading.mode === "BUY") {
      applyPosition(await buyShares(trading.position.ticker, input));
    } else {
      applyPosition(await sellShares(trading.position.ticker, input));
    }
    setTrading(null);
    await load();
  }

  async function handleTransactionDelete(id: number) {
    if (!confirm("Delete this transaction? Later sales and position cycles will be recalculated.")) return;
    await deleteTransaction(id);
    setSummary(null);
    await load();
  }

  const openPositions = positions ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-900">My Positions</h1>
        {!showForm && !editing && !trading && (
          <button onClick={() => setShowForm(true)} className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700">
            I Bought This Stock
          </button>
        )}
      </div>

      <nav className="flex gap-1 overflow-x-auto border-b border-gray-200" role="tablist">
        {TABS.map((option) => (
          <button
            key={option}
            role="tab"
            aria-selected={tab === option}
            onClick={() => setTab(option)}
            className={`shrink-0 px-3 py-2 text-xs font-medium uppercase tracking-wide ${
              tab === option ? "border-b-2 border-gray-900 text-gray-900" : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {option}
          </button>
        ))}
      </nav>

      {showForm && <PositionForm onSubmit={handleCreate} onCancel={() => setShowForm(false)} />}
      {editing && <PositionForm initial={editing} onSubmit={handleUpdate} onCancel={() => setEditing(null)} />}
      {trading && <TradeModal mode={trading.mode} position={trading.position} onSubmit={handleTrade} onCancel={() => setTrading(null)} />}

      {positions === null && !error && <LoadingState label="Loading positions…" />}
      {error && <ErrorState message={error} onRetry={load} />}

      {(tab === "OVERVIEW" || tab === "OPEN POSITIONS") && summary && <PortfolioSummaryBar summary={summary} />}

      {(tab === "OVERVIEW" || tab === "OPEN POSITIONS") && positions !== null && openPositions.length === 0 && (
        <EmptyState title="You haven't entered any positions yet." hint="Use “I Bought This Stock” to track a manual holding." />
      )}

      {(tab === "OVERVIEW" || tab === "OPEN POSITIONS") && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {openPositions.map((position) => (
            <PositionCard
              key={position.id}
              position={position}
              quote={quotes[position.ticker]}
              quoteRefreshing={quotesRefreshing}
              onEdit={() => setEditing(position)}
              onDelete={() => handleDelete(position)}
              onBuyMore={() => setTrading({ mode: "BUY", position })}
              onSell={() => setTrading({ mode: "SELL", position })}
            />
          ))}
        </div>
      )}

      {tab === "HISTORY" && <TransactionHistory transactions={transactions} onDelete={handleTransactionDelete} />}
      {tab === "CLOSED" && <ClosedPositions positions={closed} />}
    </div>
  );
}
