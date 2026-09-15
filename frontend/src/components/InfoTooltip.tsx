export default function InfoTooltip({ text }: { text: string }) {
  return (
    <span
      data-testid="info-tooltip"
      tabIndex={0}
      title={text}
      aria-label={text}
      role="img"
      className="ml-1 inline-flex h-4 w-4 shrink-0 cursor-help select-none items-center justify-center rounded-full bg-gray-200 align-middle text-[10px] font-semibold text-gray-500"
    >
      ?
    </span>
  );
}
