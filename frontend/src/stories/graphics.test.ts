import { describe, expect, it } from "vitest";
import type { CpiDashboard, EctDashboard, SeriesData } from "@/api/types";
import cpiFixture from "@/test/fixtures/cpi.json";
import ectFixture from "@/test/fixtures/ect.json";
import arrivals from "@/test/fixtures/series_arrivals_ry.json";
import departures from "@/test/fixtures/series_departures_ry.json";
import net from "@/test/fixtures/series_net_ry.json";
import nonNz from "@/test/fixtures/series_net_nonnz_ry.json";
import nz from "@/test/fixtures/series_net_nz_ry.json";
import { buildCpiStories } from "./cpi";
import { buildEctStories } from "./ect";
import { buildMigrationStories, type MigrationInput } from "./migration";
import type { Story } from "./types";

const cpi = cpiFixture as unknown as CpiDashboard;
const ect = ectFixture as unknown as EctDashboard;
const mig: MigrationInput = {
  net: net as SeriesData, arrivals: arrivals as SeriesData, departures: departures as SeriesData,
  nz: nz as SeriesData, nonNz: nonNz as SeriesData,
  releases: [{ id: 2, release_key: "international-migration:july 2026", status: "published", page_url: null }],
};
const all = () => [...buildCpiStories(cpi), ...buildEctStories(ect), ...buildMigrationStories(mig)];
const get = (template: string, stories: Story[] = all()) => stories.find((s) => s.template === template)!;

/** The CPI fixture with the latest all-groups annual rate replaced. */
function cpiWithAnnual(latest: number, prior?: number): CpiDashboard {
  const series = cpi.series.map((x) => {
    if (x.slug !== "all_groups" || x.adjustment !== "none") return x;
    const pts = [...x.points];
    pts[pts.length - 1] = { ...pts[pts.length - 1], annual_pct: latest };
    if (prior !== undefined) pts[pts.length - 2] = { ...pts[pts.length - 2], annual_pct: prior };
    return { ...x, points: pts };
  });
  return { ...cpi, series };
}

describe("story graphics: one encoding per message, real values, correct units", () => {
  it("annual inflation is a quarterly line of the published rate, in percent, with a zero baseline", () => {
    const t = get("inflation-annual").thumb;
    expect(t).toMatchObject({ kind: "line", format: "pct", period: "quarter", zero: true, name: "Annual CPI inflation" });
    if (t.kind !== "line") throw new Error();
    expect(t.points).toHaveLength(40);
    expect(t.points.at(-1)).toMatchObject({ period: "2026-06" });
    expect(t.points.at(-1)!.value).toBeCloseTo(4.058, 3);
  });

  it("contributions are a signed ranking in percentage points, largest first", () => {
    const t = get("inflation-drivers").thumb;
    expect(t).toMatchObject({ kind: "bars", format: "pp" });
    if (t.kind !== "bars") throw new Error();
    expect(t.items[0]).toMatchObject({ label: "Transport" });
    const values = t.items.map((i) => i.value);
    expect(values).toEqual([...values].sort((a, b) => b - a));
    expect(values.some((v) => v < 0)).toBe(true);
  });

  it("tradables versus non-tradables is a pair of annual rates with the gap in percentage points", () => {
    const t = get("inflation-tradables").thumb;
    expect(t).toMatchObject({ kind: "pair", format: "pct", gap: { label: "Gap", value: "+1.5 pp" } });
    if (t.kind !== "pair") throw new Error();
    expect(t.items.map((i) => i.label)).toEqual(["Tradables", "Non-tradables"]);
    expect(t.items[0].value.toFixed(1)).toBe("4.9");
    expect(t.items[1].value.toFixed(1)).toBe("3.4");
  });

  it("retail spending is signed monthly columns of the published change, never the level", () => {
    const t = get("spending-retail").thumb;
    expect(t).toMatchObject({ kind: "columns", format: "pct", period: "month", name: "Retail card spending, monthly change" });
    if (t.kind !== "columns") throw new Error();
    expect(t.points).toHaveLength(24);
    expect(t.points.at(-1)).toMatchObject({ period: "2026-09", value: -0.4 });
  });

  it("industry movements are a signed ranking in percent", () => {
    expect(get("spending-industries").thumb).toMatchObject({ kind: "bars", format: "pct" });
  });

  it("net migration is a year-ended line in people that marks provisional points", () => {
    const t = get("migration-net").thumb;
    expect(t).toMatchObject({ kind: "line", format: "people", period: "year-ended", zero: true });
    if (t.kind !== "line") throw new Error();
    expect(t.points.at(-1)).toMatchObject({ period: "2026-07", value: 20350, provisional: true });
    expect(t.points[0].provisional).toBe(false);
  });

  it("arrivals and departures are a pair of year-ended counts whose stated difference is the net figure", () => {
    const t = get("migration-flows").thumb;
    expect(t).toMatchObject({
      kind: "pair", format: "people",
      items: [{ label: "Arrivals", value: 134434 }, { label: "Departures", value: 114084 }],
      gap: { label: "Arrivals minus departures", value: "+20,350" },
    });
  });

  it("citizenship is a diverging pair of signed net flows", () => {
    expect(get("migration-citizenship").thumb).toMatchObject({
      kind: "bars", format: "people",
      items: [{ label: "Non-NZ citizens", value: 58685 }, { label: "NZ citizens", value: -38335 }],
    });
  });
});

describe("economy at a glance: plain language that matches the measure", () => {
  it("only the headline story of each category carries a glance", () => {
    expect(all().filter((s) => s.glance).map((s) => s.template)).toEqual(["inflation-annual", "spending-retail", "migration-net"]);
  });

  it("inflation: the rate compared with the previous quarter in percentage points, and prices compared with a year earlier", () => {
    expect(get("inflation-annual").glance).toEqual({
      metric: "Inflation", value: "4.1%", measure: "annual change in consumer prices",
      comparison: "Up 1.0 percentage points from 3.1% in the March 2026 quarter",
      plain: "Consumer prices were 4.1% higher than a year earlier.", direction: "up",
    });
  });

  it("easing inflation is never described as falling prices", () => {
    const g = get("inflation-annual", buildCpiStories(cpiWithAnnual(2.5, 3.1))).glance!;
    expect(g.comparison).toBe("Down 0.6 percentage points from 3.1% in the March 2026 quarter");
    expect(g.plain).toBe("Consumer prices were 2.5% higher than a year earlier.");
    expect(g.direction).toBe("down");
  });

  it("negative and zero inflation are worded from the displayed rate", () => {
    expect(get("inflation-annual", buildCpiStories(cpiWithAnnual(-0.5))).glance!.plain).toBe("Consumer prices were 0.5% lower than a year earlier.");
    expect(get("inflation-annual", buildCpiStories(cpiWithAnnual(0.04))).glance!.plain).toBe("Consumer prices were unchanged from a year earlier.");
    expect(get("inflation-annual", buildCpiStories(cpiWithAnnual(3.08, 3.1))).glance!.comparison).toBe("Unchanged from 3.1% in the March 2026 quarter");
  });

  it("retail spending: the published monthly change, with the previous month's change for comparison", () => {
    expect(get("spending-retail").glance).toEqual({
      metric: "Retail card spending", value: "−0.4%", measure: "monthly change, seasonally adjusted",
      comparison: "Previous month: −0.9% (August 2026)",
      plain: "Retail card spending was 0.4% lower than in August 2026, after seasonal adjustment.", direction: "down",
    });
  });

  it("net migration: the year-ended total against the non-overlapping year a year earlier", () => {
    expect(get("migration-net").glance).toEqual({
      metric: "Net migration", value: "+20,350", measure: "people, year-ended total",
      comparison: "Up from a net gain of 9,592 a year earlier",
      plain: "Over the year, 20,350 more migrants arrived than left.", direction: "up",
    });
  });
});

describe("net migration glance wording follows the sign of both years", () => {
  /** The net series with its latest value and the value a year earlier replaced. */
  const withNet = (latest: number, yearAgo: number): MigrationInput => {
    const s = net as SeriesData;
    const points = s.points.map((p, i, all) =>
      i === all.length - 1 ? { ...p, value: latest } : i === all.length - 13 ? { ...p, value: yearAgo } : p);
    return { ...mig, net: { ...s, points } };
  };
  const glanceOf = (latest: number, yearAgo: number) => get("migration-net", buildMigrationStories(withNet(latest, yearAgo))).glance!;

  it("calls a widening loss larger, never 'up', and points the arrow down", () => {
    expect(glanceOf(-8000, -5000)).toMatchObject({ comparison: "Larger than a net loss of 5,000 a year earlier", direction: "down" });
    expect(glanceOf(-8000, -5000).plain).toBe("Over the year, 8,000 more migrants left than arrived.");
  });

  it("calls a narrowing loss smaller and points the arrow up", () => {
    expect(glanceOf(-3000, -5000)).toMatchObject({ comparison: "Smaller than a net loss of 5,000 a year earlier", direction: "up" });
  });

  it("uses up and down for gains, and plain comparison when the sign changed", () => {
    expect(glanceOf(4000, 9000)).toMatchObject({ comparison: "Down from a net gain of 9,000 a year earlier", direction: "down" });
    expect(glanceOf(4000, -2000)).toMatchObject({ comparison: "Compared with a net loss of 2,000 a year earlier", direction: "up" });
  });
});
