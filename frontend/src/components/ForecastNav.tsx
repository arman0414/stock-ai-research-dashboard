import Link from "next/link";
import type { Horizon } from "@/lib/types";
import { HORIZONS } from "@/lib/types";
import { horizonDayCount } from "@/lib/format";

export default function ForecastNav({ current }: { current: Horizon }) {
  return (
    <nav data-testid="forecast-nav" className="flex flex-wrap gap-2">
      {HORIZONS.map((horizon) => {
        const active = horizon === current;
        return (
          <Link
            key={horizon}
            href={`/forecast/${horizon}`}
            aria-current={active ? "page" : undefined}
            className={`rounded-md px-3 py-1.5 text-sm font-semibold ${active ? "bg-gray-900 text-white" : "border border-gray-200 text-gray-600 hover:bg-gray-50"}`}
          >
            {horizonDayCount(horizon)} Days
          </Link>
        );
      })}
    </nav>
  );
}
