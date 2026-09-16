import type { EntrySetupReason, LiveEntrySetup } from "@/lib/types";
import { formatCurrency, formatSignedPercentPoints } from "@/lib/format";
import EntrySetupBadge from "./EntrySetupBadge";

const REASON_SYMBOL: Record<EntrySetupReason["symbol"], string> = { check: "✓", cross: "✕", warning: "⚠" };
const REASON_CLASS: Record<EntrySetupReason["symbol"], string> = { check: "text-green-700", cross: "text-red-600", warning: "text-amber-600" };

/**
 * Full Entry Setup display: state, research reward/risk, and a plain-
 * language "Why?" checklist -- never a wall of ML terminology, never a
 * numeric score. Entry Setup is an interpretation layer only: it never
 * alters the predicted price, return, or signal_status shown alongside it.
 */
export default function EntrySetupChecklist({ liveEntrySetup }: { liveEntrySetup: LiveEntrySetup }) {
  if (!liveEntrySetup.available || !liveEntrySetup.entry_setup) {
    return (
      <div data-testid="entry-setup-checklist" className="rounded-lg border border-gray-100 bg-gray-50 p-3 text-sm text-gray-400">
        {liveEntrySetup.reason ?? "Entry Setup is not available yet."}
      </div>
    );
  }

  const setup = liveEntrySetup.entry_setup;

  return (
    <div data-testid="entry-setup-checklist" className="rounded-lg border border-gray-100 p-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-gray-400">Entry Setup</span>
        <EntrySetupBadge state={setup.state} />
      </div>

      {setup.research_reward_risk !== null && (
        <p className="mt-2 text-sm text-gray-600">
          Research Reward/Risk: <span className="font-medium text-gray-900">{setup.research_reward_risk.toFixed(1)}x</span>
        </p>
      )}

      <details className="mt-2">
        <summary className="cursor-pointer select-none text-xs font-medium text-blue-700">Why {setup.state === "GOOD_SETUP" ? "GOOD SETUP" : setup.state.replace("_", " ")}?</summary>
        <ul data-testid="entry-setup-reasons" className="mt-2 space-y-1 text-sm text-gray-700">
          {setup.reasons.map((reason, index) => (
            <li key={index} className="flex items-start gap-1.5">
              <span className={`mt-0.5 ${REASON_CLASS[reason.symbol]}`} aria-hidden>
                {REASON_SYMBOL[reason.symbol]}
              </span>
              <span>{reason.text}</span>
            </li>
          ))}
        </ul>
        {setup.reward_target_price !== null && (
          <p className="mt-2 text-xs text-gray-400">Model Target used for reward: {formatCurrency(setup.reward_target_price)}</p>
        )}
        <p className="mt-2 text-[11px] italic text-gray-400">{setup.disclaimer}</p>
      </details>

      {liveEntrySetup.model_expected_move_pct != null && (
        <p className="mt-2 text-xs text-gray-400">Model Expected Move: {formatSignedPercentPoints(liveEntrySetup.model_expected_move_pct)}</p>
      )}
    </div>
  );
}
