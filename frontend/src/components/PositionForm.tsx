"use client";

import { useState } from "react";
import type { Position, PositionInput } from "@/lib/types";
import { ApiError } from "@/lib/api";

interface PositionFormProps {
  initial?: Position;
  onSubmit: (input: PositionInput) => Promise<void>;
  onCancel: () => void;
}

export default function PositionForm({ initial, onSubmit, onCancel }: PositionFormProps) {
  const [ticker, setTicker] = useState(initial?.ticker ?? "");
  const [shares, setShares] = useState(initial?.shares?.toString() ?? "");
  const [purchasePrice, setPurchasePrice] = useState(initial?.purchase_price?.toString() ?? "");
  const [purchaseDate, setPurchaseDate] = useState(initial?.purchase_date ?? new Date().toISOString().slice(0, 10));
  const [myTarget, setMyTarget] = useState(initial?.my_target_price?.toString() ?? "");
  const [stopLoss, setStopLoss] = useState(initial?.stop_loss_price?.toString() ?? "");
  const [notes, setNotes] = useState(initial?.notes ?? "");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (!ticker.trim() || !shares || !purchasePrice || !purchaseDate) {
      setError("Ticker, shares, purchase price, and purchase date are required.");
      return;
    }
    setSubmitting(true);
    try {
      await onSubmit({
        ticker: ticker.trim().toUpperCase(),
        shares: parseFloat(shares),
        purchase_price: parseFloat(purchasePrice),
        purchase_date: purchaseDate,
        my_target_price: myTarget ? parseFloat(myTarget) : null,
        stop_loss_price: stopLoss ? parseFloat(stopLoss) : null,
        notes: notes || null,
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save position.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3 rounded-xl border border-gray-200 bg-white p-4">
      <h3 className="text-sm font-semibold text-gray-900">{initial ? "Edit Position" : "I Bought This Stock"}</h3>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Ticker">
          <input
            value={ticker}
            onChange={(e) => setTicker(e.target.value.toUpperCase())}
            disabled={!!initial}
            className="input"
            placeholder="NVDA"
          />
        </Field>
        <Field label="Shares">
          <input value={shares} onChange={(e) => setShares(e.target.value)} type="number" step="any" className="input" placeholder="20" />
        </Field>
        <Field label="Purchase Price">
          <input value={purchasePrice} onChange={(e) => setPurchasePrice(e.target.value)} type="number" step="any" className="input" placeholder="190.00" />
        </Field>
        <Field label="Purchase Date">
          <input value={purchaseDate} onChange={(e) => setPurchaseDate(e.target.value)} type="date" className="input" />
        </Field>
        <Field label="My Target Price (optional)">
          <input value={myTarget} onChange={(e) => setMyTarget(e.target.value)} type="number" step="any" className="input" placeholder="240.00" />
        </Field>
        <Field label="Stop Loss (optional)">
          <input value={stopLoss} onChange={(e) => setStopLoss(e.target.value)} type="number" step="any" className="input" placeholder="180.00" />
        </Field>
      </div>
      <Field label="Notes (optional)">
        <textarea value={notes} onChange={(e) => setNotes(e.target.value)} className="input" rows={2} />
      </Field>

      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}

      <div className="flex justify-end gap-2">
        <button type="button" onClick={onCancel} className="rounded-md border border-gray-200 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50">
          Cancel
        </button>
        <button type="submit" disabled={submitting} className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50">
          {submitting ? "Saving…" : "Save Position"}
        </button>
      </div>

      <style jsx>{`
        .input {
          width: 100%;
          border-radius: 0.375rem;
          border: 1px solid #d1d5db;
          padding: 0.375rem 0.625rem;
          font-size: 0.875rem;
        }
        .input:focus {
          outline: none;
          border-color: #60a5fa;
        }
      `}</style>
    </form>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block text-xs font-medium text-gray-500">
      {label}
      <div className="mt-1">{children}</div>
    </label>
  );
}
