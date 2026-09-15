"use client";

import { useState } from "react";
import { getStockAnalysis, refreshStock, ApiError } from "@/lib/api";
import type { StockAnalysis } from "@/lib/types";

const STEPS = ["Updating stock data…", "Analyzing chart structure…", "Running prediction model…", "Analysis complete."];

export default function RunAnalysisButton({ ticker, onComplete }: { ticker: string; onComplete: (analysis: StockAnalysis) => void }) {
  const [stepIndex, setStepIndex] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const running = stepIndex !== null && stepIndex < STEPS.length - 1;

  async function run() {
    setError(null);
    setStepIndex(0);
    try {
      await refreshStock(ticker);
      setStepIndex(1);
      // Structure + prediction both happen server-side inside /analysis;
      // we just narrate the two stages while that single call is in flight.
      setStepIndex(2);
      const analysis = await getStockAnalysis(ticker, true);
      setStepIndex(3);
      onComplete(analysis);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Analysis failed. Existing data is still shown.");
      setStepIndex(null);
    }
  }

  return (
    <div>
      <button
        onClick={run}
        disabled={running}
        className="rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-60"
      >
        {running ? "Running…" : "Run New Analysis"}
      </button>
      {stepIndex !== null && (
        <p data-testid="analysis-progress" className="mt-2 text-sm text-gray-500">
          {STEPS[stepIndex]}
        </p>
      )}
      {error && (
        <p role="alert" className="mt-2 text-sm text-red-600">
          {error}
        </p>
      )}
    </div>
  );
}
