import { formatNumber } from "@/lib/format";
import { fullMonth } from "@/pages/inflation/format";
import type { Sign } from "./types";

const shown = (v: number, decimals: number) => Number(v.toFixed(decimals)) || 0;

/** Direction of a change as a reader sees it: both values rounded to the displayed precision first. */
export function direction(current: number, previous: number, decimals: number): "up" | "down" | "flat" {
  const a = shown(current, decimals);
  const b = shown(previous, decimals);
  return a > b ? "up" : a < b ? "down" : "flat";
}

export function signOf(value: number, decimals: number): Sign {
  const v = shown(value, decimals);
  return v > 0 ? "positive" : v < 0 ? "negative" : "neutral";
}

export const rate = (v: number) => `${formatNumber(v, { decimals: 1 })}%`;
export const signedRate = (v: number) => `${formatNumber(v, { signed: true, decimals: 1 })}%`;
/** Contributions are published to two or three decimals; two is what Stats NZ shows in its tables. */
export const ppShort = (v: number, decimals = 2) => `${formatNumber(v, { signed: true, decimals })} pp`;
export const ppLong = (v: number) => `${formatNumber(v, { signed: true, decimals: 1 })} percentage points`;
export const people = (v: number) => formatNumber(Math.round(v));
export const signedPeople = (v: number) => formatNumber(Math.round(v), { signed: true });

export const quarterName = (period: string) => `${fullMonth(period)} quarter`;
export const yearEndedName = (period: string) => `year ended ${fullMonth(period)}`;
export const monthName = fullMonth;

type Pt = { period: string; value: number };

/** The most recent earlier point at or above the last point's value: "last this high in ...". */
export function lastAtLeast(points: Pt[]): Pt | null {
  const last = points.at(-1);
  if (!last) return null;
  for (let i = points.length - 2; i >= 0; i--) if (points[i].value >= last.value) return points[i];
  return null;
}

/** The most recent earlier point at or below the last point's value: "last this low in ...". */
export function lastAtMost(points: Pt[]): Pt | null {
  const last = points.at(-1);
  if (!last) return null;
  for (let i = points.length - 2; i >= 0; i--) if (points[i].value <= last.value) return points[i];
  return null;
}
