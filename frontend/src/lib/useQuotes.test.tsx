import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useQuotes } from "./useQuotes";
import * as api from "./api";
import { makeQuoteResult } from "./testFixtures";

describe("useQuotes", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("fetches all tickers in a single batched request, not one request per ticker", async () => {
    const spy = vi.spyOn(api, "getStockQuotes").mockResolvedValue({
      NVDA: makeQuoteResult({ ticker: "NVDA" }),
      AMD: makeQuoteResult({ ticker: "AMD" }),
    });

    const { result } = renderHook(() => useQuotes(["NVDA", "AMD"]));

    await act(async () => {
      await vi.runOnlyPendingTimersAsync();
    });

    // Every call must request the whole ticker list in one go -- never a
    // separate call per individual ticker.
    for (const call of spy.mock.calls) {
      expect(call[0]).toEqual(["NVDA", "AMD"]);
    }
    expect(result.current.quotes.NVDA).toBeDefined();
    expect(result.current.quotes.AMD).toBeDefined();
  });

  it("one ticker's failure does not prevent the others from resolving", async () => {
    vi.spyOn(api, "getStockQuotes").mockResolvedValue({
      NVDA: makeQuoteResult({ ticker: "NVDA" }),
      // MU deliberately missing -- simulates a partial provider failure
    });

    const { result } = renderHook(() => useQuotes(["NVDA", "MU"]));

    await act(async () => {
      await vi.runOnlyPendingTimersAsync();
    });

    expect(result.current.quotes.NVDA).toBeDefined();
    expect(result.current.quotes.MU).toBeUndefined(); // absent, not a thrown error that would blank NVDA too
  });

  it("polls again after the interval elapses", async () => {
    const spy = vi.spyOn(api, "getStockQuotes").mockResolvedValue({ NVDA: makeQuoteResult({ ticker: "NVDA" }) });
    Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });

    renderHook(() => useQuotes(["NVDA"]));
    await act(async () => {
      await vi.runOnlyPendingTimersAsync();
    });
    const callsAfterMount = spy.mock.calls.length;
    expect(callsAfterMount).toBeGreaterThan(0);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(spy.mock.calls.length).toBeGreaterThan(callsAfterMount);
  });

  it("does not poll while the tab is hidden", async () => {
    const spy = vi.spyOn(api, "getStockQuotes").mockResolvedValue({ NVDA: makeQuoteResult({ ticker: "NVDA" }) });
    Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true });

    renderHook(() => useQuotes(["NVDA"]));
    await act(async () => {
      await vi.runOnlyPendingTimersAsync(); // the initial mount fetch always runs regardless of visibility
    });
    const callsAfterMount = spy.mock.calls.length;

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(spy.mock.calls.length).toBe(callsAfterMount); // no additional poll while hidden
  });
});
