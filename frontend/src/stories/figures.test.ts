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
import type { Story } from "./types";

const stories = new Map([
  ...buildCpiStories(cpiFixture as unknown as CpiDashboard),
  ...buildEctStories(ectFixture as unknown as EctDashboard),
  ...buildMigrationStories({
    net: net as SeriesData, arrivals: arrivals as SeriesData, departures: departures as SeriesData, nz: nz as SeriesData, nonNz: nonNz as SeriesData, releases: [],
  }),
].map((s) => [s.template, s]));
type Opt = {
  series: { name?: string; type?: string; markPoint?: { data: { label?: { formatter?: string; position?: string } }[] }; markLine?: unknown; markArea?: unknown; data: unknown[] }[];
  yAxis: { data?: string[]; min?: number }; title?: { text: string };
};

describe("story figures", () => {
  it("annotates the ten-year peak on the annual inflation chart and keeps the reference band", () => {
    const view = figureView(stories.get("inflation-annual")!, "10y", TEST_THEME);
    const opt = view.option as unknown as Opt;
    const labels = opt.series[0].markPoint!.data.map((d) => d.label?.formatter).filter(Boolean);
    expect(labels).toContain("Peak 7.3% (Jun 2022)");
    expect(opt.series[0].markPoint!.data.find((d) => d.label?.formatter?.startsWith("Peak"))?.label?.position).toBe("top");
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
    const peak = opt.series[0].markPoint!.data.find((d) => d.label?.formatter === "Peak 133,738 (Oct 2023)");
    // The peak sits in the right half, near the provisional band and its label, so its label reads leftwards.
    expect(peak?.label?.position).toBe("left");
    expect(netView.csvRows.every((r) => String(r.series).startsWith("mig.ry."))).toBe(true);
    const flows = figureView(stories.get("migration-flows")!, "10y", TEST_THEME).option as unknown as Opt;
    expect(flows.series.map((x) => x.name)).toEqual(["Migrant arrivals", "Migrant departures"]);
    const cit = figureView(stories.get("migration-citizenship")!, "10y", TEST_THEME).option as unknown as Opt;
    expect(cit.series.map((x) => x.name)).toEqual(["Non-New Zealand citizens", "New Zealand citizens"]);
    expect(cit.series[0].markLine).toBeDefined();
  });
describe("contribution horizon controls", () => {
  const drivers = stories.get("inflation-drivers")!;
  const blocksOf = (story: Story) => (story.figure.kind === "cpi-contributions" ? story.figure.blocks : []);
  const withBlocks = (blocks: ReturnType<typeof blocksOf>): Story => ({ ...drivers, figure: { kind: "cpi-contributions", blocks } });
  const quarterly = blocksOf(drivers).find((b) => b.horizon === "quarterly")!;
  const annual = blocksOf(drivers).find((b) => b.horizon === "annual")!;
  const options = (story: Story) => variantsOf(story)?.options.map((o) => o.value);

  it("offers only the quarterly horizon when the release has no annual contributions", () => {
    const story = withBlocks([quarterly, { ...annual, available: false, items: [] }]);
    expect(options(story)).toEqual(["quarterly"]);
    expect(variantsOf(story)?.initial).toBe("quarterly");
    expect(figureView(story, "annual", TEST_THEME).csvRows[0]).toMatchObject({ horizon: "quarterly" });
  });

  it("offers only the quarterly horizon when the annual block is missing", () => {
    expect(options(withBlocks([quarterly]))).toEqual(["quarterly"]);
  });

  it("starts on the annual horizon when only annual contributions exist", () => {
    const story = withBlocks([{ ...quarterly, available: false, items: [] }, annual]);
    expect(options(story)).toEqual(["annual"]);
    expect(variantsOf(story)?.initial).toBe("annual");
    const view = figureView(story, variantsOf(story)!.initial, TEST_THEME);
    expect(view.csvRows[0]).toMatchObject({ horizon: "annual" });
    expect(figureView(story, "quarterly", TEST_THEME).csvRows[0]).toMatchObject({ horizon: "annual" });
  });

  it("treats an available block with no items as unavailable", () => {
    expect(options(withBlocks([quarterly, { ...annual, items: [] }]))).toEqual(["quarterly"]);
  });

  it("offers both horizons, quarterly first, and switches between them", () => {
    const story = withBlocks([annual, quarterly]);
    expect(options(story)).toEqual(["quarterly", "annual"]);
    expect(variantsOf(story)?.initial).toBe("quarterly");
    expect(figureView(story, "annual", TEST_THEME).csvRows[0]).toMatchObject({ horizon: "annual" });
    expect(figureView(story, "quarterly", TEST_THEME).csvRows[0]).toMatchObject({ horizon: "quarterly" });
  });

  it("renders an empty, labelled figure rather than throwing when neither horizon is available", () => {
    const story = withBlocks([{ ...quarterly, available: false, items: [] }, { ...annual, available: false, items: [] }]);
    expect(variantsOf(story)).toBeNull();
    const view = figureView(story, "", TEST_THEME);
    expect(view.csvRows).toEqual([]);
    expect(view.caveat).toMatch(/not available/i);
    expect(() => figureView(withBlocks([]), "annual", TEST_THEME)).not.toThrow();
  });
});
});
