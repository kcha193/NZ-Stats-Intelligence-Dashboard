import { describe, expect, it } from "vitest";
import type { CpiDashboard, EctDashboard, SeriesData } from "@/api/types";
import { TEST_THEME } from "@/charts/theme";
import cpiFixture from "@/test/fixtures/cpi.json";
import ectFixture from "@/test/fixtures/ect.json";
import arrivals from "@/test/fixtures/series_arrivals_ry.json";
import departures from "@/test/fixtures/series_departures_ry.json";
import net from "@/test/fixtures/series_net_ry.json";
import nonNz from "@/test/fixtures/series_net_nonnz_ry.json";
import nz from "@/test/fixtures/series_net_nz_ry.json";
import { buildEctStories } from "./ect";
import { buildMigrationStories } from "./migration";
import { buildCpiStories } from "./cpi";
import { figureView, variantsOf } from "./figures";

const stories = new Map([
  ...buildCpiStories(cpiFixture as unknown as CpiDashboard),
  ...buildEctStories(ectFixture as unknown as EctDashboard),
  ...buildMigrationStories({
    net: net as SeriesData, arrivals: arrivals as SeriesData, departures: departures as SeriesData, nz: nz as SeriesData, nonNz: nonNz as SeriesData, releases: [],
  }),
].map((s) => [s.template, s]));
type Opt = {
  series: { name?: string; type?: string; markPoint?: { data: { label?: { formatter?: string } }[] }; markLine?: unknown; markArea?: unknown; data: unknown[] }[];
  yAxis: { data?: string[]; min?: number }; title?: { text: string };
};

describe("story figures", () => {
  it("annotates the ten-year peak on the annual inflation chart and keeps the reference band", () => {
    const view = figureView(stories.get("inflation-annual")!, "10y", TEST_THEME);
    const opt = view.option as unknown as Opt;
    const labels = opt.series[0].markPoint!.data.map((d) => d.label?.formatter).filter(Boolean);
    expect(labels).toContain("Peak 7.3% (Jun 2022)");
    expect(opt.series[0].markArea).toBeDefined();
    expect(opt.series[0].data).toHaveLength(40);
    expect(view.unit).toBe("percent change from the same quarter a year earlier");
    expect(view.caveat).toMatch(/not a forecast/);
    expect(view.csvRows.at(-1)).toMatchObject({ period: "2026-06", release_key: "consumers-price-index:june 2026 quarter" });
  });

  it("switches the contribution chart between quarterly and annual blocks, in percentage points", () => {
    const story = stories.get("inflation-drivers")!;
    expect(variantsOf(story)?.options.map((o) => o.value)).toEqual(["quarterly", "annual"]);
    const q = figureView(story, "quarterly", TEST_THEME);
    const y = figureView(story, "annual", TEST_THEME);
    expect(q.unit).toBe("percentage points");
    expect((q.option as unknown as Opt).yAxis.data?.[0]).toBe("Transport");
    expect(q.csvRows[0]).toMatchObject({ horizon: "quarterly", contribution_percentage_points: 0.824 });
    expect(y.csvRows[0]).toMatchObject({ horizon: "annual", contribution_percentage_points: 1.484 });
    expect(y.title).toMatch(/annual/);
  });

  it("shows card spending as published monthly changes by default, and the level with a stated non-zero axis", () => {
    const story = stories.get("spending-retail")!;
    expect(variantsOf(story)?.initial).toBe("change");
    const change = figureView(story, "change", TEST_THEME);
    expect(change.unit).toBe("percent change from the previous month, seasonally adjusted");
    expect((change.option as unknown as Opt).series[0].type).toBe("bar");
    expect((change.option as unknown as Opt).series[0].data).toHaveLength(24);
    const level = figureView(story, "level", TEST_THEME);
    expect(level.unit).toBe("NZD million, seasonally adjusted");
    expect((level.option as unknown as Opt).title?.text).toMatch(/not zero/);
    expect(level.caveat).toMatch(/does not start at zero/);
  });

  it("ranks industry changes with signs on one percent axis", () => {
    const view = figureView(stories.get("spending-industries")!, "", TEST_THEME);
    const opt = view.option as unknown as Opt;
    expect(opt.yAxis.data?.[0]).toBe("Fuel");
    expect(opt.yAxis.data?.at(-1)).toBe("Hospitality");
    expect(view.csvRows).toHaveLength(8);
    expect(view.csvRows[0]).toMatchObject({ unit: "percent", adjustment: "seasonally_adjusted" });
  });

  it("draws migration stories on year-ended series only, with provisional shading and the ten-year peak", () => {
    const netView = figureView(stories.get("migration-net")!, "10y", TEST_THEME);
    const opt = netView.option as unknown as Opt;
    expect(opt.series[0].markArea).toBeDefined();
    expect(opt.series[0].markPoint!.data.map((d) => d.label?.formatter)).toContain("Peak 133,738 (Oct 2023)");
    expect(netView.csvRows.every((r) => String(r.series).startsWith("mig.ry."))).toBe(true);
    const flows = figureView(stories.get("migration-flows")!, "10y", TEST_THEME).option as unknown as Opt;
    expect(flows.series.map((x) => x.name)).toEqual(["Migrant arrivals", "Migrant departures"]);
    const cit = figureView(stories.get("migration-citizenship")!, "10y", TEST_THEME).option as unknown as Opt;
    expect(cit.series.map((x) => x.name)).toEqual(["Non-New Zealand citizens", "New Zealand citizens"]);
    expect(cit.series[0].markLine).toBeDefined();
  });
});
