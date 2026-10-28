import type { ChartTableColumn } from "@/charts/ChartCard";
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

export const CPI_TABLE_NOTE = "Index base: June 2017 = 1000. Series identifiers, adjustment and release metadata are included in the CSV download; source and capture time are shown above.";

export const CPI_HISTORY_COLUMNS: readonly ChartTableColumn[] = [
  { key: "period", label: "Quarter ended" },
  { key: "series_name", label: "Series", format: (v) => String(v).replace(/, (unadjusted|seasonally adjusted) index$/, "") },
  { key: "index", label: "Index (June 2017 = 1000)", numeric: true, format: (v) => formatNumber(Number(v)) },
  { key: "quarterly_pct", label: "Quarterly change (%)", numeric: true, format: (v) => formatNumber(Number(v), { decimals: 1 }) },
  { key: "annual_pct", label: "Annual change (%)", numeric: true, format: (v) => formatNumber(Number(v), { decimals: 1 }) },
];

export const CPI_CONTRIBUTION_COLUMNS: readonly ChartTableColumn[] = [
  { key: "reference_period", label: "Quarter ended" },
  { key: "group", label: "Group" },
  { key: "contribution_percentage_points", label: "Contribution (percentage points)", numeric: true, format: (v) => formatNumber(Number(v), { decimals: 3 }) },
];
