import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TradeModal from "./TradeModal";
import TransactionHistory from "./TransactionHistory";
import ClosedPositions from "./ClosedPositions";
import PortfolioSummaryBar from "./PortfolioSummaryBar";
import { makeClosedPosition, makePortfolioSummary, makePosition, makeTransaction } from "@/lib/testFixtures";

import * as api from "@/lib/api";

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api, "previewSell").mockImplementation(async (ticker, input) => ({
    ticker, quantity: input.quantity, shares_owned: 150, remaining_shares: 150 - input.quantity,
    cost_basis_per_share: 32, cost_basis_total: input.quantity * 32,
    sale_proceeds: input.quantity * input.price_per_share - (input.fees ?? 0),
    realized_profit_loss: input.quantity * (input.price_per_share - 32) - (input.fees ?? 0),
    realized_profit_loss_pct: ((input.quantity * (input.price_per_share - 32) - (input.fees ?? 0)) / (input.quantity * 32)) * 100,
    exceeds_position: false,
  }));
});

const IREN = makePosition({ id: 9, ticker: "IREN", shares: 150, purchase_price: 32, average_cost: 32, total_cost_basis: 4800 });

describe("TradeModal - Buy More", () => {
  it("previews the new weighted average cost and quantity before confirming", async () => {
    const user = userEvent.setup();
    render(<TradeModal mode="BUY" position={makePosition({ ticker: "IREN", shares: 100, average_cost: 30 })} onSubmit={vi.fn()} onCancel={vi.fn()} />);

    await user.type(screen.getByLabelText("Quantity"), "50");
    await user.type(screen.getByLabelText("Purchase price"), "36");

    // (100*30 + 50*36) / 150 = 32
    expect(await screen.findByText("$32.00")).toBeInTheDocument();
    expect(screen.getByText("150")).toBeInTheDocument();
    expect(screen.getByText("$30.00")).toBeInTheDocument(); // old average cost
  });

  it("submits the buy with quantity, price, date and fee", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<TradeModal mode="BUY" position={IREN} onSubmit={onSubmit} onCancel={vi.fn()} />);

    await user.type(screen.getByLabelText("Quantity"), "10");
    await user.type(screen.getByLabelText("Purchase price"), "40");
    await user.type(screen.getByLabelText("Fee"), "2");
    await user.click(screen.getByRole("button", { name: "Confirm Purchase" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ quantity: 10, price_per_share: 40, fees: 2 });
  });
});

describe("TradeModal - Sell", () => {
  it("previews proceeds, cost basis and realized P/L", async () => {
    const user = userEvent.setup();
    render(<TradeModal mode="SELL" position={IREN} onSubmit={vi.fn()} onCancel={vi.fn()} />);

    await user.type(screen.getByLabelText("Quantity to sell"), "50");
    await user.type(screen.getByLabelText("Sale price"), "45");

    expect(await screen.findByText("$2,250.00")).toBeInTheDocument(); // proceeds
    expect(screen.getByText("$1,600.00")).toBeInTheDocument(); // cost basis
    expect(screen.getByText("+$650.00")).toBeInTheDocument(); // realized
    expect(screen.getByText("+40.63%")).toBeInTheDocument(); // return
  });

  it("reduces proceeds by the fee", async () => {
    const user = userEvent.setup();
    render(<TradeModal mode="SELL" position={IREN} onSubmit={vi.fn()} onCancel={vi.fn()} />);

    await user.type(screen.getByLabelText("Quantity to sell"), "50");
    await user.type(screen.getByLabelText("Sale price"), "45");
    await user.type(screen.getByLabelText("Fee"), "2");

    expect(await screen.findByText("$2,248.00")).toBeInTheDocument();
    expect(screen.getByText("+$648.00")).toBeInTheDocument();
  });

  it("shows a loss in red styling when selling below cost", async () => {
    const user = userEvent.setup();
    render(<TradeModal mode="SELL" position={IREN} onSubmit={vi.fn()} onCancel={vi.fn()} />);

    await user.type(screen.getByLabelText("Quantity to sell"), "50");
    await user.type(screen.getByLabelText("Sale price"), "20");

    const realized = await screen.findByText("-$600.00");
    expect(realized).toHaveClass("text-red-700");
  });

  it("blocks selling more shares than owned with a clear message", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<TradeModal mode="SELL" position={makePosition({ ticker: "IREN", shares: 100, average_cost: 32 })} onSubmit={onSubmit} onCancel={vi.fn()} />);

    await user.type(screen.getByLabelText("Quantity to sell"), "120");
    await user.type(screen.getByLabelText("Sale price"), "45");

    expect(await screen.findByRole("alert")).toHaveTextContent("You currently own 100 shares of IREN.");
    expect(screen.getByRole("button", { name: "Confirm Sale" })).toBeDisabled();
    expect(onSubmit).not.toHaveBeenCalled();
  });
});

describe("TransactionHistory", () => {
  const rows = [
    makeTransaction({
      id: 2,
      transaction_type: "SELL",
      quantity: 50,
      price_per_share: 45,
      transaction_date: "2026-09-18T00:00:00Z",
      cost_basis_total: 1600,
      sale_proceeds: 2250,
      realized_profit_loss: 650,
      realized_profit_loss_pct: 40.625,
    }),
    makeTransaction({ id: 1, transaction_type: "BUY", quantity: 150, price_per_share: 32, transaction_date: "2026-09-02T00:00:00Z" }),
    makeTransaction({ id: 3, ticker: "NVDA", transaction_type: "BUY", quantity: 5, price_per_share: 200, transaction_date: "2026-09-10T00:00:00Z" }),
  ];

  it("lists buys and sells with realized P/L", () => {
    render(<TransactionHistory transactions={rows} />);
    expect(screen.getByText("+$650.00 (+40.63%)")).toBeInTheDocument();
    expect(screen.getAllByText("BUY").length).toBe(2);
    expect(screen.getByText("SELL")).toBeInTheDocument();
  });

  it("shows a dash for buys, which realize nothing", () => {
    render(<TransactionHistory transactions={[rows[1]]} />);
    expect(screen.getByTestId("transaction-1")).toHaveTextContent("—");
  });

  it("filters to sells only", async () => {
    const user = userEvent.setup();
    render(<TransactionHistory transactions={rows} />);
    await user.click(screen.getByRole("button", { name: "Sells" }));

    expect(screen.getByTestId("transaction-2")).toBeInTheDocument();
    expect(screen.queryByTestId("transaction-1")).not.toBeInTheDocument();
  });

  it("filters by stock", async () => {
    const user = userEvent.setup();
    render(<TransactionHistory transactions={rows} />);
    await user.selectOptions(screen.getByLabelText("Filter by stock"), "NVDA");

    expect(screen.getByTestId("transaction-3")).toBeInTheDocument();
    expect(screen.queryByTestId("transaction-2")).not.toBeInTheDocument();
  });

  it("renders an unknown date rather than inventing one", () => {
    render(<TransactionHistory transactions={[makeTransaction({ id: 7, transaction_date: null })]} />);
    expect(screen.getByTestId("transaction-7")).toHaveTextContent("Unknown");
  });
});

describe("ClosedPositions", () => {
  it("shows a fully closed cycle with its totals", () => {
    render(<ClosedPositions positions={[makeClosedPosition()]} />);
    const card = screen.getByTestId("closed-position-IREN");
    expect(card).toHaveTextContent("Closed");
    expect(card).toHaveTextContent("$4,800.00");
    expect(card).toHaveTextContent("$6,750.00");
    expect(card).toHaveTextContent("+$1,950.00 (+40.63%)");
  });

  it("styles a losing close in red", () => {
    render(<ClosedPositions positions={[makeClosedPosition({ realized_profit_loss: -500, return_pct: -10.4 })]} />);
    expect(screen.getByText("-$500.00 (-10.40%)")).toHaveClass("text-red-700");
  });

  it("explains the empty state", () => {
    render(<ClosedPositions positions={[]} />);
    expect(screen.getByText("No closed positions yet.")).toBeInTheDocument();
  });
});

describe("PortfolioSummaryBar", () => {
  it("labels realized and unrealized P/L separately", () => {
    render(<PortfolioSummaryBar summary={makePortfolioSummary()} />);
    expect(screen.getByText("Portfolio Value")).toBeInTheDocument();
    expect(screen.getByText("Open Cost Basis")).toBeInTheDocument();
    expect(screen.getByText("Unrealized P/L")).toBeInTheDocument();
    expect(screen.getByText("Realized P/L")).toBeInTheDocument();
    expect(screen.getByText("+$1,300.00")).toBeInTheDocument();
    expect(screen.getByText("+$650.00")).toBeInTheDocument();
    expect(screen.getByText("+$1,950.00")).toBeInTheDocument(); // total
  });

  it("uses red styling for a negative total", () => {
    render(<PortfolioSummaryBar summary={makePortfolioSummary({ unrealized_pl: -200, realized_pl: -50, total_pl: -250 })} />);
    expect(screen.getByText("-$250.00")).toHaveClass("text-red-700");
  });
});

