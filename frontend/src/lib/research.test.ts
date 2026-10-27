import { describe, expect, it } from "vitest";
import type { ForecastGroup, Kpi } from "@/api/types";
import { horizonEnd, observationFor } from "./research";

// SYNTHETIC FIXTURE group; the KPI shape is the overview's.
const group = (horizon_key: string, over: Partial<ForecastGroup> = {}) =>
  ({ indicator: "cpi_inflation", basis: "annual_change", unit: "percent", horizon_key, ...over }) as ForecastGroup;
const cpi = { published_at: "2026-07-21T10:45:00+12:00", metric: { value: 4.058, period: "2026-06", period_label: "Quarter ended June 2026" } } as Kpi;

describe("official reference line", () => {
  it.each([
    ["quarter:2027-03", "2027-03"], ["year_to:2026-06", "2026-06"], ["month:2026-12", "2026-12"],
    ["calendar:2027", "2027-12"], ["split:2026/27", "2027-01"], ["relative:soon", null],
  ])("knows when %s ends", (key, end) => expect(horizonEnd(key)).toBe(end));

  it("is drawn only for a target after the latest observed quarter", () => {
    expect(observationFor(group("year_to:2027-06"), cpi)?.value).toBe(4.058);
    expect(observationFor(group("year_to:2026-06"), cpi)).toBeNull(); // the same quarter: its own outcome, not a reference
    expect(observationFor(group("year_to:2026-03"), cpi)).toBeNull(); // never a later quarter standing in for an earlier one
  });

  it("is never drawn for another statistic", () => {
    expect(observationFor(group("year_to:2027-06", { basis: "annual_average_change" }), cpi)).toBeNull();
    expect(observationFor(group("year_to:2027-06", { indicator: "ocr" }), cpi)).toBeNull();
  });
});
