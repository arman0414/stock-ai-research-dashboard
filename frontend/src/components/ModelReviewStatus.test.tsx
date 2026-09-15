import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import ModelReviewStatus from "./ModelReviewStatus";

describe("ModelReviewStatus", () => {
  it("shows NOT TRAINED YET with no progress bar when no champion exists", () => {
    render(<ModelReviewStatus status={{ horizon: "5d", resolved_new_live_predictions: 0, threshold: 100, status: "NOT_TRAINED" }} />);
    expect(screen.getByText("NOT TRAINED YET")).toBeInTheDocument();
    expect(screen.queryByText(/of 100 new resolved/)).not.toBeInTheDocument();
  });

  it("shows COLLECTING DATA with progress below the threshold", () => {
    render(<ModelReviewStatus status={{ horizon: "5d", model_version: "v1", resolved_new_live_predictions: 37, threshold: 100, status: "COLLECTING_DATA" }} />);
    expect(screen.getByText("COLLECTING DATA")).toBeInTheDocument();
    expect(screen.getByText(/37 of 100 new resolved 5d live forecasts/)).toBeInTheDocument();
  });

  it("shows READY FOR MODEL REVIEW at the threshold, and never claims auto-promotion", () => {
    const { container } = render(<ModelReviewStatus status={{ horizon: "5d", model_version: "v1", resolved_new_live_predictions: 100, threshold: 100, status: "READY_FOR_MODEL_REVIEW" }} />);
    expect(screen.getByText("READY FOR MODEL REVIEW")).toBeInTheDocument();
    expect(container.textContent).toMatch(/manual review/i);
    expect(container.textContent).not.toMatch(/auto.?promot|automatically retrain/i);
  });
});
