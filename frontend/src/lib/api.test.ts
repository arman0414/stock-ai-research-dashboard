import { afterEach, describe, expect, it, vi } from "vitest";
import { addStock, ApiError, listWatchlist, listTransactions, previewSell } from "./api";

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

describe("ledger API contracts", () => {
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

  it("loads history beyond 500 rows and normalizes decimal strings", async () => {
    const first = Array.from({ length: 500 }, (_, id) => ({ id: id + 2, ticker: "IREN", transaction_type: "BUY",
      quantity: "1.000000", price_per_share: "10.000000", fees: "0.000000", cycle_index: 1 }));
    const last = { id: 1, ticker: "MU", transaction_type: "SELL", quantity: "2.000000", price_per_share: "12.000000",
      fees: "0.010000", realized_profit_loss: "3.990000", cycle_index: 1 };
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse(first)).mockResolvedValueOnce(jsonResponse([last]));
    vi.stubGlobal("fetch", fetchMock);
    const history = await listTransactions();
    expect(history).toHaveLength(501);
    expect(history[500]).toMatchObject({ ticker: "MU", quantity: 2, realized_profit_loss: 3.99 });
    expect(fetchMock.mock.calls[1][0]).toContain("offset=500");
  });

  it("sends the sale date and normalizes the backend preview", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ cost_basis_per_share: "10.003333", cost_basis_total: "10.01",
      sale_proceeds: "11.00", realized_profit_loss: "0.99", realized_profit_loss_pct: "9.8901",
      shares_owned: "1.000000", remaining_shares: "0.000000", exceeds_position: false }));
    vi.stubGlobal("fetch", fetchMock);
    const result = await previewSell("IREN", { quantity: 1, price_per_share: 11, transaction_date: "2026-09-19T15:00:00.000Z" });
    expect(result).toMatchObject({ cost_basis_total: 10.01, realized_profit_loss: 0.99, exceeds_position: false });
    expect(new URL(String(fetchMock.mock.calls[0][0]), "http://localhost").searchParams.get("transaction_date")).toBe("2026-09-19T15:00:00.000Z");
  });
});
