import type { ChangeOut } from "@/api/types";
import { formatNumber, formatPercent } from "./format";

/** Rates (CPI inflation) are percentages; their changes are percentage points, never "percent of a percent". */
export const isRate = (unit: string) => unit === "percent";

const decimalsFor = (unit: string) => (isRate(unit) || unit === "NZD million" || unit === "NZD" ? 1 : 0);

export function formatMetricValue(value: number, unit: string): string {
  const text = formatNumber(value, { decimals: decimalsFor(unit) });
  return isRate(unit) ? `${text}%` : text;
}

export function formatChange(change: ChangeOut, unit: string): string {
  if (isRate(unit)) return `${formatNumber(change.absolute, { signed: true, decimals: 1 })} percentage points`;
  return `${formatNumber(change.absolute, { signed: true })} (${formatPercent(change.percent)})`;
}
