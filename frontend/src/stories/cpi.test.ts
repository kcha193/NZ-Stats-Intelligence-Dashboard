import { describe, expect, it } from "vitest";
import type { CpiDashboard } from "@/api/types";
import cpiFixture from "@/test/fixtures/cpi.json";
import { buildCpiStories, contributionKey } from "./cpi";

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

describe("CPI evidence provenance", () => {
  const evidenceKeys = (insights: { evidence: { series_key: string }[] }[]) => new Set(insights.flatMap((i) => i.evidence.map((e) => e.series_key)));

  it("builds contribution keys the way the backend persists them", () => {
    expect(contributionKey("quarterly", "transport")).toBe("cpi.contrib.q.transport");
    expect(contributionKey("annual", "transport")).toBe("cpi.contrib.a.transport");
  });

  it("labels every quarterly contribution row with a persisted series key", () => {
    const s = byTemplate(cpi).get("inflation-drivers")!;
    const rows = s.evidence.filter((e) => e.label.endsWith("quarterly contribution"));
    const q = cpi.contributions.find((b) => b.horizon === "quarterly")!;
    expect(rows.map((e) => e.seriesKey)).toEqual(q.items.map((i) => `cpi.contrib.q.${i.slug}`));
    // The API's own analysis cites the same keys for the same values, so the story and the analysis agree on provenance.
    const cited = evidenceKeys(cpi.analysis.executive_summary as unknown as { evidence: { series_key: string }[] }[]);
    for (const slug of ["transport", "housing"]) expect(cited.has(`cpi.contrib.q.${slug}`)).toBe(true);
    expect(cited.has("cpi.contrib.a.transport")).toBe(true);
    expect(rows.find((e) => e.seriesKey === "cpi.contrib.q.transport")).toMatchObject({ period: "2026-06", value: 0.824 });
    expect(s.evidence.some((e) => e.seriesKey.startsWith("cpi.contribution"))).toBe(false);
  });

  it("cites the annual contribution it mentions under the persisted annual key", () => {
    const s = byTemplate(cpi).get("inflation-drivers")!;
    expect(s.context.join(" ")).toContain("Over the year, Transport (+1.48 pp) made the largest contribution to annual inflation of 4.1%.");
    expect(s.evidence.find((e) => e.seriesKey === "cpi.contrib.a.transport")).toMatchObject({
      label: "Transport, annual contribution", period: "2026-06", value: 1.484, unit: "percentage points",
    });
  });
});

describe("CPI drivers: which groups pull the other way", () => {
  const item = (slug: string, group: string, points: number, rank: number) => ({ slug, group, points, rank });
  const drivers = (headline: number, items: ReturnType<typeof item>[]) => {
    const contributions = cpi.contributions.map((b) => (b.horizon === "quarterly" ? { ...b, headline_pct: headline, items } : b));
    return byTemplate({ ...cpi, contributions }).get("inflation-drivers")!;
  };
  const other = (s: { context: string[] }) => s.context[0];

  it("names negative groups as the ones pulling against a positive headline", () => {
    const s = drivers(0.6, [item("a", "Transport", 0.5, 1), item("b", "Food", 0.2, 2), item("c", "Housing", -0.1, 3)]);
    expect(other(s)).toBe("One group pulled the other way: Housing (−0.10 pp).");
    expect(s.headline).toBe("Transport made the largest contribution to quarterly inflation of 0.6%");
  });

  it("names positive groups as the ones pulling against a negative headline", () => {
    const s = drivers(-0.6, [item("a", "Transport", -0.5, 1), item("b", "Food", -0.2, 2), item("c", "Housing", 0.1, 3)]);
    expect(other(s)).toBe("One group pulled the other way: Housing (+0.10 pp).");
    expect(other(s)).not.toContain("Transport");
    expect(s.headline).toBe("Transport made the largest downward contribution to quarterly inflation of −0.6%");
    expect(s.stat).toMatchObject({ value: "−0.50 pp", sign: "negative" });
  });

  it("lists several opposing groups largest first, in either direction", () => {
    const up = drivers(0.9, [item("a", "Transport", 0.9, 1), item("b", "Food", 0.3, 2), item("c", "Housing", -0.05, 3), item("d", "Health", -0.25, 4)]);
    expect(other(up)).toBe("2 groups pulled the other way: Health (−0.25 pp), Housing (−0.05 pp).");
    const down = drivers(-0.9, [item("a", "Transport", -0.9, 1), item("b", "Food", -0.3, 2), item("c", "Housing", 0.05, 3), item("d", "Health", 0.25, 4)]);
    expect(other(down)).toBe("2 groups pulled the other way: Health (+0.25 pp), Housing (+0.05 pp).");
  });

  it("says no group pulled the other way, naming the missing sign", () => {
    expect(other(drivers(0.6, [item("a", "Transport", 0.5, 1), item("b", "Food", 0.1, 2)]))).toBe("No group made a negative contribution this quarter.");
    expect(other(drivers(-0.6, [item("a", "Transport", -0.5, 1), item("b", "Food", -0.1, 2)]))).toBe("No group made a positive contribution this quarter.");
  });

  it("ignores contributions that round to zero at the displayed two decimals", () => {
    expect(other(drivers(0.6, [item("a", "Transport", 0.6, 1), item("b", "Food", -0.004, 2)]))).toBe("No group made a negative contribution this quarter.");
    expect(other(drivers(-0.6, [item("a", "Transport", -0.6, 1), item("b", "Food", 0.004, 2)]))).toBe("No group made a positive contribution this quarter.");
  });

  it("attributes no direction when the headline change rounds to zero", () => {
    const s = drivers(0.02, [item("a", "Transport", 0.3, 1), item("b", "Food", -0.28, 2)]);
    expect(other(s)).toBe("The headline change rounds to 0.0%, so no group is treated as driving prices up or down. Contributions pointed both ways: Transport (+0.30 pp) against Food (−0.28 pp).");
    expect(s.context.join(" ")).not.toMatch(/pulled the other way/);
    expect(s.headline).toBe("Transport made the largest contribution to quarterly inflation of 0.0%");
  });

  it("keeps the zero-headline wording to what the data support when contributions are one-sided", () => {
    const s = drivers(-0.03, [item("a", "Transport", 0.0, 1), item("b", "Food", -0.03, 2)]);
    expect(other(s)).toBe("The headline change rounds to 0.0%, so no group is treated as driving prices up or down.");
  });
});

