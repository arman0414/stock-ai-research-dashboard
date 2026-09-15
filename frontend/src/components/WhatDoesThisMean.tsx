export default function WhatDoesThisMean() {
  return (
    <details data-testid="what-does-this-mean" className="rounded-xl border border-gray-200 bg-white">
      <summary className="cursor-pointer select-none px-4 py-2.5 text-sm font-medium text-gray-700">What does this prediction mean?</summary>
      <div className="border-t border-gray-100 px-4 py-3 text-sm text-gray-600">
        <ul className="space-y-2">
          <li>
            <span className="font-semibold text-gray-900">Model Target</span> is the model&apos;s estimated stock price at the end of the selected trading-day horizon.
          </li>
          <li>
            <span className="font-semibold text-gray-900">Expected Range</span> shows how large the model&apos;s historical prediction errors have been.
          </li>
          <li>
            <span className="font-semibold text-gray-900">Model Confidence</span> is the calibrated confidence in the predicted direction.
          </li>
          <li>
            <span className="font-semibold text-gray-900">NO STRONG SIGNAL</span> means the prediction does not currently satisfy our historically validated signal requirements.
          </li>
        </ul>
      </div>
    </details>
  );
}
