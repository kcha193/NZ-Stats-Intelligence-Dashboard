import { describe, expect, it } from "vitest";
import type { ForecastGroup } from "@/api/types";
import { axisNote, forecastChartHeight, forecastOption, valueRange } from "./forecasts";
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

  it("separates close levels instead of starting every axis at zero", () => {
    // OCR 2.5 and 2.75: padded to [2.25, 3.0], widened to the one-point minimum [2.125, 3.125], rounded out to quarters.
    expect(valueRange([2.5, 2.75])).toEqual({ min: 2, max: 3.25, step: 0.25, zero: false });
    // CPI 2.1 and 2.4: [1.85, 2.65] widened to [1.75, 2.75]; zero is more than one span away, so it is left out.
    expect(valueRange([2.1, 2.4])).toEqual({ min: 1.75, max: 2.75, step: 0.25, zero: false });
  });

  it("keeps zero when the data come within one span of it, and when they cross it", () => {
    // 2.1 to 4.06 padded to [1.81, 4.35]: the start is within one span (2.55) of zero, so the axis starts there; a
    // 4.35-point span takes a step of 1 (at most six intervals), so the axis ends at 5.
    expect(valueRange([2.1, 2.4, 4.06])).toEqual({ min: 0, max: 5, step: 1, zero: true });
    const r = valueRange([-1.2, 0.8]);
    expect(r.zero).toBe(true);
    expect(r.min).toBeLessThan(-1.2);
    expect(r.max).toBeGreaterThan(0.8);
    expect(valueRange([])).toEqual({ min: 0, max: 1, step: 0.25, zero: true });
  });

  it("puts both ends on the tick step, so every gap between ticks is equal", () => {
    for (const values of [[2.25, 3.4], [43.5], [-0.3, 2.9], [1.6, 2.8, 4.06]]) {
      const r = valueRange(values);
      expect(Math.abs(r.min / r.step - Math.round(r.min / r.step))).toBeLessThan(1e-9);
      expect(Math.abs(r.max / r.step - Math.round(r.max / r.step))).toBeLessThan(1e-9);
      expect((r.max - r.min) / r.step).toBeLessThanOrEqual(7);
    }
  });

  it("never lets a small difference fill the axis", () => {
    const r = valueRange([2.5, 2.55]);
    expect(r.max - r.min).toBeGreaterThanOrEqual(1);
  });

  it("says when the axis does not start at zero", () => {
    expect(axisNote(valueRange([2.1, 2.4, 4.06]), "%")).toBeNull();
    expect(axisNote(valueRange([2.5, 2.75]), "%")).toMatch(/runs from 2%, not zero/);
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
