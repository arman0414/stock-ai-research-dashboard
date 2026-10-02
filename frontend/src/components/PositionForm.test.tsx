import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import PositionForm from "./PositionForm";
import { makePosition } from "@/lib/testFixtures";

describe("PositionForm annotations", () => {
  it("does not offer ledger-derived fields and submits only annotations", async () => {
    const user = userEvent.setup();
    const submit = vi.fn().mockResolvedValue(undefined);
    render(<PositionForm initial={makePosition({ notes: "before" })} onSubmit={submit} onCancel={vi.fn()} />);
    expect(screen.queryByLabelText("Shares")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Purchase Price")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Purchase Date")).not.toBeInTheDocument();
    await user.clear(screen.getByLabelText("Notes (optional)"));
    await user.type(screen.getByLabelText("Notes (optional)"), "after");
    await user.click(screen.getByRole("button", { name: "Save Position" }));
    await waitFor(() => expect(submit).toHaveBeenCalledOnce());
    expect(Object.keys(submit.mock.calls[0][0]).sort()).toEqual(["my_target_price", "notes", "stop_loss_price"]);
    expect(submit.mock.calls[0][0].notes).toBe("after");
  });

  it("still records purchase fields when opening a holding", async () => {
    const user = userEvent.setup();
    const submit = vi.fn().mockResolvedValue(undefined);
    render(<PositionForm onSubmit={submit} onCancel={vi.fn()} />);
    await user.type(screen.getByLabelText("Ticker"), "iren");
    await user.type(screen.getByLabelText("Shares"), "3");
    await user.type(screen.getByLabelText("Purchase Price"), "10");
    await user.click(screen.getByRole("button", { name: "Save Position" }));
    await waitFor(() => expect(submit).toHaveBeenCalledOnce());
    expect(submit.mock.calls[0][0]).toMatchObject({ ticker: "IREN", shares: 3, purchase_price: 10 });
  });
});
