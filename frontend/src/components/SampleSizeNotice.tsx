import { SAMPLE_SIZE_DESCRIPTION, SAMPLE_SIZE_TEXT, sampleSizeLabel } from "@/lib/predictionAccuracy";

const STYLES: Record<string, string> = {
  EARLY_RESULTS: "bg-gray-100 text-gray-600 border-gray-200",
  LIMITED_LIVE_EVIDENCE: "bg-amber-50 text-amber-700 border-amber-200",
  MEANINGFUL_LIVE_SAMPLE: "bg-green-100 text-green-800 border-green-200",
};

export default function SampleSizeNotice({ resolvedCount }: { resolvedCount: number }) {
  const label = sampleSizeLabel(resolvedCount);
  return (
    <div data-testid="sample-size-notice" data-label={label} className="flex flex-wrap items-center gap-2 text-xs">
      <span className={`rounded-full border px-2 py-0.5 font-semibold uppercase tracking-wide ${STYLES[label]}`}>{SAMPLE_SIZE_TEXT[label]}</span>
      <span className="text-gray-500">{SAMPLE_SIZE_DESCRIPTION[label]}</span>
    </div>
  );
}
