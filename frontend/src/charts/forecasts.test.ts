import { describe, expect, it } from "vitest";
import type { ForecastGroup } from "@/api/types";
import { forecastChartHeight, forecastOption, valueRange } from "./forecasts";
import { TEST_THEME } from "./theme";

// SYNTHETIC FIXTURE: fictional institutions and values.
const forecast = (key: string, name: string, value: number, over = {}) => ({
  summary_id: 1, institution: { key, name, kind: "bank" }, document_title: "Synthetic outlook", published_on: "2026-08-13",
  indicator: "cpi_inflation", indicator_label: "Annual CPI inflation", horizon: "year to June 2027", value, unit: "percent",
  direction: "down", scenario: null, qualification: null, evidence: [], ...over,
});
const group = (over: Partial<ForecastGroup> = {}): ForecastGroup => ({
  key: "k", indicator: "cpi_inflation", indicator_name: "CPI inflation", unit: "percent", unit_label: "%",
  basis: "annual_change", basis_label: "Annual change (through the year)", horizon_key: "year_to:2027-06",
  horizon_label: "Year to June 2027", kind: "central", scenario: null, comparable: true, note: "",
  rows: [
    { forecast: forecast("alpha", "Kowhai Bank <img src=x onerror=alert(1)>", 2.1), earlier_vintages: [] },
    { forecast: forecast("beta", "Tasman Economics", 2.4, { qualification: "assumes <b>stable</b> oil" }), earlier_vintages: [] },
  ],
  ...over,
});

type Opt = { yAxis: { data: string[]; inverse: boolean }; xAxis: { min: number; max: number }; series: { data: unknown[]; itemStyle: { color: string; borderColor: string }; markLine?: { data: { xAxis: number }[] } }[]; tooltip: { formatter: (p: { dataIndex: number }) => string } };

describe("forecast dot plot", () => {
  it("puts one row per institution, top to bottom in the group's order", () => {
    const o = forecastOption(group(), TEST_THEME) as unknown as Opt;
    expect(o.yAxis.data).toEqual(["Kowhai Bank <img src=x onerror=alert(1)>", "Tasman Economics"]);
    expect(o.yAxis.inverse).toBe(true);
    expect(o.series[0].data).toHaveLength(2);
  });

  it("starts the value axis at zero and keeps negative values in view", () => {
    expect(valueRange([2.1, 2.4]).min).toBe(0);
    expect(valueRange([2.1, 2.4]).max).toBeGreaterThan(2.4);
    const r = valueRange([-1.2, 0.8]);
    expect(r.min).toBeLessThan(-1.2);
    expect(r.max).toBeGreaterThan(0.8);
    expect(valueRange([]).max).toBeGreaterThan(0);
  });

  it("draws central forecasts filled and scenarios hollow, in the one forecast colour", () => {
    const central = forecastOption(group(), TEST_THEME) as unknown as Opt;
    expect(central.series[0].itemStyle.color).toBe(TEST_THEME.series[0]);
    const scenario = forecastOption(group({ kind: "scenario", scenario: "Downside" }), TEST_THEME) as unknown as Opt;
    expect(scenario.series[0].itemStyle.color).toBe(TEST_THEME.surface);
    expect(scenario.series[0].itemStyle.borderColor).toBe(TEST_THEME.series[0]);
  });

  it("marks the official observation only when one is given, inside the axis range", () => {
    expect((forecastOption(group(), TEST_THEME) as unknown as Opt).series[0].markLine).toBeUndefined();
    const o = forecastOption(group(), TEST_THEME, { value: 4.06, label: "Stats NZ, quarter ended June 2026" }) as unknown as Opt;
    expect(o.series[0].markLine!.data[0].xAxis).toBe(4.06);
    expect(o.xAxis.max).toBeGreaterThan(4.06);
  });

  it("escapes upstream text in tooltips", () => {
    const o = forecastOption(group(), TEST_THEME) as unknown as Opt;
    const html = o.tooltip.formatter({ dataIndex: 0 }) + o.tooltip.formatter({ dataIndex: 1 });
    expect(html).not.toContain("<img");
    expect(html).toContain("&lt;img src=x onerror=alert(1)&gt;");
    expect(html).toContain("assumes &lt;b&gt;stable&lt;/b&gt; oil");
    expect(html).toContain("2.1%");
  });

  it("grows with the number of rows so axis labels are never clipped", () => {
    expect(forecastChartHeight(1)).toBeLessThan(forecastChartHeight(6));
    expect(forecastChartHeight(1)).toBeGreaterThanOrEqual(140);
  });
});
