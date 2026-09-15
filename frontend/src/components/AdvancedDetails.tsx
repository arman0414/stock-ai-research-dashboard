import type { HorizonPrediction } from "@/lib/types";
import { formatPercent } from "@/lib/format";

export default function AdvancedDetails({ prediction }: { prediction: HorizonPrediction }) {
  const { classification, model, as_of } = prediction;
  return (
    <details data-testid="advanced-details" className="mt-3 rounded-md border border-gray-200 bg-gray-50 text-sm">
      <summary className="cursor-pointer select-none px-3 py-2 font-medium text-gray-600">Advanced Details</summary>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 px-3 pb-3 pt-1 text-gray-600 sm:grid-cols-3">
        <Row label="Raw probability" value={formatPercent(classification.raw_probability)} />
        <Row label="Calibration method" value={model.calibration_method} />
        <Row label="Classifier version" value={model.classification_version} />
        <Row label="Regressor version" value={model.regression_version} />
        <Row label="Feature date" value={as_of} />
        <Row label="Historical samples" value={classification.historical_signal_samples?.toString() ?? "—"} />
        <Row label="Gating reason" value={classification.gating_reason} />
      </dl>
    </details>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-gray-400">{label}</dt>
      <dd className="font-mono text-xs text-gray-700">{value}</dd>
    </div>
  );
}
