import { describe, expect, it } from "vitest";
import type { CpiDashboard } from "@/api/types";
import { TEST_THEME } from "@/charts/theme";
import cpiFixture from "@/test/fixtures/cpi.json";
import { buildCpiStories } from "./cpi";
import { figureView, variantsOf } from "./figures";

const stories = new Map(buildCpiStories(cpiFixture as unknown as CpiDashboard).map((s) => [s.template, s]));
type Opt = { series: { markPoint?: { data: { label?: { formatter?: string } }[] }; markArea?: unknown; data: unknown[] }[]; yAxis: { data?: string[] } };

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
});
