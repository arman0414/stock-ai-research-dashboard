"use client";

import { useEffect, useState } from "react";
import type { HorizonPrediction, Position, QuoteResult } from "@/lib/types";
import { formatCurrency, formatDate, formatSignedCurrency, formatSignedPercent } from "@/lib/format";
import { getPrediction } from "@/lib/api";
import CurrentPrice from "./CurrentPrice";
import SignalBadge from "./SignalBadge";

export default function PositionCard({
  position,
  quote,
  quoteRefreshing,
  onEdit,
  onDelete,
  onBuyMore,
  onSell,
}: {
  position: Position;
  quote?: QuoteResult;
  quoteRefreshing?: boolean;
  onEdit: () => void;
  onDelete: () => void;
  onBuyMore?: () => void;
  onSell?: () => void;
}) {
  const [primaryPrediction, setPrimaryPrediction] = useState<HorizonPrediction | null>(null);
  const [modelUnavailable, setModelUnavailable] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getPrediction(position.ticker)
      .then((prediction) => {
        if (cancelled) return;
        setPrimaryPrediction(prediction.predictions[prediction.primary_research_horizon as "5d"] ?? null);
      })
      .catch(() => {
        if (!cancelled) setModelUnavailable(true);
      });
    return () => {
      cancelled = true;
    };
  }, [position.ticker]);

  // CURRENT PRICE for portfolio value/P&L comes from the fresh quote service
  // -- never from a prediction's frozen start price, and never by running
  // the ML model just to read a price.
  const currentPrice = quote?.price ?? null;
  const cost = position.total_cost_basis;
  const currentValue = currentPrice !== null ? position.shares * currentPrice : null;
  const profit = currentValue !== null ? currentValue - cost : null;
  const returnPct = currentValue !== null && cost > 0 ? (currentValue - cost) / cost : null;

  return (
    <div data-testid={`position-card-${position.ticker}`} className="rounded-xl border border-gray-200 bg-white p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h3 className="text-lg font-semibold text-gray-900">{position.ticker}</h3>
        <div className="flex flex-wrap gap-2">
          {onBuyMore && (
            <button onClick={onBuyMore} className="rounded-md border border-gray-300 px-2 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50">
              Buy More
            </button>
          )}
          {onSell && (
            <button onClick={onSell} className="rounded-md border border-gray-300 px-2 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50">
              Sell
            </button>
          )}
          <button onClick={onEdit} className="text-xs font-medium text-gray-500 hover:underline">
            Edit Details
          </button>
          <button onClick={onDelete} className="text-xs font-medium text-red-500 hover:underline">
            Remove
          </button>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <Metric label="Shares" value={position.shares.toString()} />
        <Metric label="Avg Cost" value={formatCurrency(position.average_cost)} />
        <div>
          <p className="text-xs text-gray-400">Current</p>
          <CurrentPrice quote={quote} size="sm" refreshing={quoteRefreshing} />
        </div>
        <Metric label="Cost Basis" value={formatCurrency(cost)} />
        <Metric label="Market Value" value={formatCurrency(currentValue)} />
        <Metric label="Unrealized P/L" value={formatSignedCurrency(profit)} valueClassName={profitColor(profit)} />
        <Metric label="Unrealized P/L %" value={formatSignedPercent(returnPct)} valueClassName={profitColor(profit)} />
        <Metric label="Purchased" value={formatDate(position.purchase_date)} />
        {position.realized_pl !== 0 && (
          <Metric label="Realized P/L" value={formatSignedCurrency(position.realized_pl)} valueClassName={profitColor(position.realized_pl)} />
        )}
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3 border-t border-gray-100 pt-3 text-sm">
        <div>
          <p className="text-xs text-gray-400">My Target (yours)</p>
          <p className="font-medium text-gray-900">{formatCurrency(position.my_target_price)}</p>
        </div>
        <div>
          <p className="text-xs text-gray-400">My Stop Loss (yours)</p>
          <p className="font-medium text-gray-900">{formatCurrency(position.stop_loss_price)}</p>
        </div>
      </div>

      <div className="mt-3 border-t border-gray-100 pt-3 text-sm">
        {modelUnavailable && <p className="text-xs text-gray-400">Model signal unavailable for this ticker.</p>}
        {primaryPrediction && (
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-gray-400">5D Model Signal (not your target)</p>
              <p className="mt-1">
                <SignalBadge status={primaryPrediction.classification.signal_status} size="sm" />
              </p>
            </div>
            <div className="text-right">
              <p className="text-xs text-gray-400">5D Model Target</p>
              <p className="font-medium text-gray-900">{formatCurrency(primaryPrediction.regression.model_target_price)}</p>
            </div>
          </div>
        )}
      </div>

      {position.notes && <p className="mt-3 rounded-md bg-gray-50 p-2 text-xs text-gray-600">{position.notes}</p>}
    </div>
  );
}

function profitColor(value: number | null): string {
  if (value === null) return "text-gray-900";
  if (value > 0) return "text-green-700";
  if (value < 0) return "text-red-700";
  return "text-gray-900";
}

function Metric({ label, value, valueClassName }: { label: string; value: string; valueClassName?: string }) {
  return (
    <div>
      <p className="text-xs text-gray-400">{label}</p>
      <p className={`font-medium ${valueClassName ?? "text-gray-900"}`}>{value}</p>
    </div>
  );
}
