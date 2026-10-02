"use client";

import { useEffect, useMemo, useState } from "react";
import type { Position, TradeInput, SellPreview } from "@/lib/types";
import { formatCurrency, formatSignedCurrency, formatSignedPercentPoints } from "@/lib/format";

import { previewSell } from "@/lib/api";

type Mode = "BUY" | "SELL";

function nowLocalISO() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}T${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}:${String(now.getSeconds()).padStart(2, "0")}`;
}

/**
 * Buy More / Sell form with a live preview.
 *
 * The preview mirrors the backend's average-cost rules so the numbers shown
 * before confirming match what actually gets recorded, but the backend stays
 * authoritative -- nothing here is persisted as P/L.
 */
export default function TradeModal({
  mode,
  position,
  onSubmit,
  onCancel,
}: {
  mode: Mode;
  position: Position;
  onSubmit: (input: TradeInput) => Promise<void>;
  onCancel: () => void;
}) {
  const [quantity, setQuantity] = useState("");
  const [price, setPrice] = useState("");
  const [date, setDate] = useState(nowLocalISO());
  const [fees, setFees] = useState("");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const quantityNum = parseFloat(quantity);
  const priceNum = parseFloat(price);
  const feesNum = parseFloat(fees) || 0;
  const hasInputs = Number.isFinite(quantityNum) && quantityNum > 0 && Number.isFinite(priceNum) && priceNum > 0;

  const buyPreview = useMemo(() => {
    if (!hasInputs || mode !== "BUY") return null;
    const newQuantity = position.shares + quantityNum;
    const newCost = position.shares * position.average_cost + quantityNum * priceNum + feesNum;
    return { newQuantity, newAverageCost: newCost / newQuantity };
  }, [hasInputs, mode, position.shares, position.average_cost, quantityNum, priceNum, feesNum]);

  const transactionDate = date ? new Date(date).toISOString() : null;
  const previewKey = JSON.stringify([mode, position.ticker, quantityNum, priceNum, feesNum, transactionDate]);
  const [previewResult, setPreviewResult] = useState<{ key: string; value?: SellPreview; error?: string } | null>(null);
  useEffect(() => {
    if (!hasInputs || mode !== "SELL" || feesNum < 0) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      previewSell(position.ticker, { quantity: quantityNum, price_per_share: priceNum,
        fees: feesNum, transaction_date: transactionDate }).then(
        value => { if (!cancelled) setPreviewResult({ key: previewKey, value }); },
        err => { if (!cancelled) setPreviewResult({ key: previewKey, error: err instanceof Error ? err.message : "Could not preview sale." }); },
      );
    }, 150);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [hasInputs, mode, position.ticker, quantityNum, priceNum, feesNum, transactionDate, previewKey]);
  const currentPreview = previewResult?.key === previewKey ? previewResult : null;
  const sellPreview = currentPreview?.value;
  const oversell = mode === "SELL" && ((Number.isFinite(quantityNum) && quantityNum > position.shares) || sellPreview?.exceeds_position);
  const previewPending = mode === "SELL" && !sellPreview;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!hasInputs || oversell || previewPending || feesNum < 0) return;
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit({
        quantity: quantityNum,
        price_per_share: priceNum,
        transaction_date: transactionDate,
        fees: feesNum,
        notes: notes.trim() || null,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not record this transaction.");
      setSubmitting(false);
    }
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-semibold text-gray-900">
          {mode === "BUY" ? `Buy more ${position.ticker}` : `Sell ${position.ticker}`}
        </h3>
        <p className="text-xs text-gray-500">Shares owned: {position.shares}</p>
      </div>

      <form onSubmit={handleSubmit} className="mt-3 space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <Field label={mode === "BUY" ? "Quantity" : "Quantity to sell"}>
            <input
              type="number"
              step="any"
              min="0"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              aria-label={mode === "BUY" ? "Quantity" : "Quantity to sell"}
              className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm"
              required
            />
          </Field>
          <Field label={mode === "BUY" ? "Purchase price" : "Sale price"}>
            <input
              type="number"
              step="any"
              min="0"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              aria-label={mode === "BUY" ? "Purchase price" : "Sale price"}
              className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm"
              required
            />
          </Field>
          <Field label={mode === "BUY" ? "Purchase date" : "Sale date"}>
            <input
              type="datetime-local"
              step="1"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              aria-label={mode === "BUY" ? "Purchase date" : "Sale date"}
              className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm"
            />
          </Field>
          <Field label="Fee (optional)">
            <input
              type="number"
              step="any"
              min="0"
              value={fees}
              onChange={(e) => setFees(e.target.value)}
              aria-label="Fee"
              placeholder="0"
              className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm"
            />
          </Field>
        </div>
        <Field label="Notes (optional)">
          <input
            type="text"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            aria-label="Notes"
            className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm"
          />
        </Field>

        {oversell && (
          <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-700">
            {sellPreview?.error ?? `You currently own ${position.shares} shares of ${position.ticker}.`}
          </p>
        )}

        {buyPreview && (
          <dl className="grid grid-cols-3 gap-2 rounded-md bg-gray-50 p-3 text-xs">
            <PreviewItem label="Old avg cost" value={formatCurrency(position.average_cost)} />
            <PreviewItem label="New avg cost" value={formatCurrency(buyPreview.newAverageCost)} />
            <PreviewItem label="New quantity" value={String(buyPreview.newQuantity)} />
          </dl>
        )}

        {sellPreview && !oversell && (
          <dl className="grid grid-cols-2 gap-2 rounded-md bg-gray-50 p-3 text-xs sm:grid-cols-4">
            <PreviewItem label="Estimated proceeds" value={formatCurrency(sellPreview.sale_proceeds)} />
            <PreviewItem label="Cost basis" value={formatCurrency(sellPreview.cost_basis_total)} />
            <PreviewItem
              label="Estimated realized P/L"
              value={formatSignedCurrency(sellPreview.realized_profit_loss)}
              tone={sellPreview.realized_profit_loss >= 0 ? "positive" : "negative"}
            />
            <PreviewItem
              label="Estimated return"
              value={formatSignedPercentPoints(sellPreview.realized_profit_loss_pct, 2)}
              tone={sellPreview.realized_profit_loss >= 0 ? "positive" : "negative"}
            />
          </dl>
        )}

        {currentPreview?.error && <p role="alert" className="text-sm text-red-600">{currentPreview.error}</p>}
        {previewPending && hasInputs && !oversell && !currentPreview?.error && <p role="status" className="text-xs text-gray-500">Checking sale…</p>}

        {error && (
          <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-700">
            {error}
          </p>
        )}

        <div className="flex gap-2">
          <button
            type="submit"
            disabled={!hasInputs || Boolean(oversell) || previewPending || feesNum < 0 || submitting}
            className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting ? "Saving…" : mode === "BUY" ? "Confirm Purchase" : "Confirm Sale"}
          </button>
          <button type="button" onClick={onCancel} className="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50">
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-gray-600">{label}</span>
      {children}
    </label>
  );
}

function PreviewItem({ label, value, tone }: { label: string; value: string; tone?: "positive" | "negative" }) {
  const toneClass = tone === "positive" ? "text-green-700" : tone === "negative" ? "text-red-700" : "text-gray-900";
  return (
    <div>
      <dt className="text-[11px] uppercase tracking-wide text-gray-500">{label}</dt>
      <dd className={`mt-0.5 font-semibold ${toneClass}`}>{value}</dd>
    </div>
  );
}

