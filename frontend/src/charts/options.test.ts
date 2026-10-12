import { describe, expect, it } from "vitest";
import {
  divergingBarOption, lineOption, rankedBarOption, revisionBarOption, sliceYears,
  stackedPanelsOption, type ChartPoint,
} from "./options";
import { TEST_THEME } from "./theme";

const pts = (rows: [string, number, string?][]): ChartPoint[] =>
  rows.map(([period, value, status]) => ({ period, value, status: status ?? "final" }));

const input = (series: ChartPoint[], extra = {}) => ({
  series: [{ name: "Net", points: series, color: "#123456" }],
  unit: "people",
  frequency: "monthly" as const,
  ...extra,
});

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Opt = any;

describe("lineOption", () => {
  it("uses a zero baseline for non-negative series and none otherwise", () => {
    const nonNeg = lineOption(input(pts([["2026-01", 5], ["2026-02", 9]])), TEST_THEME) as Opt;
    expect(nonNeg.yAxis.min).toBe(0);
    const mixed = lineOption(input(pts([["2026-01", -5], ["2026-02", 9]])), TEST_THEME) as Opt;
    expect(mixed.yAxis.min).toBeUndefined();
  });

  it("draws a zero reference line only when values cross zero", () => {
    const mixed = lineOption(input(pts([["2026-01", -5], ["2026-02", 9]])), TEST_THEME) as Opt;
    expect(mixed.series[0].markLine.data[0].yAxis).toBe(0);
    const nonNeg = lineOption(input(pts([["2026-01", 5], ["2026-02", 9]])), TEST_THEME) as Opt;
    expect(nonNeg.series[0].markLine).toBeUndefined();
  });

  it("shades from the first provisional period and only when one exists", () => {
    const withProv = lineOption(
      input(pts([["2026-01", 1], ["2026-02", 2, "provisional"], ["2026-03", 3, "provisional"]])),
      TEST_THEME,
    ) as Opt;
    const area = withProv.series[0].markArea.data[0];
    expect(area[0].xAxis).toBe("2026-02");
    expect(area[1].xAxis).toBe("2026-03");
    const none = lineOption(input(pts([["2026-01", 1], ["2026-02", 2]])), TEST_THEME) as Opt;
    expect(none.series[0].markArea).toBeUndefined();
  });

  it("highlights the latest observation with a labelled marker", () => {
    const o = lineOption(input(pts([["2026-01", 1], ["2026-02", 2]])), TEST_THEME) as Opt;
    expect(o.series[0].markPoint.data[0].coord).toEqual(["2026-02", 2]);
  });

  it("aligns series with different start periods using nulls", () => {
    const o = lineOption(
      {
        series: [
          { name: "A", points: pts([["2026-01", 1], ["2026-02", 2], ["2026-03", 3]]), color: "#111" },
          { name: "B", points: pts([["2026-02", 5], ["2026-03", 6]]), color: "#222" },
        ],
        unit: "people",
        frequency: "monthly",
      },
      TEST_THEME,
    ) as Opt;
    expect(o.xAxis.data).toEqual(["2026-01", "2026-02", "2026-03"]);
    expect(o.series[1].data).toEqual([null, 5, 6]);
    expect(o.legend).toBeDefined();
  });

  it("tooltips name the period, value, unit and provisional status", () => {
    const o = lineOption(
      input(pts([["2026-06", 100], ["2026-07", 5170, "provisional"]])),
      TEST_THEME,
    ) as Opt;
    const html: string = o.tooltip.formatter([{ axisValue: "2026-07", seriesName: "Net", value: 5170, marker: "●" }]);
    expect(html).toContain("Jul 2026");
    expect(html).toContain("5,170");
    expect(html).toContain("people");
    expect(html).toContain("(provisional)");
  });

  it("labels year-ended periods as such in tooltips", () => {
    const o = lineOption(input(pts([["2026-07", 20350]]), { frequency: "rolling_annual" }), TEST_THEME) as Opt;
    const html: string = o.tooltip.formatter([{ axisValue: "2026-07", seriesName: "Net", value: 20350, marker: "●" }]);
    expect(html).toContain("Year ended Jul 2026");
  });
});

describe("divergingBarOption", () => {
  it("colours bars by sign and lighter when provisional", () => {
    const o = divergingBarOption(
      { name: "Net", points: pts([["2026-05", -3], ["2026-06", 4], ["2026-07", 6, "provisional"]]), unit: "people", frequency: "monthly" },
      TEST_THEME,
    ) as Opt;
    const items = o.series[0].data;
    expect(items[0].itemStyle.color).toBe(TEST_THEME.negative);
    expect(items[1].itemStyle.color).toBe(TEST_THEME.positive);
    expect(items[2].itemStyle.opacity).toBeLessThan(1);
  });
});

describe("stackedPanelsOption", () => {
  it("keeps monthly and year-ended on separate axes and grids", () => {
    const o = stackedPanelsOption(
      { monthly: pts([["2026-06", 100], ["2026-07", 200]]), yearEnded: pts([["2026-07", 20350]]), unit: "people" },
      TEST_THEME,
    ) as Opt;
    expect(o.grid).toHaveLength(2);
    expect(o.yAxis).toHaveLength(2);
    expect(o.series.map((s: Opt) => s.yAxisIndex)).toEqual([0, 1]);
    expect(o.title.map((t: Opt) => t.text)).toEqual(["Monthly estimate", "Year ended (rolling 12 months)"]);
    expect(o.axisPointer.link[0].xAxisIndex).toBe("all");
  });
});

describe("rankedBarOption", () => {
  it("sorts descending top-to-bottom and dims provisional totals", () => {
    const o = rankedBarOption(
      { items: [{ name: "B", value: 2, provisional: false }, { name: "A", value: 9, provisional: true }], unit: "people" },
      TEST_THEME,
    ) as Opt;
    expect(o.yAxis.data).toEqual(["A", "B"]); // descending order; inverse axis puts the largest at the top
    expect(o.yAxis.inverse).toBe(true);
    expect(o.series[0].data[0].value).toBe(9);
  });
});

describe("revisionBarOption", () => {
  it("centres revisions on zero", () => {
    const o = revisionBarOption({ rows: [{ period: "2026-05", absolute: -10 }, { period: "2026-06", absolute: 25 }], unit: "people" }, TEST_THEME) as Opt;
    expect(o.series[0].markLine.data[0].yAxis).toBe(0);
    expect(o.series[0].data[0].itemStyle.color).toBe(TEST_THEME.negative);
  });
});

describe("sliceYears", () => {
  it("keeps the last N years relative to the latest period", () => {
    const all = pts([["2015-07", 1], ["2016-08", 2], ["2026-07", 3]]);
    expect(sliceYears(all, 10).map((p) => p.period)).toEqual(["2016-08", "2026-07"]);
    expect(sliceYears(all, null)).toHaveLength(3);
  });
});
