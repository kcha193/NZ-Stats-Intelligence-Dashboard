import type { CpiSeries } from "@/api/types";
import { formatNumber } from "@/lib/format";

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

/** `2026-03` as "March 2026" (monthLabel abbreviates, which reads badly in running text). */
export function fullMonth(period: string): string {
  const [y, m] = period.split("-").map(Number);
  return `${MONTHS[m - 1]} ${y}`;
}

export const rate = (v: number) => `${formatNumber(v, { decimals: 1 })}%`;
export const points = (v: number) => `${formatNumber(v, { signed: true, decimals: 1 })} percentage points`;

/** The official name without the "unadjusted index" suffix the API adds to every stored series name. */
export const plainName = (s: CpiSeries) => s.name.replace(/, (unadjusted|seasonally adjusted) index$/, "");
