import type { HorizonPrediction, MarketContext, SentimentSummary } from "@/lib/types";
import { OVERALL_SETUP_LABELS, buildResearchChecklist, getResearchStrength, overallSetupState, type ChecklistStatus } from "@/lib/researchStrength";

const ICON: Record<ChecklistStatus, string> = { GOOD: "✓", WARNING: "⚠", NEUTRAL: "○" };
const ICON_COLOR: Record<ChecklistStatus, string> = { GOOD: "text-green-600", WARNING: "text-amber-600", NEUTRAL: "text-gray-300" };

const OVERALL_STYLES: Record<string, string> = {
  STRONG_RESEARCH_SETUP: "bg-green-100 text-green-800 border-green-200",
  WORTH_WATCHING: "bg-blue-50 text-blue-700 border-blue-200",
  MIXED_SETUP: "bg-amber-50 text-amber-700 border-amber-200",
  NO_STRONG_SIGNAL: "bg-gray-100 text-gray-600 border-gray-200",
};

export default function ResearchChecklist({
  prediction,
  marketContext,
  sentiment,
}: {
  prediction: HorizonPrediction;
  marketContext: MarketContext;
  sentiment: SentimentSummary | null;
}) {
  const checklist = buildResearchChecklist(prediction, marketContext, sentiment);
  const strength = getResearchStrength(prediction);
  const overall = overallSetupState(strength, checklist);

  return (
    <div data-testid="research-checklist" className="rounded-xl border border-gray-200 bg-white p-4">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">Research Checklist</h2>
      <ul className="mt-3 space-y-1.5 text-sm text-gray-700">
        {checklist.map((item) => (
          <li key={item.label} className="flex items-center gap-2">
            <span className={`w-4 text-center font-semibold ${ICON_COLOR[item.status]}`}>{ICON[item.status]}</span>
            {item.label}
          </li>
        ))}
      </ul>

      <div className="mt-4 flex items-center gap-2 border-t border-gray-100 pt-3">
        <span className="text-xs font-medium uppercase tracking-wide text-gray-400">Overall</span>
        <span data-testid="overall-setup-state" className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-wide ${OVERALL_STYLES[overall]}`}>
          {OVERALL_SETUP_LABELS[overall]}
        </span>
      </div>
    </div>
  );
}
