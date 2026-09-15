import type { Explanation } from "@/lib/types";

export default function ExplanationPanel({ explanation }: { explanation: Explanation }) {
  if (explanation.positives.length === 0 && explanation.risks.length === 0) {
    return <p className="text-sm text-gray-400">No structural signals are currently available to explain this outlook.</p>;
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-green-700">Positive</p>
        {explanation.positives.length === 0 ? (
          <p className="mt-1 text-sm text-gray-400">Nothing notable right now.</p>
        ) : (
          <ul className="mt-1 space-y-1 text-sm text-gray-700">
            {explanation.positives.map((item, index) => (
              <li key={index} className="flex gap-1.5">
                <span className="text-green-600">•</span> {item}
              </li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-red-700">Risks</p>
        {explanation.risks.length === 0 ? (
          <p className="mt-1 text-sm text-gray-400">Nothing notable right now.</p>
        ) : (
          <ul className="mt-1 space-y-1 text-sm text-gray-700">
            {explanation.risks.map((item, index) => (
              <li key={index} className="flex gap-1.5">
                <span className="text-red-600">•</span> {item}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
