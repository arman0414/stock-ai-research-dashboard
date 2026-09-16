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

// jsdom does not implement ResizeObserver. Components (e.g. PriceChart) that
// observe their container for layout-only resizes need SOME implementation
// present, so tests exercise the real observe/disconnect lifecycle rather
// than crashing on a missing global.
class ResizeObserverStub implements ResizeObserver {
  static instances: ResizeObserverStub[] = [];
  readonly callback: ResizeObserverCallback;
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();

  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
    ResizeObserverStub.instances.push(this);
  }
}

(globalThis as unknown as { ResizeObserver: typeof ResizeObserverStub }).ResizeObserver = ResizeObserverStub;
(globalThis as unknown as { __ResizeObserverStub: typeof ResizeObserverStub }).__ResizeObserverStub = ResizeObserverStub;
