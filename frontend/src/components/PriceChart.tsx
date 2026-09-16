"use client";

import { useEffect, useRef } from "react";
import { CandlestickSeries, ColorType, createChart, type IChartApi, type ISeriesApi, type UTCTimestamp } from "lightweight-charts";
import type { PriceBarPoint, PriceRange } from "@/lib/types";
import { PRICE_RANGES } from "@/lib/types";

interface PriceChartProps {
  data: PriceBarPoint[];
  support?: number | null;
  resistance?: number | null;
  range: PriceRange;
  onRangeChange: (range: PriceRange) => void;
}

export default function PriceChart({ data, support, resistance, range, onRangeChange }: PriceChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  // lightweight-charts throws a raw "Object is disposed" error (rather than
  // failing gracefully) if any chart/series method is ever called after
  // chart.remove() -- including a second remove() itself. Nothing in the
  // library exposes an isDisposed check, so this ref is the guard: it is set
  // BEFORE any other cleanup step and checked before every subsequent
  // chart/series call, so a callback already queued when cleanup runs (a
  // ResizeObserver tick, a data/price-line effect from React Strict Mode's
  // dev-only mount->cleanup->mount simulation) bails out instead of touching
  // a chart that no longer exists.
  const disposedRef = useRef(true);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    disposedRef.current = false;
    const chart = createChart(container, {
      height: 320,
      layout: { background: { type: ColorType.Solid, color: "#ffffff" }, textColor: "#4b5563" },
      grid: { vertLines: { color: "#f3f4f6" }, horzLines: { color: "#f3f4f6" } },
      timeScale: { borderColor: "#e5e7eb" },
      rightPriceScale: { borderColor: "#e5e7eb" },
    });
    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#16a34a",
      downColor: "#dc2626",
      borderVisible: false,
      wickUpColor: "#16a34a",
      wickDownColor: "#dc2626",
    });
    chartRef.current = chart;
    seriesRef.current = series;

    // Container-based ResizeObserver instead of a window "resize" listener --
    // it also reacts to layout-only width changes (e.g. a sidebar toggling)
    // that never fire a window resize event, and it is what gets disconnected
    // below before the chart is removed.
    const resizeObserver = new ResizeObserver((entries) => {
      if (disposedRef.current) return;
      const entry = entries[0];
      if (!entry) return;
      chart.applyOptions({ width: entry.contentRect.width });
    });
    resizeObserver.observe(container);

    return () => {
      // Order matters: flip the guard and stop anything that could still
      // call into the chart BEFORE the chart itself is removed.
      disposedRef.current = true;
      resizeObserver.disconnect();
      chartRef.current = null;
      seriesRef.current = null;
      chart.remove();
    };
  }, []);

  useEffect(() => {
    if (disposedRef.current || !seriesRef.current) return;
    seriesRef.current.setData(
      data.map((bar) => ({
        time: (new Date(bar.date).getTime() / 1000) as UTCTimestamp,
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
      }))
    );
    chartRef.current?.timeScale().fitContent();
  }, [data]);

  useEffect(() => {
    const series = seriesRef.current;
    if (disposedRef.current || !series) return;
    const lines = [] as ReturnType<ISeriesApi<"Candlestick">["createPriceLine"]>[];
    if (support) {
      lines.push(series.createPriceLine({ price: support, color: "#16a34a", lineStyle: 2, lineWidth: 1, title: "Support" }));
    }
    if (resistance) {
      lines.push(series.createPriceLine({ price: resistance, color: "#dc2626", lineStyle: 2, lineWidth: 1, title: "Resistance" }));
    }
    return () => {
      if (disposedRef.current) return;
      lines.forEach((line) => series.removePriceLine(line));
    };
  }, [support, resistance, data]);

  return (
    <div>
      <div className="mb-2 flex gap-1">
        {PRICE_RANGES.map((option) => (
          <button
            key={option}
            onClick={() => onRangeChange(option)}
            className={`rounded-md px-2.5 py-1 text-xs font-medium ${
              option === range ? "bg-gray-900 text-white" : "text-gray-500 hover:bg-gray-100"
            }`}
          >
            {option}
          </button>
        ))}
      </div>
      {/* The chart's container div is ALWAYS mounted (never swapped out for a
          different element) once this component renders. lightweight-charts
          attaches its own canvas nodes to it directly, outside React's
          knowledge; if the "no data" message and the chart container were
          alternatives in the same ternary/JSX slot, React would reuse this
          div for both (same element type) and overwrite those untracked
          canvas children when it patches in the empty-state text -- corrupting
          the chart's DOM without ever going through chart.remove(). Hiding the
          container with a class keeps the chart's own DOM intact. */}
      <div className="relative">
        {data.length === 0 && (
          <div className="flex h-80 items-center justify-center text-sm text-gray-400">No price history available for this range.</div>
        )}
        <div ref={containerRef} data-testid="price-chart" className={data.length === 0 ? "hidden" : undefined} />
      </div>
    </div>
  );
}
