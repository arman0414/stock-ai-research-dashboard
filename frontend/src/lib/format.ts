export function formatCurrency(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString("en-US", { style: "currency", currency: "USD", minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatSignedPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${(value * 100).toFixed(digits)}%`;
}

export function formatSignedCurrency(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatCurrency(value, digits)}`;
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("en-US", { year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

export function horizonDayCount(horizon: string): number {
  return parseInt(horizon, 10) || 0;
}

/** "5 Trading Days" */
export function horizonTradingDaysLabel(horizon: string): string {
  return `${horizonDayCount(horizon)} Trading Days`;
}

/** "5 TRADING DAYS" */
export function horizonTradingDaysLabelUpper(horizon: string): string {
  return horizonTradingDaysLabel(horizon).toUpperCase();
}

/** "5D" -- compact badge only, never used as the sole timeframe label. */
export function horizonShortBadge(horizon: string): string {
  return horizon.toUpperCase();
}

const TRADING_DAYS_APPROXIMATION: Record<string, string> = {
  "5d": "approximately one market week",
  "10d": "approximately two market weeks",
  "15d": "approximately three market weeks",
};

export function tradingDaysTooltip(horizon: string): string {
  const approx = TRADING_DAYS_APPROXIMATION[horizon] ?? "a span of upcoming trading sessions";
  return `${horizonTradingDaysLabel(horizon)} usually means ${approx} and does not include weekends or market holidays.`;
}

/** How far `lower` sits below `current`, as a positive fraction (0.09 = 9% below). */
export function percentBelow(current: number, lower: number): number {
  if (!current) return 0;
  return (current - lower) / current;
}

/** How far `higher` sits above `current`, as a positive fraction (0.009 = 0.9% above). */
export function percentAbove(current: number, higher: number): number {
  if (!current) return 0;
  return (higher - current) / current;
}
