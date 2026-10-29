import { describe, expect, it } from "vitest";
import gdp from "@/test/fixtures/gdp.json";
import labour from "@/test/fixtures/labour_market.json";
import type { GdpDashboard, LabourDashboard } from "@/api/types";
import { firstLatestOption, firstLatestRows, growthOption, rateOption } from "./macro";
import { TEST_THEME } from "./theme";

const g = gdp as unknown as GdpDashboard;
const l = labour as unknown as LabourDashboard;
const byKey = <T extends { key: string }>(list: T[], key: string) => list.find((s) => s.key === key)!;
type Opt = { series: { type: string; name: string; data: unknown[] }[]; legend?: { data: string[] }; tooltip: { formatter: (p: unknown) => string } };

describe("growthOption", () => {
  it("draws quarterly growth as signed bars and annual measures as a line, one measure per chart", () => {
    const q = growthOption(byKey(g.series, "gdp.production.cv.sa.pct_qoq"), "5y", TEST_THEME) as unknown as Opt;
    expect(q.series).toHaveLength(1);
    expect(q.series[0].type).toBe("bar");
    expect(q.series[0].data).toHaveLength(20);
    const negative = (q.series[0].data as { value: number; itemStyle: { color: string } }[]).find((d) => d && d.value < 0)!;
    expect(negative.itemStyle.color).toBe(TEST_THEME.negative);
    const a = growthOption(byKey(g.series, "gdp.production.cv.nsa.pct_annual_avg"), "5y", TEST_THEME) as unknown as Opt;
    expect(a.series[0].type).toBe("line");
    expect(a.series[0].name).toBe("Annual average GDP growth (production, real)");
  });
});

describe("rateOption", () => {
  it("keeps one rate on its own axis with the latest published value", () => {
    const o = rateOption(byKey(l.series, "hlfs.rate.unemployment.sa"), "full", TEST_THEME) as unknown as Opt;
    expect(o.series).toHaveLength(1);
    expect((o.series[0].data as (number | null)[]).at(-1)).toBe(5.6);
  });
});

describe("firstLatestOption", () => {
  const table = g.revisions[0];
  it("pairs first-published and latest values for each quarter, oldest first, with a legend", () => {
    const o = firstLatestOption(table, TEST_THEME, "%") as unknown as Opt;
    expect(o.series.map((s) => s.name)).toEqual(["Stored baseline", "Latest"]);
    expect(o.legend!.data).toEqual(["Stored baseline", "Latest"]);
    const quarters = [...table.rows].map((r) => r.period).sort();
    const march = quarters.indexOf("2026-03");
    expect((o.series[0].data as number[])[march]).toBe(0.8);
    expect((o.series[1].data as number[])[march]).toBe(0.9);
  });
  it("escapes upstream release titles in the tooltip and marks earliest-stored figures", () => {
    const hostile = { ...table, rows: table.rows.map((r) => ({ ...r, first_release: "<img src=x onerror=alert(1)>" })) };
    const o = firstLatestOption(hostile, TEST_THEME, "%") as unknown as Opt;
    const html = o.tooltip.formatter([{ dataIndex: 0 }]);
    expect(html).not.toContain("<img");
    expect(html).toContain("&lt;img");
    const rows = firstLatestRows(table, { releaseKey: "k", sourceUrl: null });
    expect(rows.some((r) => r.first_basis === "earliest stored")).toBe(true);
  });
});
