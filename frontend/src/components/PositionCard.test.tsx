import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import PositionCard from "./PositionCard";
import { makeMultiHorizonPrediction, makePosition } from "@/lib/testFixtures";
import * as api from "@/lib/api";

describe("PositionCard", () => {
  it("computes cost, current value, profit, and return from shares/prices", async () => {
    vi.spyOn(api, "getPrediction").mockResolvedValue(
      makeMultiHorizonPrediction({ current_price: 218.29 })
    );

    const position = makePosition({ shares: 20, purchase_price: 190 });
    render(<PositionCard position={position} onEdit={() => {}} onDelete={() => {}} />);

    // cost = 20 * 190 = 3800
    expect(await screen.findByText("$3,800.00")).toBeInTheDocument();

    // current value = 20 * 218.29 = 4365.80
    await waitFor(() => expect(screen.getByText("$4,365.80")).toBeInTheDocument());

    // profit = 4365.80 - 3800 = +565.80
    expect(screen.getByText("+$565.80")).toBeInTheDocument();
  });

  it("keeps My Target (user's own) visually and numerically separate from the model's target", async () => {
    vi.spyOn(api, "getPrediction").mockResolvedValue(makeMultiHorizonPrediction());

    const position = makePosition({ my_target_price: 240 });
    render(<PositionCard position={position} onEdit={() => {}} onDelete={() => {}} />);

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

  it("falls back to a plain current price and hides the model section when prediction is unavailable", async () => {
    vi.spyOn(api, "getPrediction").mockRejectedValue(new api.ApiError("not found", 404));
    vi.spyOn(api, "getPositionCurrentPrice").mockResolvedValue(218.29);

    render(<PositionCard position={makePosition()} onEdit={() => {}} onDelete={() => {}} />);

    expect(await screen.findByText("Model signal unavailable for this ticker.")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("$218.29")).toBeInTheDocument());
  });
});
