import { describe, expect, it } from "vitest";
import type { Kpi, Overview, ReleaseSummary } from "@/api/types";
import { buildPulse, freshness } from "./pulse";

const change = (label: string, previous: number, absolute: number, percent: number | null) =>
  ({ label, comparison_period: "x", previous, absolute, percent });

function kpi(series_key: string, over: Partial<Kpi["metric"]>, published_at: string): Kpi {
  return {
    release_id: 1, published_at, source_url: "https://www.stats.govt.nz/x",
    metric: {
      series_key, label: series_key, value: 0, unit: "people", frequency: "monthly", period: "2026-07",
      period_label: "July 2026", status: "final", std_error: null, change_prior: null, change_year_ago: null, ...over,
    },
  };
}

const CPI = kpi("cpi.index.nsa.all_groups", {
  label: "CPI annual inflation, all groups", value: 4.058, unit: "percent", frequency: "quarterly", period: "2026-06",
  period_label: "Quarter ended June 2026", change_year_ago: change("vs June 2025 quarter (a year earlier)", 2.658, 1.4, null),
}, "2026-07-21T10:45:00+12:00");
const ECT = kpi("ect.m.sa.retail.value", {
  label: "Retail, seasonally adjusted, value", value: 6976, unit: "NZD million", period: "2026-09",
  period_label: "September 2026", change_prior: change("vs August 2026", 6955.1, 20.9, 0.3005),
}, "2026-10-16T10:45:00+13:00");
const MIG = kpi("mig.ry.net", {
  label: "Net migration, year ended", value: 20350, frequency: "rolling_annual", period_label: "Year ended July 2026",
  status: "provisional", change_year_ago: change("vs year ended July 2025", 9592, 10758, 112.2),
}, "2026-09-14T10:45:00+12:00");
const next = { series_slug: "international-migration", published_at: "2026-11-12T10:45:00+13:00", title: "International migration: September 2026" } as ReleaseSummary;
const overview = (kpis: Kpi[]) => ({ kpis, upcoming: [next] }) as unknown as Overview;
const NOW = new Date("2026-10-27T07:00:00Z");

describe("economic pulse", () => {
  it("picks one headline indicator per topic, in reading order", () => {
    const items = buildPulse(overview([MIG, ECT, CPI, kpi("mig.m.net", {}, MIG.published_at)]), NOW);
    expect(items.map((i) => i.key)).toEqual(["inflation", "spending", "migration"]);
    expect(items.map((i) => i.kpi.metric.series_key)).toEqual(["cpi.index.nsa.all_groups", "ect.m.sa.retail.value", "mig.ry.net"]);
  });

  it("omits a topic that has no verified data rather than inventing one", () => {
    expect(buildPulse(overview([ECT]), NOW).map((i) => i.key)).toEqual(["spending"]);
    expect(buildPulse(overview([]), NOW)).toEqual([]);
  });

  it("writes plain, deterministic sentences from the published comparisons", () => {
    const [cpi, ect, mig] = buildPulse(overview([CPI, ECT, MIG]), NOW);
    expect(cpi.value).toBe("4.1%");
    expect(cpi.sentence).toBe("Consumer prices were 4.1% higher than a year earlier in the quarter ended June 2026, up from 2.7% a year before.");
    expect(ect.value).toBe("$6,976m");
    expect(ect.sentence).toBe("Retail card spending was $6,976 million in September 2026 (seasonally adjusted), 0.3% more than in August 2026.");
    expect(mig.value).toBe("+20,350");
    expect(mig.sentence).toBe("Net migration added 20,350 people in the year ended July 2026, up from 9,592 a year earlier.");
    for (const i of [cpi, ect, mig]) expect(i.sentence).not.toMatch(/[–—]|because|due to|driven by/);
  });

  it("describes falls and net losses without spin", () => {
    const fall = kpi("mig.ry.net", { value: -3200, frequency: "rolling_annual", period_label: "Year ended July 2026",
      change_year_ago: change("vs year ended July 2025", 1800, -5000, null) }, MIG.published_at);
    expect(buildPulse(overview([fall]), NOW)[0].sentence).toBe("Net migration reduced the population by 3,200 people in the year ended July 2026, down from a gain of 1,800 a year earlier.");
    const deflation = { ...CPI, metric: { ...CPI.metric, value: -0.4, change_year_ago: change("x", 0.5, -0.9, null) } };
    expect(buildPulse(overview([deflation]), NOW)[0].sentence).toBe("Consumer prices were 0.4% lower than a year earlier in the quarter ended June 2026, down from 0.5% a year before.");
  });

  it("links each indicator to its dashboard and its next scheduled release", () => {
    const [, , mig] = buildPulse(overview([CPI, ECT, MIG]), NOW);
    expect(mig.dashboard).toEqual({ to: "/migration", label: "Explore migration" });
    expect(mig.next?.title).toBe("International migration: September 2026");
    expect(buildPulse(overview([CPI]), NOW)[0].next).toBeNull();
  });
});

describe("freshness", () => {
  it("is current within the usual release interval and says when it may be out of date", () => {
    expect(freshness(ECT, NOW).state).toBe("current");
    expect(freshness(CPI, NOW)).toMatchObject({ state: "current", label: "Latest release" });
    const later = new Date("2026-12-20T00:00:00Z");
    const f = freshness(ECT, later);
    expect(f.state).toBe("stale");
    expect(f.label).toBe("May be out of date");
    expect(f.detail).toBe("Published 65 days ago. A newer release is usually out by now; this site has not verified one yet.");
  });
});
