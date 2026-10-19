import { describe, expect, it } from "vitest";
import type { CpiContributionBlock, CpiPoint, CpiSeries } from "@/api/types";
import { toCsv } from "@/lib/csv";
import {
  addQuarters, annualInflationOption, componentOption, contributionCsvRows, contributionOption,
  historyCsvRows, quarterAxis, quarterlyInflationOption, rangeFilter, tradablesOption,
} from "./cpi";
import { TEST_THEME } from "./theme";

// Published Stats NZ index numbers (base June 2017 = 1000), June 2023 to June 2026.
const ALL = { "2023-06": 1231, "2023-09": 1253, "2023-12": 1259, "2024-03": 1267, "2024-06": 1272, "2024-09": 1280, "2024-12": 1287, "2025-03": 1299, "2025-06": 1306, "2025-09": 1319, "2025-12": 1327, "2026-03": 1339, "2026-06": 1359 };
const TRAD = { "2023-06": 1180, "2023-09": 1201, "2023-12": 1198, "2024-03": 1190, "2024-06": 1184, "2024-09": 1182, "2024-12": 1185, "2025-03": 1194, "2025-06": 1198, "2025-09": 1208, "2025-12": 1216, "2026-03": 1224, "2026-06": 1257 };
const NON = { "2023-06": 1272, "2023-09": 1294, "2023-12": 1308, "2024-03": 1329, "2024-06": 1341, "2024-09": 1358, "2024-12": 1367, "2025-03": 1382, "2025-06": 1391, "2025-09": 1406, "2025-12": 1415, "2026-03": 1430, "2026-06": 1438 };

const points = (levels: Record<string, number>): CpiPoint[] =>
  Object.entries(levels).map(([period, index]) => {
    const rate = (lag: number) => {
      const earlier = levels[addQuarters(period, -lag)];
      return earlier === undefined ? null : (index / earlier - 1) * 100;
    };
    return { period, index, quarterly_pct: rate(1), annual_pct: rate(4) };
  });
const series = (name: string, levels: Record<string, number>): CpiSeries => ({
  key: "cpi.index.nsa.all_groups", slug: "all_groups", name, unit: "index", adjustment: "none",
  classification: "All groups", source_reference: "CPIQ.SE9A", status: "final", points: points(levels), source_url: null,
});
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const opt = (o: unknown) => o as any;

describe("axis and range", () => {
  it("keeps a missing quarter on the axis so lines break there", () => {
    expect(quarterAxis(["2025-03", "2025-12"])).toEqual(["2025-03", "2025-06", "2025-09", "2025-12"]);
  });
  it("returns the last N quarters or everything", () => {
    const all = points(ALL);
    expect(rangeFilter(all, "3y")).toHaveLength(12);
    expect(rangeFilter(all, "3y")[0].period).toBe("2023-09");
    expect(rangeFilter(all, "full")).toHaveLength(13);
    expect(rangeFilter([], "5y")).toEqual([]);
  });
});

describe("headline inflation charts", () => {
  it("draws annual inflation with a zero line, latest marker, unconnected gaps and the reference band", () => {
    const option = opt(annualInflationOption(points(ALL), TEST_THEME, { band: true }));
    const s = option.series[0];
    expect(option.yAxis.name).toBe("Annual change (%)");
    expect(s.connectNulls).toBe(false);
    expect(s.data.slice(0, 4)).toEqual([null, null, null, null]);
    expect(s.markLine.data).toEqual([{ yAxis: 0 }]);
    expect(s.markPoint.data[0].coord[0]).toBe("2026-06");
    expect(s.markPoint.label.formatter()).toBe("4.1%");
    expect(s.markArea.data).toEqual([[{ yAxis: 1 }, { yAxis: 3 }]]);
    expect(s.markArea.label.formatter).toMatch(/1% to 3% target band \(reference\)/);
    expect(opt(annualInflationOption(points(ALL), TEST_THEME)).series[0].markArea).toBeUndefined();
  });
  it("does not bridge a missing observation", () => {
    const without = Object.fromEntries(Object.entries(ALL).filter(([p]) => p !== "2025-12"));
    const option = opt(annualInflationOption(points(without), TEST_THEME));
    expect(option.xAxis.data).toContain("2025-12");
    expect(option.series[0].data[option.xAxis.data.indexOf("2025-12")]).toBeNull();
  });
  it("draws quarterly inflation as signed bars with a zero line", () => {
    const option = opt(quarterlyInflationOption(points(TRAD), TEST_THEME));
    const s = option.series[0];
    expect(s.type).toBe("bar");
    expect(option.yAxis.name).toBe("Quarterly change (%)");
    expect(s.markLine.data).toEqual([{ yAxis: 0 }]);
    const negative = s.data[option.xAxis.data.indexOf("2024-03")];
    expect(negative.value).toBeLessThan(0);
    expect(negative.itemStyle.color).toBe(TEST_THEME.negative);
    expect(s.data.at(-1).itemStyle.color).toBe(TEST_THEME.positive);
  });
});

describe("tradables and non-tradables", () => {
  it.each([["annual", "Annual change (%)"], ["quarterly", "Quarterly change (%)"]] as const)("compares both on one %s axis with direct labels", (horizon, name) => {
    const option = opt(tradablesOption(points(TRAD), points(NON), horizon, TEST_THEME));
    expect(option.series.map((s: { name: string }) => s.name)).toEqual(["Tradables", "Non-tradables"]);
    expect(option.series.every((s: { endLabel: { show: boolean } }) => s.endLabel.show)).toBe(true);
    expect(option.legend).toBeUndefined();
    expect(Array.isArray(option.yAxis)).toBe(false);
    expect(option.yAxis.name).toBe(name);
    expect(option.series[0].markLine.data).toEqual([{ yAxis: 0 }]);
  });
});

describe("contributions", () => {
  const block: CpiContributionBlock = {
    horizon: "quarterly", available: true, reference_period: "2026-06", unit: "percentage points",
    sum_points: 1.4, headline_pct: 1.494, gap_points: 0.094, note: "",
    items: [["food", "Food", 0.076], ["transport", "Transport", 0.824], ["miscellaneous", "Miscellaneous goods and services", -0.009], ["housing", "Housing and household utilities", 0.305]]
      .map(([slug, group, points], i) => ({ slug: slug as string, group: group as string, points: points as number, rank: i + 1 })),
  };
  it("ranks groups by published percentage points with signed labels", () => {
    const option = opt(contributionOption(block, TEST_THEME));
    const s = option.series[0];
    expect(option.xAxis.name).toBe("Percentage points");
    expect(option.yAxis.data).toEqual(["Transport", "Housing and household utilities", "Food", "Miscellaneous goods and services"]);
    expect(s.label.formatter({ value: 0.824 })).toBe("+0.82");
    expect(s.label.formatter({ value: -0.009 })).toBe("−0.01");
    expect(s.data.at(-1).itemStyle.color).toBe(TEST_THEME.negative);
    expect(option.xAxis.min).toBeLessThan(0);
    expect(option.tooltip.formatter({ name: "Transport", value: 0.824 })).toContain("percentage points");
  });
  it("exports published values with the unit and the gap to the headline", () => {
    const rows = contributionCsvRows(block, { releaseKey: "k", sourceUrl: "https://x" });
    expect(rows[0]).toMatchObject({ rank: 1, group: "Food", unit: "percentage points", gap_percentage_points: 0.094 });
  });
});

describe("component explorer", () => {
  const s = series("Food", ALL);
  it("switches between index, quarterly and annual views", () => {
    const index = opt(componentOption(s, "index", "full", TEST_THEME));
    expect(index.yAxis.name).toMatch(/June 2017 = 1000/);
    expect(index.yAxis.min).toBeGreaterThan(0);
    expect(index.yAxis.min).toBeLessThan(1231);
    expect(opt(componentOption(s, "quarterly", "full", TEST_THEME)).series[0].type).toBe("bar");
    expect(opt(componentOption(s, "annual", "full", TEST_THEME)).series[0].type).toBe("line");
    expect(opt(componentOption(s, "annual", "3y", TEST_THEME)).xAxis.data).toHaveLength(12);
  });
  it("escapes upstream names in tooltips", () => {
    const hostile = series("<img src=x onerror=alert(1)>", ALL);
    const text = opt(componentOption(hostile, "annual", "full", TEST_THEME)).tooltip.formatter([{ axisValue: "2026-06" }]);
    expect(text).not.toContain("<img");
    expect(text).toContain("&lt;img");
  });
});

describe("csv export", () => {
  it("carries provenance and neutralises spreadsheet formulas", () => {
    const hostile = series('=HYPERLINK("http://x")', ALL);
    const rows = historyCsvRows(hostile, hostile.points, { releaseKey: "consumers-price-index:june 2026 quarter", sourceUrl: null });
    expect(rows[0]).toMatchObject({ unit: "index", source_reference: "CPIQ.SE9A", base: "June 2017 quarter (=1000)" });
    expect(toCsv(rows)).toContain("'=HYPERLINK");
    expect(rows.at(-1)).toMatchObject({ period: "2026-06", index: 1359 });
  });
});
