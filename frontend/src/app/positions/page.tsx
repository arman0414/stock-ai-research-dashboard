"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, createPosition, deletePosition, listPositions, updatePosition } from "@/lib/api";
import type { Position, PositionInput } from "@/lib/types";
import { useQuotes } from "@/lib/useQuotes";
import PositionCard from "@/components/PositionCard";
import PositionForm from "@/components/PositionForm";
import { EmptyState, ErrorState, LoadingState } from "@/components/StatusStates";

export default function PositionsPage() {
  const [positions, setPositions] = useState<Position[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Position | null>(null);
  const tickers = useMemo(() => [...new Set(positions?.map((p) => p.ticker) ?? [])], [positions]);
  const { quotes } = useQuotes(tickers);

  const load = useCallback(async () => {
    try {
      setPositions(await listPositions());
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load positions.");
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch-on-mount, setState happens after the await
    load();
  }, [load]);

  async function handleCreate(input: PositionInput) {
    await createPosition(input);
    setShowForm(false);
    load();
  }

  async function handleUpdate(input: PositionInput) {
    if (!editing) return;
    await updatePosition(editing.id, input);
    setEditing(null);
    load();
  }

  async function handleDelete(position: Position) {
    if (!confirm(`Close your ${position.ticker} position? This only removes it from tracking here.`)) return;
    await deletePosition(position.id);
    load();
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-900">My Positions</h1>
        {!showForm && !editing && (
          <button onClick={() => setShowForm(true)} className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700">
            I Bought This Stock
          </button>
        )}
      </div>

      {showForm && <PositionForm onSubmit={handleCreate} onCancel={() => setShowForm(false)} />}
      {editing && <PositionForm initial={editing} onSubmit={handleUpdate} onCancel={() => setEditing(null)} />}

      {positions === null && !error && <LoadingState label="Loading positions…" />}
      {error && <ErrorState message={error} onRetry={load} />}
      {positions !== null && positions.length === 0 && (
        <EmptyState title="You haven't entered any positions yet." hint="Use “I Bought This Stock” to track a manual holding." />
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {positions?.map((position) => (
          <PositionCard key={position.id} position={position} quote={quotes[position.ticker]} onEdit={() => setEditing(position)} onDelete={() => handleDelete(position)} />
        ))}
      </div>
    </div>
  );
}
