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

describe("card spending industry direction wording", () => {
  const KEYS = ["consumables", "durables", "hospitality", "apparel", "motor_vehicles", "fuel", "services", "non_retail"];
  /** Sets each industry's latest month to `percent` above (or below) the month before; unlisted industries are unchanged. */
  const withMoves = (moves: Partial<Record<string, number>>): EctDashboard => ({
    ...ect,
    series: ect.series.map((s) => {
      const key = KEYS.find((k) => s.series.key === `ect.m.sa.${k}.value`);
      if (!key) return s;
      const points = s.points.map((p) => ({ ...p }));
      points[points.length - 1].value = points[points.length - 2].value * (1 + (moves[key] ?? 0) / 100);
      return { ...s, points };
    }),
  });
  const industries = (moves: Partial<Record<string, number>>) => byTemplate(withMoves(moves)).get("spending-industries")!;
  const all = (v: number) => Object.fromEntries(KEYS.map((k) => [k, v]));

  it("describes only rises when every industry rose", () => {
    const s = industries({ ...all(1), fuel: 3, services: 2 });
    expect(s.dek).toBe("Fuel (+3.0%) and services (+2.0%) rose most, compared with August 2026.");
    expect(s.headline).toBe("Card spending rose or held in every industry in September 2026, led by fuel (+3.0%)");
    expect(s.stat).toMatchObject({ value: "+3.0%", label: "Largest rise of 8 industries", sign: "positive" });
  });

  it("describes only falls when every industry fell", () => {
    const s = industries({ ...all(-1), fuel: -3, services: -2 });
    expect(s.dek).toBe("Fuel (−3.0%) and services (−2.0%) fell most, compared with August 2026.");
    expect(s.dek).not.toMatch(/rose/);
    expect(s.headline).toBe("Card spending fell or held in every industry in September 2026, led by fuel (−3.0%)");
    expect(s.stat).toMatchObject({ value: "−3.0%", label: "Largest fall of 8 industries", sign: "negative" });
  });

  it("names two risers and two fallers from their signs in a mixed month", () => {
    const s = industries({ fuel: 3, services: 2, durables: 0.5, hospitality: -2, apparel: -1, consumables: -0.5 });
    expect(s.dek).toBe("Fuel (+3.0%) and services (+2.0%) rose most; hospitality (−2.0%) and apparel (−1.0%) fell most, compared with August 2026.");
  });

  it("does not call a second industry a riser when only one rose", () => {
    const s = industries({ fuel: 3, hospitality: -2, apparel: -1, durables: 0.04 });
    expect(s.dek).toBe("Fuel (+3.0%) was the only industry to rise; hospitality (−2.0%) and apparel (−1.0%) fell most, compared with August 2026.");
    expect(s.dek).not.toContain("durables");
  });

  it("does not call a second industry a faller when only one fell", () => {
    const s = industries({ fuel: 3, services: 2, hospitality: -2, durables: -0.04 });
    expect(s.dek).toBe("Fuel (+3.0%) and services (+2.0%) rose most; hospitality (−2.0%) was the only industry to fall, compared with August 2026.");
    expect(s.dek).not.toContain("durables");
  });

  it("states that nothing moved when every industry is unchanged", () => {
    const s = industries({});
    expect(s.dek).toBe("Seasonally adjusted spending was unchanged in every industry compared with August 2026, at one decimal place.");
    expect(s.headline).toBe("Card spending was unchanged in every industry in September 2026");
    expect(s.stat).toMatchObject({ label: "Largest movement of 8 industries", sign: "neutral" });
    expect(s.context).toContain("0 of 8 industries recorded higher seasonally adjusted spending than in August 2026.");
  });

  it("treats movements that round to zero at the displayed precision as unchanged", () => {
    const s = industries({ consumables: 0.04, durables: -0.04, fuel: 0.049 });
    expect(s.headline).toBe("Card spending was unchanged in every industry in September 2026");
    expect(s.dek).not.toMatch(/rose|fell/);
  });
});

describe("card spending industry evidence status", () => {
  const industries = (data: EctDashboard) => byTemplate(data).get("spending-industries")!;

  it("carries each point's own status instead of calling every value final", () => {
    const s = industries(ect);
    const fuel = s.evidence.filter((e) => e.seriesKey === "ect.m.sa.fuel.value");
    const source = ect.series.find((x) => x.series.key === "ect.m.sa.fuel.value")!.points;
    expect(fuel.map((e) => [e.period, e.status])).toEqual([
      ["2026-09", source.at(-1)!.status], ["2026-08", source.at(-2)!.status],
    ]);
    expect(s.evidence.some((e) => e.status === "unknown")).toBe(true);
  });

  it("flags the story provisional when a latest industry value is provisional", () => {
    const series = ect.series.map((x) => x.series.key === "ect.m.sa.fuel.value"
      ? { ...x, points: x.points.map((p, i, all) => (i === all.length - 1 ? { ...p, status: "provisional" } : p)) } : x);
    const s = industries({ ...ect, series });
    expect(s.dataStatus).toBe("provisional");
    expect(s.evidence.find((e) => e.seriesKey === "ect.m.sa.fuel.value" && e.period === "2026-09")!.status).toBe("provisional");
    expect(industries(ect).dataStatus).toBe("final");
  });
});
