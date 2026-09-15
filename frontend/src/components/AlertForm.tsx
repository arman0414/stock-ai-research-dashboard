"use client";

import { useState } from "react";
import { ALERT_TYPES, type AlertType } from "@/lib/types";
import { ApiError, createAlert } from "@/lib/api";

export default function AlertForm({ onCreated, defaultTicker }: { onCreated: () => void; defaultTicker?: string }) {
  const [ticker, setTicker] = useState(defaultTicker ?? "");
  const [alertType, setAlertType] = useState<AlertType>("MY_TARGET_PRICE");
  const [threshold, setThreshold] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const needsThreshold = ALERT_TYPES.find((option) => option.value === alertType)?.needsThreshold ?? false;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (!ticker.trim()) {
      setError("Ticker is required.");
      return;
    }
    if (needsThreshold && !threshold) {
      setError("A price is required for this alert type.");
      return;
    }
    setSubmitting(true);
    try {
      await createAlert(ticker.trim().toUpperCase(), alertType, needsThreshold ? parseFloat(threshold) : null);
      setTicker(defaultTicker ?? "");
      setThreshold("");
      onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create alert.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-wrap items-end gap-2 rounded-xl border border-gray-200 bg-white p-4">
      <label className="text-xs font-medium text-gray-500">
        Ticker
        <input
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase())}
          placeholder="NVDA"
          className="mt-1 block w-24 rounded-md border border-gray-300 px-2 py-1.5 text-sm"
        />
      </label>
      <label className="text-xs font-medium text-gray-500">
        Alert Type
        <select
          value={alertType}
          onChange={(e) => setAlertType(e.target.value as AlertType)}
          className="mt-1 block rounded-md border border-gray-300 px-2 py-1.5 text-sm"
        >
          {ALERT_TYPES.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      {needsThreshold && (
        <label className="text-xs font-medium text-gray-500">
          Price
          <input
            value={threshold}
            onChange={(e) => setThreshold(e.target.value)}
            type="number"
            step="any"
            placeholder="240.00"
            className="mt-1 block w-28 rounded-md border border-gray-300 px-2 py-1.5 text-sm"
          />
        </label>
      )}
      <button type="submit" disabled={submitting} className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50">
        {submitting ? "Adding…" : "Add Alert"}
      </button>
      {error && (
        <p role="alert" className="w-full text-sm text-red-600">
          {error}
        </p>
      )}
    </form>
  );
}
