import { describe, expect, it } from "vitest";
import type { EvaluatedForecast, ForecastGroup, ForecastSeries, Kpi } from "@/api/types";
import { cpiMeasureFor, horizonEnd, matchedOutcomeFor, observationFor } from "./research";

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

// SYNTHETIC FIXTURE series and evaluation rows; the shapes are the API's (`basis` from the history, `measure` from the evaluation).
const series = (basis: string, summaryIds: number[], over: Partial<ForecastSeries> = {}) =>
  ({ indicator: "cpi_inflation", basis, horizon_key: "quarter:2026-06", kind: "central", vintages: summaryIds.map((summary_id) => ({ summary_id })), ...over }) as ForecastSeries;
const row = (measure: string, summaryId: number, over: Partial<EvaluatedForecast> = {}) =>
  ({ measure, target_quarter: "2026-06", status: "matched", forecast: { summary_id: summaryId }, first: { value: 1.5, first_release: true }, ...over }) as EvaluatedForecast;

describe("CPI history basis to official evaluation measure", () => {
  it.each([
    ["annual_change", "annual_change"],
    ["annual_average_change", "annual_average_change"],
    ["quarterly_change:unadjusted", "quarterly_change_nsa"],
    ["quarterly_change", "quarterly_change_sa"], // the history drops "seasonally adjusted"; the evaluation confirms it per forecast
  ])("maps %s to %s", (basis, measure) => expect(cpiMeasureFor(series(basis, []))).toBe(measure));

  it.each(["quarterly_change:auckland", "annual_change:auckland", "quarterly_change_nsa", "quarterly_change:unadjusted-auckland", "constructor", ""])(
    "has no measure for the unsupported basis %j", (basis) => expect(cpiMeasureFor(series(basis, []))).toBeNull());

  it("has no measure for another indicator, even with a CPI-like basis", () => {
    expect(cpiMeasureFor(series("annual_change", [], { indicator: "gdp" }))).toBeNull();
  });
});

describe("the matched official outcome for a history series", () => {
  it("finds the unadjusted quarterly outcome that the old prefix match missed", () => {
    const found = matchedOutcomeFor(series("quarterly_change:unadjusted", [1]), [row("quarterly_change_nsa", 1)]);
    expect(found?.measure).toBe("quarterly_change_nsa");
  });

  it("keeps seasonally adjusted and unadjusted quarterly outcomes apart", () => {
    const evaluated = [row("quarterly_change_nsa", 1, { first: { value: 1.2 } as EvaluatedForecast["first"] }), row("quarterly_change_sa", 2)];
    expect(matchedOutcomeFor(series("quarterly_change:unadjusted", [1]), evaluated)?.measure).toBe("quarterly_change_nsa");
    expect(matchedOutcomeFor(series("quarterly_change", [2]), evaluated)?.measure).toBe("quarterly_change_sa");
  });

  it.each(["annual_change", "annual_average_change"])("matches %s on its own measure only", (basis) => {
    const evaluated = [row("quarterly_change_nsa", 1), row(basis, 1)];
    expect(matchedOutcomeFor(series(basis, [1]), evaluated)?.measure).toBe(basis);
    expect(matchedOutcomeFor(series(basis, [1]), [row("annual_change" === basis ? "annual_average_change" : "annual_change", 1)])).toBeNull();
  });

  it("shows no outcome for an unqualified quarterly change the evaluation did not match as seasonally adjusted", () => {
    // Another institution's seasonally adjusted forecast (summary 9) shares the target; this series' own (summary 1) was not matched.
    expect(matchedOutcomeFor(series("quarterly_change", [1]), [row("quarterly_change_sa", 9)])).toBeNull();
  });

  it("needs a matched row for the right target quarter, never pending, and never for a scenario", () => {
    expect(matchedOutcomeFor(series("annual_change", [1]), [row("annual_change", 1, { status: "pending", first: null })])).toBeNull();
    expect(matchedOutcomeFor(series("annual_change", [1]), [row("annual_change", 1, { target_quarter: "2026-03" })])).toBeNull();
    expect(matchedOutcomeFor(series("annual_change", [1], { kind: "scenario" }), [row("annual_change", 1)])).toBeNull();
  });
});
