import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as api from "@/lib/api";
import { makePosition } from "@/lib/testFixtures";
import type { SellPreview } from "@/lib/types";
import TradeModal from "./TradeModal";

const preview: SellPreview = { ticker: "IREN", quantity: 5, shares_owned: 20, remaining_shares: 15,
  cost_basis_per_share: 10, cost_basis_total: 50, sale_proceeds: 150,
  realized_profit_loss: 100, realized_profit_loss_pct: 200, exceeds_position: false };
const position = makePosition({ ticker: "IREN", shares: 20, average_cost: 15 });

beforeEach(() => vi.restoreAllMocks());

describe("dated backend sale previews", () => {
  it("uses backend historical basis and includes the selected time", async () => {
    const user = userEvent.setup();
    const spy = vi.spyOn(api, "previewSell").mockResolvedValue(preview);
    render(<TradeModal mode="SELL" position={position} onSubmit={vi.fn()} onCancel={vi.fn()} />);
    await user.type(screen.getByLabelText("Quantity to sell"), "5");
    await user.type(screen.getByLabelText("Sale price"), "30");
    expect(await screen.findByText("$50.00")).toBeInTheDocument();
    expect(screen.queryByText("$75.00")).not.toBeInTheDocument();
    expect(spy.mock.lastCall?.[1].transaction_date).toMatch(/T\d\d:\d\d:\d\d\.000Z$/);
  });

  it("blocks confirmation when the backend rejects historical ordering", async () => {
    const user = userEvent.setup();
    const submit = vi.fn();
    vi.spyOn(api, "previewSell").mockResolvedValue({ ...preview, exceeds_position: true, error: "Sold before buying." });
    render(<TradeModal mode="SELL" position={position} onSubmit={submit} onCancel={vi.fn()} />);
    await user.type(screen.getByLabelText("Quantity to sell"), "5");
    await user.type(screen.getByLabelText("Sale price"), "30");
    expect(await screen.findByRole("alert")).toHaveTextContent("Sold before buying.");
    expect(screen.getByRole("button", { name: "Confirm Sale" })).toBeDisabled();
    expect(submit).not.toHaveBeenCalled();
  });

  it("does not enable a sale with a failed preview", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "previewSell").mockRejectedValue(new Error("Preview unavailable"));
    render(<TradeModal mode="SELL" position={position} onSubmit={vi.fn()} onCancel={vi.fn()} />);
    await user.type(screen.getByLabelText("Quantity to sell"), "5");
    await user.type(screen.getByLabelText("Sale price"), "30");
    expect(await screen.findByRole("alert")).toHaveTextContent("Preview unavailable");
    expect(screen.getByRole("button", { name: "Confirm Sale" })).toBeDisabled();
  });

  it("ignores a stale response after the inputs change", async () => {
    const user = userEvent.setup();
    let resolveOld!: (value: SellPreview) => void;
    const old = new Promise<SellPreview>(resolve => { resolveOld = resolve; });
    const spy = vi.spyOn(api, "previewSell").mockReturnValueOnce(old).mockResolvedValue({ ...preview, realized_profit_loss: 110 });
    render(<TradeModal mode="SELL" position={position} onSubmit={vi.fn()} onCancel={vi.fn()} />);
    await user.type(screen.getByLabelText("Quantity to sell"), "5");
    await user.type(screen.getByLabelText("Sale price"), "30");
    await waitFor(() => expect(spy).toHaveBeenCalledOnce());
    await user.clear(screen.getByLabelText("Sale price"));
    await user.type(screen.getByLabelText("Sale price"), "32");
    expect(screen.getByRole("button", { name: "Confirm Sale" })).toBeDisabled();
    expect(await screen.findByText("+$110.00")).toBeInTheDocument();
    resolveOld(preview);
    await waitFor(() => expect(screen.queryByText("+$100.00")).not.toBeInTheDocument());
  });
});
