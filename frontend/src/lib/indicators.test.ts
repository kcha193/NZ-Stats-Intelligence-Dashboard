import { describe, expect, it } from "vitest";
import type { Kpi } from "@/api/types";
import overview from "@/test/fixtures/overview.json";
import { groupIndicators } from "./indicators";

const kpi = (series_key: string, label = series_key) => ({ metric: { series_key, label } }) as unknown as Kpi;

describe("indicator groups", () => {
  it("groups every indicator by topic in reading order and keeps the backend order within a group", () => {
    const groups = groupIndicators([kpi("mig.ry.net"), kpi("ect.m.sa.retail.value"), kpi("mig.m.net"), kpi("cpi.index.nsa.all_groups"), kpi("lab.x")]);
    expect(groups.map((g) => g.key)).toEqual(["inflation", "spending", "migration", "other"]);
    expect(groups.find((g) => g.key === "migration")!.kpis.map((k) => k.metric.series_key)).toEqual(["mig.ry.net", "mig.m.net"]);
    expect(groups.flatMap((g) => g.kpis)).toHaveLength(5);
  });

  it("omits empty groups and never drops an indicator from the real overview", () => {
    const kpis = (overview as unknown as { kpis: Kpi[] }).kpis;
    const groups = groupIndicators(kpis);
    expect(groups.flatMap((g) => g.kpis)).toHaveLength(kpis.length);
    expect(groups.every((g) => g.kpis.length > 0)).toBe(true);
  });
});
