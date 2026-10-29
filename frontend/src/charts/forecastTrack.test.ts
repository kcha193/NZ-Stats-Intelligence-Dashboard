import { describe, expect, it } from "vitest";
import type { EvaluatedForecast, ForecastEvaluation, ForecastHistory } from "@/api/types";
import evaluation from "@/test/fixtures/research_synthetic_evaluation.json";
import history from "@/test/fixtures/research_synthetic_history.json";
import { dateBounds, errorOption, revisionOption } from "./forecastTrack";
import { valueRange } from "./forecasts";
import { TEST_THEME } from "./theme";

// SYNTHETIC FIXTURE research (fictional institutions) over real Stats NZ CPI outcomes.
const h = history as unknown as ForecastHistory;
const e = evaluation as unknown as ForecastEvaluation;
type Line = { series: { data: [number, number][]; lineStyle: { color: string }; markLine?: { data: { yAxis: number }[] } }[];
  tooltip: { formatter: (p: { dataIndex: number }) => string }; yAxis: { min: number; max: number } };
type Dots = { series: { data: [number, number][]; itemStyle: { color: string } }[]; yAxis: { data: string[] };
  xAxis: { min: number; max: number }; tooltip: { formatter: (p: { dataIndex: number }) => string } };

const target = "cpi_inflation|percent|annual_change|year_to:2027-06|central";
const panels = h.series.filter((s) => s.target_key === target);

describe("revision panels", () => {
  it("draw each vintage in order, in the forecast colour, on axes shared by every institution", () => {
    const harbourside = panels.find((s) => s.institution.key === "harbourside")!;
    const range = valueRange(panels.flatMap((s) => s.vintages.map((v) => v.value)));
    const o = revisionOption(harbourside, TEST_THEME, range, dateBounds(panels)) as unknown as Line;
    expect(o.series[0].data.map((d) => d[1])).toEqual([2.5, 2.7, 2.3]);
    expect(o.series[0].lineStyle.color).toBe(TEST_THEME.series[0]);
    expect(o.yAxis).toMatchObject({ min: range.min, max: range.max });
    expect(o.series[0].markLine).toBeUndefined();
  });

  it("say whether each vintage was a revision, and escape document titles", () => {
    const s = structuredClone(panels.find((x) => x.institution.key === "harbourside")!);
    s.vintages[0].document_title = "<img src=x onerror=alert(1)>";
    const o = revisionOption(s, TEST_THEME, valueRange([2, 3]), dateBounds([s])) as unknown as Line;
    expect(o.tooltip.formatter({ dataIndex: 0 })).toContain("First vintage");
    expect(o.tooltip.formatter({ dataIndex: 0 })).toContain("&lt;img");
    expect(o.tooltip.formatter({ dataIndex: 1 })).toMatch(/Revised \+0\.2/);
    expect(o.tooltip.formatter({ dataIndex: 2 })).toMatch(/Revised −0\.4/);
  });

  it("mark the official outcome only when one is given", () => {
    const s = h.series.find((x) => x.target_key.includes("year_to:2026-06") && x.institution.key === "harbourside")!;
    const o = revisionOption(s, TEST_THEME, valueRange([3, 4.1]), dateBounds([s]), { value: 4.1, label: "First published" }) as unknown as Line;
    expect(o.series[0].markLine!.data[0].yAxis).toBe(4.1);
  });
});

describe("forecast errors", () => {
  // Simulated verified scores test the drawing primitive; real historical fixture outcomes remain unscored.
  const matched = e.evaluated.filter((r) => r.status === "matched").map((r) => ({ ...r,
    first: { ...r.first!, first_release: true }, error_first: r.forecast.value! - r.first!.value,
  })) as EvaluatedForecast[];

  it("place one dot per matched forecast on a symmetric axis around zero", () => {
    const o = errorOption(matched, TEST_THEME) as unknown as Dots;
    expect(o.series[0].data).toHaveLength(matched.length);
    expect(o.xAxis.min).toBe(-o.xAxis.max);
    expect(o.xAxis.max).toBeGreaterThanOrEqual(Math.max(...matched.map((r) => Math.abs(r.error_first!))));
    expect(o.series[0].itemStyle.color).toBe(TEST_THEME.series[0]);
  });

  it("explain each dot with the target, the outcome and the horizon", () => {
    const o = errorOption(matched, TEST_THEME) as unknown as Dots;
    const text = matched.map((_, i) => o.tooltip.formatter({ dataIndex: i })).join(" ");
    expect(text).toMatch(/June 2026 quarter/);
    expect(text).toMatch(/outcome 4\.1%/);
  });
});
