import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import PositionsPage from "./page";
import * as api from "@/lib/api";
import { makeClosedPosition, makePortfolioSummary, makePosition, makeTransaction } from "@/lib/testFixtures";

vi.mock("@/lib/useQuotes", () => ({
  useQuotes: () => ({ quotes: { IREN: { ticker: "IREN", price: 45, market_status: "OPEN", is_stale: false, source: "LIVE_QUOTE" } }, refreshing: false }),
}));

// PositionCard fetches a model signal on mount; keep the ML path out of these
// portfolio-tracking tests entirely.
vi.mock("@/components/PositionCard", () => ({
  default: ({ position, onBuyMore, onSell }: { position: { ticker: string; shares: number; realized_pl: number }; onBuyMore: () => void; onSell: () => void }) => (
    <div data-testid={`position-card-${position.ticker}`}>
      <span>{position.ticker}</span>
      <span>{position.shares} shares</span>
      <span>realized {position.realized_pl}</span>
      <button onClick={onBuyMore}>Buy More</button>
      <button onClick={onSell}>Sell</button>
    </div>
  ),
}));

const openPosition = makePosition({ id: 9, ticker: "IREN", shares: 100, purchase_price: 32, average_cost: 32, total_cost_basis: 3200, realized_pl: 650 });

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api, "previewSell").mockResolvedValue({ ticker: "IREN", quantity: 50, shares_owned: 100,
    remaining_shares: 50, cost_basis_per_share: 32, cost_basis_total: 1600,
    sale_proceeds: 2250, realized_profit_loss: 650, realized_profit_loss_pct: 40.625, exceeds_position: false });
  vi.spyOn(api, "listPositions").mockResolvedValue([openPosition]);
  vi.spyOn(api, "listTransactions").mockResolvedValue([
    makeTransaction({
      id: 2,
      transaction_type: "SELL",
      quantity: 50,
      price_per_share: 45,
      realized_profit_loss: 650,
      realized_profit_loss_pct: 40.625,
      cost_basis_total: 1600,
      sale_proceeds: 2250,
    }),
    makeTransaction({ id: 1, transaction_type: "BUY", quantity: 150, price_per_share: 32 }),
  ]);
  vi.spyOn(api, "listClosedPositions").mockResolvedValue([makeClosedPosition()]);
  vi.spyOn(api, "getPortfolioSummary").mockResolvedValue(makePortfolioSummary());
});

describe("PositionsPage", () => {
  it("opens on the overview with the portfolio summary and open positions", async () => {
    render(<PositionsPage />);
    expect(await screen.findByText("Portfolio Value")).toBeInTheDocument();
    expect(screen.getByTestId("position-card-IREN")).toBeInTheDocument();
  });

  it("keeps a partially sold position open and shows its realized P/L", async () => {
    render(<PositionsPage />);
    const card = await screen.findByTestId("position-card-IREN");
    expect(card).toHaveTextContent("100 shares");
    expect(card).toHaveTextContent("realized 650");
  });

  it("shows transaction history on the HISTORY tab", async () => {
    const user = userEvent.setup();
    render(<PositionsPage />);
    await screen.findByTestId("position-card-IREN");
    await user.click(screen.getByRole("tab", { name: "HISTORY" }));

    expect(await screen.findByText("+$650.00 (+40.63%)")).toBeInTheDocument();
  });

  it("shows closed cycles on the CLOSED tab", async () => {
    const user = userEvent.setup();
    render(<PositionsPage />);
    await screen.findByTestId("position-card-IREN");
    await user.click(screen.getByRole("tab", { name: "CLOSED" }));

    expect(await screen.findByTestId("closed-position-IREN")).toHaveTextContent("+$1,950.00 (+40.63%)");
  });

  it("records a sale through the ledger rather than editing quantity", async () => {
    const user = userEvent.setup();
    const sellSpy = vi.spyOn(api, "sellShares").mockResolvedValue(openPosition);
    render(<PositionsPage />);
    await screen.findByTestId("position-card-IREN");

    await user.click(screen.getByRole("button", { name: "Sell" }));
    await user.type(screen.getByLabelText("Quantity to sell"), "50");
    await user.type(screen.getByLabelText("Sale price"), "45");
    await waitFor(() => expect(screen.getByRole("button", { name: "Confirm Sale" })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: "Confirm Sale" }));

    await waitFor(() => expect(sellSpy).toHaveBeenCalledTimes(1));
    expect(sellSpy.mock.calls[0][0]).toBe("IREN");
    expect(sellSpy.mock.calls[0][1]).toMatchObject({ quantity: 50, price_per_share: 45 });
  });

  it("records a buy-more through the ledger", async () => {
    const user = userEvent.setup();
    const buySpy = vi.spyOn(api, "buyShares").mockResolvedValue(openPosition);
    render(<PositionsPage />);
    await screen.findByTestId("position-card-IREN");

    await user.click(screen.getByRole("button", { name: "Buy More" }));
    await user.type(screen.getByLabelText("Quantity"), "25");
    await user.type(screen.getByLabelText("Purchase price"), "40");
    await user.click(screen.getByRole("button", { name: "Confirm Purchase" }));

    await waitFor(() => expect(buySpy).toHaveBeenCalledTimes(1));
    expect(buySpy.mock.calls[0][1]).toMatchObject({ quantity: 25, price_per_share: 40 });
  });

  it("drops a fully closed position out of Open Positions", async () => {
    vi.spyOn(api, "listPositions").mockResolvedValue([]);
    render(<PositionsPage />);
    expect(await screen.findByText("You haven't entered any positions yet.")).toBeInTheDocument();
    expect(screen.queryByTestId("position-card-IREN")).not.toBeInTheDocument();
  });

  it("loads positions and history even when summary fails", async () => {
    vi.spyOn(api, "getPortfolioSummary").mockRejectedValue(new api.ApiError("Summary down", 500));
    const user = userEvent.setup();
    render(<PositionsPage />);
    expect(await screen.findByTestId("position-card-IREN")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "HISTORY" }));
    expect(await screen.findByText("+$650.00 (+40.63%)")).toBeInTheDocument();
    expect(await screen.findByText(/Summary: Summary down/)).toBeInTheDocument();
  });

  it("uses the committed sale response if the positions reload fails", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "sellShares").mockResolvedValue(makePosition({ ...openPosition, shares: 50 }));
    vi.spyOn(api, "listPositions").mockResolvedValueOnce([openPosition]).mockRejectedValue(new Error("Reload failed"));
    render(<PositionsPage />);
    await screen.findByTestId("position-card-IREN");
    await user.click(screen.getByRole("button", { name: "Sell" }));
    await user.type(screen.getByLabelText("Quantity to sell"), "50");
    await user.type(screen.getByLabelText("Sale price"), "45");
    await waitFor(() => expect(screen.getByRole("button", { name: "Confirm Sale" })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: "Confirm Sale" }));
    await waitFor(() => expect(screen.getByTestId("position-card-IREN")).toHaveTextContent("50 shares"));
  });

  it("keeps history and displays the error when a correction is rejected", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const remove = vi.spyOn(api, "deleteTransaction").mockRejectedValue(new Error("Later sale would oversell"));
    render(<PositionsPage />);
    await screen.findByTestId("position-card-IREN");
    await user.click(screen.getByRole("tab", { name: "HISTORY" }));
    await user.click(screen.getByRole("button", { name: "Delete transaction 1" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Later sale would oversell");
    expect(remove).toHaveBeenCalledWith(1);
    expect(screen.getByTestId("transaction-1")).toBeInTheDocument();
  });
});
