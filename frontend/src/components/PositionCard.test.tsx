import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import PositionCard from "./PositionCard";
import { makeMultiHorizonPrediction, makePosition, makeQuoteResult } from "@/lib/testFixtures";
import * as api from "@/lib/api";

describe("PositionCard", () => {
  it("computes cost, current value, profit, and return from the fresh quote -- never the prediction price", async () => {
    vi.spyOn(api, "getPrediction").mockResolvedValue(makeMultiHorizonPrediction({ current_price: 999.99 })); // deliberately different from the quote

    const position = makePosition({ shares: 20, purchase_price: 190 });
    const quote = makeQuoteResult({ price: 218.29 });
    render(<PositionCard position={position} quote={quote} onEdit={() => {}} onDelete={() => {}} />);

    // cost = 20 * 190 = 3800
    expect(await screen.findByText("$3,800.00")).toBeInTheDocument();

    // current value = 20 * 218.29 = 4365.80 (from the QUOTE price, not the $999.99 prediction price)
    await waitFor(() => expect(screen.getByText("$4,365.80")).toBeInTheDocument());
    expect(screen.queryByText("$999.99")).not.toBeInTheDocument();

    // profit = 4365.80 - 3800 = +565.80
    expect(screen.getByText("+$565.80")).toBeInTheDocument();
  });

  it("keeps My Target (user's own) visually and numerically separate from the model's target", async () => {
    vi.spyOn(api, "getPrediction").mockResolvedValue(makeMultiHorizonPrediction());

    const position = makePosition({ my_target_price: 240 });
    render(<PositionCard position={position} quote={makeQuoteResult()} onEdit={() => {}} onDelete={() => {}} />);

    expect(screen.getByText("My Target (yours)")).toBeInTheDocument();
    expect(await screen.findByText("5D Model Target")).toBeInTheDocument();

    // The user's $240 target must appear once, distinctly, from the model's $225 target.
    const myTargetLabel = screen.getByText("My Target (yours)");
    const myTargetValue = myTargetLabel.nextElementSibling;
    expect(myTargetValue).toHaveTextContent("$240.00");

    const modelTargetLabel = await screen.findByText("5D Model Target");
    const modelTargetValue = modelTargetLabel.nextElementSibling;
    expect(modelTargetValue).toHaveTextContent("$225.00");
    expect(modelTargetValue?.textContent).not.toBe(myTargetValue?.textContent);
  });

  it("shows a placeholder (not $0 or a blank card) and hides the model section when prediction is unavailable", async () => {
    vi.spyOn(api, "getPrediction").mockRejectedValue(new api.ApiError("not found", 404));

    render(<PositionCard position={makePosition()} onEdit={() => {}} onDelete={() => {}} />);

    expect(await screen.findByText("Model signal unavailable for this ticker.")).toBeInTheDocument();
    // No quote prop provided -- must show a safe placeholder, never $0.
    expect(screen.queryByText("$0.00")).not.toBeInTheDocument();
  });

  it("shows the stale-price warning when the quote falls back to a locally stored price", async () => {
    vi.spyOn(api, "getPrediction").mockResolvedValue(makeMultiHorizonPrediction());
    const staleQuote = makeQuoteResult({ price: 213.9, is_stale: true, source: "LAST_STORED_PRICE" });

    render(<PositionCard position={makePosition()} quote={staleQuote} onEdit={() => {}} onDelete={() => {}} />);

    expect(await screen.findByText("$213.90")).toBeInTheDocument();
    expect(screen.getByText(/Price may be outdated/)).toBeInTheDocument();
  });
});
