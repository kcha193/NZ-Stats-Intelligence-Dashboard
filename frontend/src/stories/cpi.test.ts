import { describe, expect, it } from "vitest";
import type { CpiDashboard } from "@/api/types";
import cpiFixture from "@/test/fixtures/cpi.json";
import { buildCpiStories } from "./cpi";

const cpi = cpiFixture as unknown as CpiDashboard;
const byTemplate = (data: CpiDashboard) => new Map(buildCpiStories(data).map((s) => [s.template, s]));

describe("CPI stories", () => {
  it("builds three stories with stable period-based identifiers and the release provenance", () => {
    const stories = buildCpiStories(cpi);
    expect(stories.map((s) => s.id)).toEqual([
      "inflation-annual-2026-06", "inflation-drivers-2026-06", "inflation-tradables-2026-06",
    ]);
    for (const s of stories) {
      expect(s.category).toBe("inflation");
      expect(s.provenance).toMatchObject({
        releaseId: 2, releaseKey: "consumers-price-index:june 2026 quarter", publishedAt: "2026-07-21T10:45:00+12:00",
        pageUrl: "https://www.stats.govt.nz/information-releases/consumers-price-index-june-2026-quarter/",
      });
      expect(s.referenceLabel).toBe("June 2026 quarter");
      expect(s.dashboard.to).toBe("/inflation");
      expect(s.methodology.length).toBeGreaterThan(0);
    }
  });

  it("headlines annual inflation with the published direction and precision", () => {
    const s = byTemplate(cpi).get("inflation-annual")!;
    expect(s.headline).toBe("Annual inflation rises to 4.1%");
    expect(s.stat).toMatchObject({ value: "4.1%", unit: "annual change in the CPI" });
    expect(s.dek).toContain("up from 3.1% in the March 2026 quarter");
    expect(s.context).toContain("Annual inflation was last this high in the December 2023 quarter (4.7%).");
    expect(s.context).toContain("A year earlier, in the June 2025 quarter, annual inflation was 2.7%, 1.4 percentage points lower than now.");
    expect(s.explanation.join(" ").match(/1\.5%/g)).toHaveLength(1);
    expect(s.caveats.join(" ")).toMatch(/reference only and is not a forecast/);
    expect(s.evidence.map((e) => e.period)).toEqual(["2026-06", "2026-03", "2025-06", "2023-12"]);
    expect(s.figure.kind).toBe("cpi-annual");
  });

  it("says 'eases' and 'holds' only when the displayed rate does", () => {
    const withLatest = (annual: number) => {
      const series = cpi.series.map((x) => x.slug === "all_groups" && x.adjustment === "none"
        ? { ...x, points: [...x.points.slice(0, -1), { ...x.points.at(-1)!, annual_pct: annual }] } : x);
      return byTemplate({ ...cpi, series }).get("inflation-annual")!.headline;
    };
    expect(withLatest(2.5)).toBe("Annual inflation eases to 2.5%");
    expect(withLatest(3.11)).toBe("Annual inflation holds at 3.1%");
  });

  it("reports contributions in percentage points, keeps signs, and never calls them price changes", () => {
    const s = byTemplate(cpi).get("inflation-drivers")!;
    expect(s.headline).toBe("Transport made the largest contribution to quarterly inflation of 1.5%");
    expect(s.stat).toMatchObject({ value: "+0.82 pp", unit: "percentage points", sign: "positive" });
    expect(s.dek).toContain("Housing and household utilities (+0.31 pp)");
    expect(s.context.join(" ")).toContain("Miscellaneous goods and services (−0.01 pp)");
    expect(s.caveats.join(" ")).toMatch(/not the group's own price change/);
    expect(s.thumb).toMatchObject({ kind: "bars" });
  });

  it("omits the drivers story when the published contributions are unavailable", () => {
    const contributions = cpi.contributions.map((b) => (b.horizon === "quarterly" ? { ...b, available: false, items: [] } : b));
    expect(byTemplate({ ...cpi, contributions }).has("inflation-drivers")).toBe(false);
  });

  it("compares tradables and non-tradables on the same annual measure", () => {
    const s = byTemplate(cpi).get("inflation-tradables")!;
    expect(s.headline).toBe("Tradables inflation (4.9%) runs ahead of non-tradables (3.4%)");
    expect(s.stat).toMatchObject({ value: "+1.5 pp", unit: "gap in annual inflation, tradables minus non-tradables" });
  });

  it("flags a corrected release in the caveats", () => {
    const analysis = { ...cpi.analysis, release: { ...cpi.analysis.release, status: "corrected" },
      corrections: { ...cpi.analysis.corrections, available: true, note: "Stats NZ corrected the index file." } };
    const s = buildCpiStories({ ...cpi, analysis })[0];
    expect(s.caveats[0]).toBe("Corrected release: Stats NZ corrected the index file.");
  });

  it("returns nothing when the headline series is missing", () => {
    expect(buildCpiStories({ ...cpi, series: [] })).toEqual([]);
  });
});
