import "@testing-library/jest-dom/vitest";
import React from "react";
import { vi } from "vitest";

// next/link relies on an App Router context that isn't mounted in isolated
// component tests; replace it with a plain anchor so click/href behavior is
// still testable without pulling in the whole router.
vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode } & Record<string, unknown>) =>
    React.createElement("a", { href, ...rest }, children),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
}));
