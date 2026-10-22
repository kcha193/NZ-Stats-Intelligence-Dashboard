import { describe, expect, it } from "vitest";
import type { EctDashboard } from "@/api/types";
import ectFixture from "@/test/fixtures/ect.json";
import { buildEctStories } from "./ect";

const ect = ectFixture as unknown as EctDashboard;
const byTemplate = (data: EctDashboard) => new Map(buildEctStories(data).map((s) => [s.template, s]));

describe("card spending stories", () => {
  it("builds retail and industry stories from one release, with stable ids", () => {
    const stories = buildEctStories(ect);
    expect(stories.map((s) => s.id)).toEqual(["spending-retail-2026-09", "spending-industries-2026-09"]);
    for (const s of stories) {
      expect(s.category).toBe("spending");
      expect(s.provenance).toMatchObject({ releaseId: 2, releaseKey: "electronic-card-transactions:september 2026", publishedAt: "2026-10-16T10:45:00+13:00" });
      expect(s.referenceLabel).toBe("September 2026");
      expect(s.dashboard.to).toBe("/electronic-card-transactions");
      expect(s.caveats.join(" ")).toMatch(/nominal/i);
    }
  });

  it("headlines the published seasonally adjusted retail change, distinct from the spending level", () => {
    const s = byTemplate(ect).get("spending-retail")!;
    expect(s.headline).toBe("Retail card spending fell 0.4% in September 2026");
    expect(s.stat).toMatchObject({ value: "−0.4%", unit: "monthly change, seasonally adjusted", sign: "negative" });
    expect(s.dek).toBe("Seasonally adjusted retail spending on electronic cards was $6.98 billion, $30 million less than in August 2026.");
    expect(s.context).toContain("The last monthly fall at least this large was in August 2026 (−0.9%).");
    expect(s.context).toContain("Compared with September 2025, retail spending was 0.8% higher.");
    expect(s.context.join(" ")).toContain("110 of 287 overlapping retail months were revised");
    expect(s.evidence[0]).toMatchObject({ seriesKey: "ect.m.sa.retail.change", period: "2026-09", value: -0.4, unit: "percent" });
  });

  it("ranks industry movements on the same adjusted, monthly basis and keeps their signs", () => {
    const s = byTemplate(ect).get("spending-industries")!;
    expect(s.headline).toBe("Spending on fuel rose 2.9% in September 2026; hospitality fell 2.3%");
    expect(s.stat).toMatchObject({ value: "+2.9%", sign: "positive" });
    expect(s.context).toContain("3 of 8 industries recorded higher seasonally adjusted spending than in August 2026.");
    expect(s.figure.kind).toBe("ect-industries");
    const items = s.figure.kind === "ect-industries" ? s.figure.items : [];
    expect(items).toHaveLength(8);
    expect(items.every((i) => i.period === "2026-09" && i.previousPeriod === "2026-08")).toBe(true);
    expect(items.find((i) => i.name === "Hospitality")!.percent).toBeCloseTo(-2.259, 3);
  });

  it("omits a story whose series are missing rather than inventing values", () => {
    const series = ect.series.filter((x) => x.series.key !== "ect.m.sa.retail.change");
    expect(byTemplate({ ...ect, series }).has("spending-retail")).toBe(false);
    expect(buildEctStories({ ...ect, series: [] })).toEqual([]);
  });
});
