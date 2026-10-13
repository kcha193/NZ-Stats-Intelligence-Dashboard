import type { CountryRank } from "@/api/types";
import type { ChartPoint } from "./options";

type Column = { value: string; status: string };

/** Rows for two series side by side. Each series keeps its own status column (a final month can sit
 * inside a provisional year-ended total), and a period present in only one series is not dropped. */
export function pairedCsvRows(a: Column, aPoints: ChartPoint[], b: Column, bPoints: ChartPoint[]) {
  const pa = new Map(aPoints.map((p) => [p.period, p]));
  const pb = new Map(bPoints.map((p) => [p.period, p]));
  return [...new Set([...pa.keys(), ...pb.keys()])].sort().map((period) => ({
    period,
    [a.value]: pa.get(period)?.value ?? null,
    [a.status]: pa.get(period)?.status ?? null,
    [b.value]: pb.get(period)?.value ?? null,
    [b.status]: pb.get(period)?.status ?? null,
  }));
}

export const combinedNetCsvRows = (monthly: ChartPoint[], yearEnded: ChartPoint[]) =>
  pairedCsvRows(
    { value: "monthly_net", status: "monthly_status" }, monthly,
    { value: "year_ended_net", status: "year_ended_status" }, yearEnded,
  );

/** Country ranking rows; the prior window has its own provisional flag (empty when withheld). */
export const countryCsvRows = (countries: CountryRank[]) =>
  countries.map((c) => ({
    country: c.name,
    arrivals_12m: c.value,
    includes_provisional: c.provisional ? "yes" : "no",
    share_percent: c.share_percent,
    prior_12m: c.prior_value,
    prior_includes_provisional: c.prior_provisional == null ? null : c.prior_provisional ? "yes" : "no",
  }));

/** Suffix for a chart title whose headline value is provisional (or of unknown status). */
export function statusNote(statuses: (string | undefined)[]): string {
  if (statuses.includes("provisional")) return ", provisional";
  return statuses.includes("unknown") ? ", status unknown" : "";
}
