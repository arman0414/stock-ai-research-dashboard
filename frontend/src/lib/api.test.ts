import { afterEach, describe, expect, it, vi } from "vitest";
import { addStock, ApiError, listWatchlist } from "./api";

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: "",
    json: async () => body,
  } as Response;
}

describe("api client error handling", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("throws an ApiError with the backend's detail message on a non-ok response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ detail: "Stock not found" }, 404)));

    await expect(listWatchlist()).rejects.toMatchObject({ message: expect.stringContaining("Stock not found") });
  });

  it("throws a clear ApiError when the backend cannot be reached at all", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("fetch failed"))
    );

    await expect(listWatchlist()).rejects.toBeInstanceOf(ApiError);
    await expect(listWatchlist()).rejects.toMatchObject({ message: expect.stringContaining("Could not reach the backend") });
  });

  it("addStock rolls back the watchlist entry when refresh finds no price history", async () => {
    const fetchMock = vi.fn();
    // 1. POST /stocks -> created
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 1, ticker: "ZZZZZZ", company_name: null, data_source: "twelve_data", created_at: null, updated_at: null, last_refreshed_at: null }, 201));
    // 2. POST /stocks/ZZZZZZ/refresh -> succeeds but finds nothing
    fetchMock.mockResolvedValueOnce(jsonResponse({ ticker: "ZZZZZZ", source: "twelve_data", start_date: "2021-01-01", end_date: "2026-01-01", rows_received: 0, rows_stored: 0 }, 200));
    // 3. GET /stocks/ZZZZZZ -> zero history rows
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 1, ticker: "ZZZZZZ", company_name: null, data_source: "twelve_data", created_at: null, updated_at: null, last_refreshed_at: null, latest_price: null, latest_price_date: null, price_history_count: 0 }, 200));
    // 4. DELETE /stocks/ZZZZZZ -> rollback
    fetchMock.mockResolvedValueOnce({ ok: true, status: 204, statusText: "", json: async () => undefined } as Response);

    vi.stubGlobal("fetch", fetchMock);

    await expect(addStock("zzzzzz")).rejects.toMatchObject({ message: expect.stringContaining("Could not fetch data for") });

    expect(fetchMock).toHaveBeenCalledTimes(4);
    const deleteCall = fetchMock.mock.calls[3];
    expect(deleteCall[1]).toMatchObject({ method: "DELETE" });
  });
});
