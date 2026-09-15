import type { SignalStatus } from "@/lib/types";

const STYLES: Record<SignalStatus, string> = {
  BULLISH: "bg-green-100 text-green-800 border-green-200",
  BEARISH: "bg-red-100 text-red-800 border-red-200",
  NO_STRONG_SIGNAL: "bg-gray-100 text-gray-700 border-gray-200",
};

const LABELS: Record<SignalStatus, string> = {
  BULLISH: "Bullish",
  BEARISH: "Bearish",
  NO_STRONG_SIGNAL: "No Strong Signal",
};

/**
 * Renders exactly the signal_status the backend returned. There is no
 * frontend logic here that could independently decide "this looks bearish" --
 * that would violate the product rule that only a validated backend
 * threshold may produce a BEARISH/BULLISH call.
 */
export default function SignalBadge({ status, size = "md" }: { status: SignalStatus; size?: "sm" | "md" | "lg" }) {
  const sizeClasses = size === "lg" ? "px-4 py-1.5 text-base" : size === "sm" ? "px-2 py-0.5 text-xs" : "px-3 py-1 text-sm";
  return (
    <span
      data-testid="signal-badge"
      data-signal={status}
      className={`inline-flex items-center rounded-full border font-medium ${sizeClasses} ${STYLES[status]}`}
    >
      {LABELS[status]}
    </span>
  );
}
