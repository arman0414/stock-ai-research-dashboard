export default function DecisionGuideHelp() {
  return (
    <details data-testid="decision-guide-help" className="rounded-xl border border-gray-200 bg-white">
      <summary className="cursor-pointer select-none px-4 py-2.5 text-sm font-medium text-gray-700">How to read model confidence</summary>
      <div className="border-t border-gray-100 px-4 py-3 text-sm text-gray-600">
        <ul className="space-y-1.5">
          <li>
            <span className="font-semibold text-gray-900">&lt;60%</span> — No Strong Signal
          </li>
          <li>
            <span className="font-semibold text-gray-900">60–65%</span> — Weak — monitor only
          </li>
          <li>
            <span className="font-semibold text-gray-900">65–70%</span> — Worth Watching — review chart/news/context
          </li>
          <li>
            <span className="font-semibold text-gray-900">70%+</span> — Strong Research Signal — review carefully before making a decision
          </li>
        </ul>
        <p className="mt-3 text-xs text-gray-500">
          Probability alone should not determine a trade. Check historical reliability, uncertainty, support/resistance, market context, and news.
        </p>
        <p className="mt-2 text-xs text-gray-500">
          <span className="font-semibold text-gray-700">Model Lean</span> is the direction the model favors. A{" "}
          <span className="font-semibold text-gray-700">Validated Signal</span> (Bullish/Bearish) only appears once that lean also clears a
          historically-validated confidence threshold with enough evidence — otherwise the dashboard shows{" "}
          <span className="font-semibold text-gray-700">No Strong Signal</span>, even if the model leans a direction.
        </p>
      </div>
    </details>
  );
}
