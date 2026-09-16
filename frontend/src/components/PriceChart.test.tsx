import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, cleanup } from "@testing-library/react";
import { StrictMode } from "react";
import PriceChart from "./PriceChart";
import type { PriceBarPoint } from "@/lib/types";

// A faithful-enough fake of lightweight-charts v5: like the real library,
// every chart/series method throws "Object is disposed" once chart.remove()
// has run (including calling remove() a second time). A permissive mock
// would never have caught the bug this guards against.
class FakeSeries {
  disposed = false;
  data: unknown[] = [];
  priceLines: object[] = [];
  private assertAlive() {
    if (this.disposed) throw new Error("Object is disposed");
  }
  setData(bars: unknown[]) {
    this.assertAlive();
    this.data = bars;
  }
  createPriceLine(options: object) {
    this.assertAlive();
    const line = { ...options };
    this.priceLines.push(line);
    return line;
  }
  removePriceLine(line: object) {
    this.assertAlive();
    this.priceLines = this.priceLines.filter((existing) => existing !== line);
  }
}

class FakeChart {
  disposed = false;
  series: FakeSeries | null = null;
  resizeCalls: { width: number }[] = [];
  private assertAlive() {
    if (this.disposed) throw new Error("Object is disposed");
  }
  addSeries() {
    this.assertAlive();
    this.series = new FakeSeries();
    return this.series;
  }
  applyOptions(options: { width: number }) {
    this.assertAlive();
    this.resizeCalls.push(options);
  }
  timeScale() {
    this.assertAlive();
    return { fitContent: () => this.assertAlive() };
  }
  remove() {
    this.assertAlive();
    this.disposed = true;
  }
}

const createChart = vi.fn(() => new FakeChart());

vi.mock("lightweight-charts", () => ({
  createChart: (...args: unknown[]) => createChart(...(args as [])),
  CandlestickSeries: "candlestick",
  ColorType: { Solid: "solid" },
}));

function getResizeObserverStub() {
  return (globalThis as unknown as { __ResizeObserverStub: { instances: { callback: ResizeObserverCallback; disconnect: () => void }[] } })
    .__ResizeObserverStub;
}

const sampleData: PriceBarPoint[] = [
  { date: "2024-01-01", open: 1, high: 2, low: 0.5, close: 1.5, volume: 100 },
  { date: "2024-01-02", open: 1.5, high: 2.5, low: 1, close: 2, volume: 200 },
];

beforeEach(() => {
  createChart.mockClear();
  getResizeObserverStub().instances.length = 0;
});

describe("PriceChart lifecycle", () => {
  it("creates exactly one chart and series on mount, and loads the initial data", () => {
    render(<PriceChart data={sampleData} range="6M" onRangeChange={() => {}} />);
    expect(createChart).toHaveBeenCalledTimes(1);
    const chart = createChart.mock.results[0]!.value as FakeChart;
    expect(chart.series?.data).toHaveLength(2);
  });

  it("removes the chart exactly once on unmount and disconnects its resize observer", () => {
    const { unmount } = render(<PriceChart data={sampleData} range="6M" onRangeChange={() => {}} />);
    const chart = createChart.mock.results[0]!.value as FakeChart;
    const observer = getResizeObserverStub().instances[0]!;

    unmount();

    expect(chart.disposed).toBe(true);
    expect(observer.disconnect).toHaveBeenCalledTimes(1);
    // Confirms cleanup didn't call remove() twice -- FakeChart.remove()
    // throws "Object is disposed" on a second call, so no throw means safe.
  });

  it("creates a brand new chart after unmount + remount without touching the disposed one", () => {
    const { unmount } = render(<PriceChart data={sampleData} range="6M" onRangeChange={() => {}} />);
    const firstChart = createChart.mock.results[0]!.value as FakeChart;
    unmount();

    render(<PriceChart data={sampleData} range="6M" onRangeChange={() => {}} />);
    const secondChart = createChart.mock.results[1]!.value as FakeChart;

    expect(createChart).toHaveBeenCalledTimes(2);
    expect(firstChart).not.toBe(secondChart);
    expect(secondChart.disposed).toBe(false);
  });

  it("survives React Strict Mode's dev-only mount, cleanup, remount simulation", () => {
    expect(() =>
      render(
        <StrictMode>
          <PriceChart data={sampleData} range="6M" onRangeChange={() => {}} />
        </StrictMode>
      )
    ).not.toThrow();

    // Strict Mode double-invokes: exactly one chart should remain live and
    // undisposed, holding the final data.
    const results = createChart.mock.results.map((r) => r.value as FakeChart);
    const alive = results.filter((c) => !c.disposed);
    expect(alive).toHaveLength(1);
    expect(alive[0]!.series?.data).toHaveLength(2);
  });

  it("ignores a resize-observer callback that fires after the component has unmounted", () => {
    const { unmount } = render(<PriceChart data={sampleData} range="6M" onRangeChange={() => {}} />);
    const observer = getResizeObserverStub().instances[0]!;
    const chart = createChart.mock.results[0]!.value as FakeChart;

    unmount();

    // Simulate a resize tick that was already queued before cleanup ran.
    expect(() => observer.callback([{ contentRect: { width: 640 } } as ResizeObserverEntry], observer as unknown as ResizeObserver)).not.toThrow();
    expect(chart.resizeCalls).toHaveLength(0);
  });

  it("updates data without recreating the chart when the range/data prop changes", () => {
    const { rerender } = render(<PriceChart data={sampleData} range="6M" onRangeChange={() => {}} />);
    const chart = createChart.mock.results[0]!.value as FakeChart;

    const moreData = [...sampleData, { date: "2024-01-03", open: 2, high: 3, low: 1.5, close: 2.5, volume: 150 }];
    rerender(<PriceChart data={moreData} range="1Y" onRangeChange={() => {}} />);

    expect(createChart).toHaveBeenCalledTimes(1);
    expect(chart.series?.data).toHaveLength(3);
  });

  it("adds and cleanly replaces support/resistance price lines as they change", () => {
    const { rerender } = render(<PriceChart data={sampleData} support={10} resistance={20} range="6M" onRangeChange={() => {}} />);
    const chart = createChart.mock.results[0]!.value as FakeChart;
    expect(chart.series?.priceLines).toHaveLength(2);

    rerender(<PriceChart data={sampleData} support={11} resistance={21} range="6M" onRangeChange={() => {}} />);
    expect(chart.series?.priceLines).toHaveLength(2);
  });

  it("keeps the chart container mounted (never swapped for the empty-state element) so lightweight-charts' own DOM nodes are never clobbered", () => {
    const { getByTestId, rerender } = render(<PriceChart data={[]} range="6M" onRangeChange={() => {}} />);
    expect(getByTestId("price-chart")).toBeInTheDocument();

    rerender(<PriceChart data={sampleData} range="6M" onRangeChange={() => {}} />);
    expect(getByTestId("price-chart")).toBeInTheDocument();
    expect(createChart).toHaveBeenCalledTimes(1);
  });
});

describe("PriceChart repeated mount/unmount (navigation simulation)", () => {
  it("never throws across rapid mount/unmount cycles", () => {
    expect(() => {
      for (let i = 0; i < 5; i++) {
        const { unmount } = render(<PriceChart data={sampleData} support={10} resistance={20} range="6M" onRangeChange={() => {}} />);
        cleanup();
        unmount();
      }
    }).not.toThrow();
  });
});
