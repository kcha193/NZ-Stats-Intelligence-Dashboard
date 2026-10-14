import { describe, expect, it } from "vitest";
import { combinedNetCsvRows, countryCsvRows, pairedCsvRows } from "./exports";
import { toCsv } from "@/lib/csv";
import type { ChartPoint } from "./options";

const pt = (period: string, value: number, status = "final"): ChartPoint => ({ period, value, status });

describe("combinedNetCsvRows", () => {
  it("exports the monthly and year-ended status in separate columns", () => {
    const rows = combinedNetCsvRows(
      [pt("2026-01", 100, "provisional"), pt("2026-02", 120)],
      [pt("2026-01", 1000, "provisional"), pt("2026-02", 1020, "provisional")],
    );
    expect(rows).toEqual([
      { period: "2026-01", monthly_net: 100, monthly_status: "provisional", year_ended_net: 1000, year_ended_status: "provisional" },
      { period: "2026-02", monthly_net: 120, monthly_status: "final", year_ended_net: 1020, year_ended_status: "provisional" },
    ]);
  });

  it("keeps year-ended totals whose month has no monthly estimate, with empty monthly cells", () => {
    const rows = combinedNetCsvRows([pt("2026-02", 120)], [pt("2026-01", 1000), pt("2026-02", 1020)]);
    expect(rows[0]).toEqual({ period: "2026-01", monthly_net: null, monthly_status: null, year_ended_net: 1000, year_ended_status: "final" });
    expect(rows).toHaveLength(2);
  });

  it("is empty when there is nothing to export", () => {
    expect(combinedNetCsvRows([], [])).toEqual([]);
  });
});

describe("pairedCsvRows", () => {
  const a = { value: "arrivals", status: "arrivals_status" };
  const b = { value: "departures", status: "departures_status" };

  it("gives each series its own status column", () => {
    const rows = pairedCsvRows(a, [pt("2026-07", 10, "provisional")], b, [pt("2026-07", 4, "final")]);
    expect(rows).toEqual([{ period: "2026-07", arrivals: 10, arrivals_status: "provisional", departures: 4, departures_status: "final" }]);
  });

  it("keeps periods that only one series has", () => {
    const rows = pairedCsvRows(a, [pt("2026-06", 9)], b, [pt("2026-07", 4)]);
    expect(rows.map((r) => [r.period, r.arrivals, r.departures])).toEqual([["2026-06", 9, null], ["2026-07", null, 4]]);
    expect(rows[1].arrivals_status).toBeNull();
  });
});

describe("countryCsvRows", () => {
  const base = { name: "Chile", series_key: "k", value: 5, prior_value: 3, change: 2, change_percent: 66.7, share_percent: 1, provisional: true };

  it("flags the prior window separately from the current one", () => {
    const [row] = countryCsvRows([{ ...base, prior_provisional: false }]);
    expect(row).toMatchObject({ includes_provisional: "yes", prior_12m: 3, prior_includes_provisional: "no" });
    expect(countryCsvRows([{ ...base, prior_provisional: true }])[0].prior_includes_provisional).toBe("yes");
  });

  it("leaves the prior flag empty when the prior window is withheld", () => {
    const [row] = countryCsvRows([{ ...base, prior_value: null, change: null, change_percent: null, prior_provisional: null }]);
    expect(row.prior_12m).toBeNull();
    expect(row.prior_includes_provisional).toBeNull();
  });
});

it("country CSV identifies the ranking window, denominator and exact bundle safely", () => {
  const provenance = { release_key: "k", title: "=unsafe", published_at: "2026-09-14T10:45:00+12:00", source_url: "https://www.stats.govt.nz/x/", captured_at: "2026-10-11T16:00:00+13:00", bundle_sha256: "abc" };
  const d = { available: true, months: 12, period_start: "2025-08", period_end: "2026-07", total: 100, countries: [], regions: [], unallocated: null, derived: true, note: "Derived monthly sum", provenance };
  const [row] = countryCsvRows([{ name: "Chile", series_key: "chile", value: 5, prior_value: null, change: null, change_percent: null, share_percent: 5, provisional: true, prior_provisional: null }], d);
  expect(row).toMatchObject({ series_key: "chile", period_start: "2025-08", period_end: "2026-07", months: 12, total_arrivals: 100, release_key: "k", release_title: "=unsafe", published_at: provenance.published_at, source_url: provenance.source_url, captured_at: provenance.captured_at, bundle_sha256: "abc", derivation_note: d.note });
  expect(toCsv([row])).toContain("'=unsafe");
});
