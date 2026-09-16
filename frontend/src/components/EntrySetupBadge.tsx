import type { EntrySetupState } from "@/lib/types";

const TEXT: Record<EntrySetupState, string> = {
  GOOD_SETUP: "GOOD SETUP",
  WATCH: "WATCH",
  WAIT: "WAIT",
  INSUFFICIENT_DATA: "INSUFFICIENT DATA",
};

const STYLES: Record<EntrySetupState, string> = {
  GOOD_SETUP: "bg-green-100 text-green-800 border-green-200",
  WATCH: "bg-amber-50 text-amber-700 border-amber-200",
  WAIT: "bg-gray-100 text-gray-600 border-gray-200",
  INSUFFICIENT_DATA: "bg-gray-50 text-gray-400 border-gray-200",
};

/**
 * Compact Entry Setup indicator -- GOOD SETUP / WATCH / WAIT only, never
 * BUY/SELL, never a numeric score. Used on the Dashboard and anywhere a
 * full checklist would be too much detail; see EntrySetupChecklist for the
 * expanded "Why?" view.
 */
export default function EntrySetupBadge({ state, size = "md" }: { state: EntrySetupState; size?: "sm" | "md" }) {
  const sizeClasses = size === "sm" ? "px-2 py-0.5 text-[10px]" : "px-2.5 py-1 text-xs";
  return (
    <span data-testid="entry-setup-badge" data-state={state} className={`inline-flex items-center rounded-full border font-semibold uppercase tracking-wide ${sizeClasses} ${STYLES[state]}`}>
      {TEXT[state]}
    </span>
  );
}
