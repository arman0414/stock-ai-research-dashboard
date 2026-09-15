export default function Disclaimer({ compact = false }: { compact?: boolean }) {
  return (
    <p data-testid="disclaimer" className={compact ? "text-xs text-gray-400" : "text-xs text-gray-500"}>
      Predictions are experimental research outputs and are not guarantees of future performance.
    </p>
  );
}
