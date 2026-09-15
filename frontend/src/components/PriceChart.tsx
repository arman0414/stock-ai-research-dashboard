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

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
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

    const resize = () => {
      if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth });
    };
    resize();
    window.addEventListener("resize", resize);

    return () => {
      window.removeEventListener("resize", resize);
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!seriesRef.current) return;
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
    if (!series) return;
    const lines = [] as ReturnType<ISeriesApi<"Candlestick">["createPriceLine"]>[];
    if (support) {
      lines.push(series.createPriceLine({ price: support, color: "#16a34a", lineStyle: 2, lineWidth: 1, title: "Support" }));
    }
    if (resistance) {
      lines.push(series.createPriceLine({ price: resistance, color: "#dc2626", lineStyle: 2, lineWidth: 1, title: "Resistance" }));
    }
    return () => {
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
      {data.length === 0 ? (
        <div className="flex h-80 items-center justify-center text-sm text-gray-400">No price history available for this range.</div>
      ) : (
        <div ref={containerRef} data-testid="price-chart" />
      )}
    </div>
  );
}
