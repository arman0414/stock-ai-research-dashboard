import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import ForecastNav from "./ForecastNav";

describe("ForecastNav", () => {
  it("links to all three horizon pages and highlights the current one", () => {
    render(<ForecastNav current="10d" />);

    const nav = screen.getByTestId("forecast-nav");
    expect(nav.querySelector('a[href="/forecast/5d"]')).toBeInTheDocument();
    expect(nav.querySelector('a[href="/forecast/10d"]')).toBeInTheDocument();
    expect(nav.querySelector('a[href="/forecast/15d"]')).toBeInTheDocument();

    const active = nav.querySelector('a[href="/forecast/10d"]');
    expect(active).toHaveAttribute("aria-current", "page");
    expect(nav.querySelector('a[href="/forecast/5d"]')).not.toHaveAttribute("aria-current");
  });
});
