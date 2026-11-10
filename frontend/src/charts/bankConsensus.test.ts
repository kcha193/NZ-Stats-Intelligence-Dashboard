import { describe, expect, it } from "vitest";
import { CONSENSUS_GROUP } from "@/components/outlook/bank/testData";
import type { BankConsensusGroup } from "@/api/bank";
import { bankConsensusOption } from "./bankConsensus";
import { TEST_THEME } from "./theme";

// SYNTHETIC: fictitious banks.
type Series = { type: string; name: string; symbol?: string; data: number[][]; markLine?: { data: { xAxis: number }[] }; markArea?: { data: unknown[] } };
type Opt = { yAxis: { data: string[] }; xAxis: { min: number; max: number }; series: Series[]; aria: { enabled: boolean } };

const group = (over: Partial<BankConsensusGroup> = {}): BankConsensusGroup => ({ ...CONSENSUS_GROUP, ...over });
const build = (g: BankConsensusGroup) => bankConsensusOption(g, TEST_THEME) as unknown as Opt;
const banks = (o: Opt) => o.series.find((s) => s.name === "Banks")!;
const refs = (o: Opt) => o.series.find((s) => s.name === "Reference")!;

describe("bank consensus dot plot", () => {
  it("draws one dot per contributing bank, in the contributors' order", () => {
    const o = build(group());
    expect(o.aria.enabled).toBe(true);
    expect(o.yAxis.data.slice(0, 3)).toEqual(["Example Bank A", "Example Bank B", "Example Bank C"]);
    expect(banks(o).data.map((d) => d[0])).toEqual([2.1, 2.4, 2.7]);
  });

  it("draws the median at two banks and the range band only from three", () => {
    const two = group({ n: 2, contributors: CONSENSUS_GROUP.contributors.slice(0, 2), title: "Two-bank comparison", std_dev: null });
    const o2 = build(two);
    expect(banks(o2).markLine?.data).toEqual([{ xAxis: 2.4 }]);
    expect(banks(o2).markArea).toBeUndefined();
    const o3 = build(group());
    expect(banks(o3).markLine?.data).toEqual([{ xAxis: 2.4 }]);
    expect(banks(o3).markArea?.data).toHaveLength(1);
  });

  it("draws no median or band for a single bank", () => {
    const one = group({ n: 1, contributors: CONSENSUS_GROUP.contributors.slice(0, 1), median: null, mean: null, minimum: null, maximum: null, range: null, std_dev: null, status: "insufficient", title: "Insufficient banks" });
    const o = build(one);
    expect(banks(o).markLine).toBeUndefined();
    expect(banks(o).markArea).toBeUndefined();
  });

  it("draws reference markers as a distinct series that does not move the median", () => {
    const o = build(group());
    expect(refs(o).symbol).toBe("diamond");
    expect(refs(o).data.map((d) => d[0])).toEqual([2.3]);
    expect(o.yAxis.data).toContain("Example Reference Bank");
    expect(banks(o).markLine?.data).toEqual([{ xAxis: 2.4 }]); // the group's own median, not recomputed with the marker
  });

  it("keeps negative and zero values on the axis", () => {
    const g = group({ contributors: [
      { key: "a", name: "Example Bank A", value: -0.25, published_on: "2026-10-01", summary_id: 1 },
      { key: "b", name: "Example Bank B", value: 0, published_on: "2026-10-01", summary_id: 2 },
      { key: "c", name: "Example Bank C", value: 0.5, published_on: "2026-10-01", summary_id: 3 },
    ], median: 0, minimum: -0.25, maximum: 0.5, markers: [] });
    const o = build(g);
    expect(o.xAxis.min).toBeLessThan(-0.25);
    expect(banks(o).data.map((d) => d[0])).toEqual([-0.25, 0, 0.5]);
  });

  it("builds an independent option for each group (different measures never share an axis)", () => {
    const other = group({ key: "other", contributors: CONSENSUS_GROUP.contributors.map((c) => ({ ...c, value: c.value + 10 })), median: 12.4, minimum: 12.1, maximum: 12.7, markers: [] });
    const a = build(group());
    const b = build(other);
    expect(b.xAxis.min).toBeGreaterThan(a.xAxis.max);
  });
});
