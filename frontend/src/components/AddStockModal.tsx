"use client";

import { useState } from "react";
import { addStock, ApiError } from "@/lib/api";

export default function AddStockModal({ open, onClose, onAdded }: { open: boolean; onClose: () => void; onAdded: () => void }) {
  const [ticker, setTicker] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!ticker.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await addStock(ticker);
      setTicker("");
      onAdded();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not add stock. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" role="dialog" aria-modal="true">
      <div className="w-full max-w-sm rounded-xl bg-white p-5 shadow-lg">
        <h2 className="text-lg font-semibold text-gray-900">Add Stock</h2>
        <p className="mt-1 text-sm text-gray-500">Enter a ticker symbol, e.g. AAPL.</p>
        <form onSubmit={handleSubmit} className="mt-4">
          <input
            autoFocus
            value={ticker}
            onChange={(event) => setTicker(event.target.value.toUpperCase())}
            placeholder="NVDA"
            aria-label="Ticker symbol"
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm uppercase focus:border-blue-400 focus:outline-none"
          />
          {error && (
            <p role="alert" className="mt-2 text-sm text-red-600">
              {error}
            </p>
          )}
          <div className="mt-4 flex justify-end gap-2">
            <button type="button" onClick={onClose} className="rounded-md border border-gray-200 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50">
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting || !ticker.trim()}
              className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {submitting ? "Adding…" : "Add Stock"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
