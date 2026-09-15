import { RESEARCH_STRENGTH_LABELS, RESEARCH_STRENGTH_STYLES, type ResearchStrengthLevel } from "@/lib/researchStrength";

export default function ResearchStrengthBadge({ level, size = "md" }: { level: ResearchStrengthLevel; size?: "sm" | "md" | "lg" }) {
  const sizeClasses = size === "lg" ? "px-3.5 py-1.5 text-sm" : size === "sm" ? "px-2 py-0.5 text-[11px]" : "px-3 py-1 text-xs";
  return (
    <span
      data-testid="research-strength-badge"
      data-strength={level}
      className={`inline-flex items-center rounded-full border font-semibold uppercase tracking-wide ${sizeClasses} ${RESEARCH_STRENGTH_STYLES[level]}`}
    >
      {RESEARCH_STRENGTH_LABELS[level]}
    </span>
  );
}
