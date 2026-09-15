import "@testing-library/jest-dom/vitest";
import React from "react";
import { vi } from "vitest";

// next/link relies on an App Router context that isn't mounted in isolated
// component tests; replace it with a plain anchor so click/href behavior is
// still testable without pulling in the whole router.
vi.mock("next/link", () => ({
  default: ({ href, children, className }: { href: string; children: React.ReactNode; className?: string }) =>
    React.createElement("a", { href, className }, children),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
}));
