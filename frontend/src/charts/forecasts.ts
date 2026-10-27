import type { EChartsCoreOption } from "echarts/core";
import type { ForecastGroup } from "@/api/types";
import { escapeHtml, formatAklDate, formatNumber } from "@/lib/format";
import type { ChartTheme } from "./theme";

/** The latest Stats NZ observation of the same statistic, drawn as a reference line: an observation, not a forecast. */
export type Observation = { value: number; label: string };

const ROW_HEIGHT = 44;
const AXIS_BAND = 72;

export const forecastChartHeight = (rows: number) => Math.max(140, rows * ROW_HEIGHT + AXIS_BAND);

export type ValueRange = { min: number; max: number; step: number; zero: boolean };

/**
 * A value axis for positions (dots and lines), not lengths. Zero is kept when the values cross it or the axis would start
 * within one span of it; otherwise the axis starts near the data so close levels (OCR 2.5% and 2.75%) separate. The span
 * never shrinks below `minSpan` (one percentage point for rates), so a small difference never fills the whole width.
 */
export function valueRange(values: number[], minSpan = 1): ValueRange {
  if (values.length === 0) return { min: 0, max: 1, step: 0.25, zero: true };
  let lo = Math.min(...values);
  let hi = Math.max(...values);
  const pad = Math.max((hi - lo) * 0.15, 0.25);
  lo -= pad;
  hi += pad;
  if (hi - lo < minSpan) {
    const mid = (lo + hi) / 2;
    lo = mid - minSpan / 2;
    hi = mid + minSpan / 2;
  }
  const span = hi - lo;
  if (lo > 0 && lo <= span) lo = 0;
  if (hi < 0 && -hi <= span) hi = 0;
  // Ticks on a round step (at most six intervals), with the ends on the step so every gap is equal.
  const step = STEPS.find((st) => (hi - lo) / st <= 6) ?? 10 ** Math.ceil(Math.log10((hi - lo) / 6));
  const min = Math.floor(lo / step + 1e-9) * step;
  const max = Math.ceil(hi / step - 1e-9) * step;
  return { min, max, step, zero: min <= 0 && max >= 0 };
}

const STEPS = [0.25, 0.5, 1, 2, 2.5, 5, 10, 20, 25, 50, 100];

/** The smallest honest span for a unit: one point for rates and shares, a tenth of the magnitude otherwise. */
export const minSpanFor = (unitLabel: string, values: number[]) =>
  unitLabel.startsWith("%") || unitLabel.includes("percentage") ? 1 : Math.max(Math.max(...values.map(Math.abs), 0) * 0.1, 1e-6);

/** Said beside any chart whose value axis does not include zero. */
export const axisNote = (r: ValueRange, unitLabel: string): string | null =>
  r.zero ? null : `The axis runs from ${formatNumber(r.min, { decimals: Number.isInteger(r.min) ? 0 : Number.isInteger(r.min * 2) ? 1 : 2 })}${unitLabel === "%" ? "%" : ` ${unitLabel}`}, not zero: marks show positions to compare, not amounts.`;

export const formatForecastValue = (value: number, unitLabel: string): string =>
  unitLabel === "%" ? `${formatNumber(value, { decimals: 2 }).replace(/0$/, "")}%` : `${formatNumber(value, { decimals: 2 }).replace(/\.?0+$/, "")} ${unitLabel}`;

export function forecastOption(group: ForecastGroup, theme: ChartTheme, observation?: Observation | null): EChartsCoreOption {
  const rows = group.rows.map((r) => r.forecast);
  const values = rows.map((f) => f.value ?? 0);
  const all = observation ? [...values, observation.value] : values;
  const range = valueRange(all, minSpanFor(group.unit_label, all));
  const hollow = group.kind === "scenario";
  const ink = theme.series[0];
  const show = (v: number) => formatForecastValue(v, group.unit_label);
  return {
    aria: { enabled: true }, animation: false, textStyle: { color: theme.text },
    grid: { left: 8, right: 56, top: observation ? 32 : 16, bottom: 40, containLabel: true },
    xAxis: {
      type: "value", min: range.min, max: range.max, interval: range.step,
      axisLabel: { color: theme.muted, formatter: (v: number) => `${formatNumber(v, { decimals: Number.isInteger(v) ? 0 : Number.isInteger(v * 2) ? 1 : 2 })}${group.unit_label === "%" ? "%" : ""}` },
      splitLine: { lineStyle: { color: theme.grid } }, axisLine: { lineStyle: { color: theme.grid } },
    },
    yAxis: {
      type: "category", inverse: true, data: rows.map((f) => f.institution.name),
      axisTick: { show: false }, axisLine: { show: false }, axisLabel: { color: theme.text, width: 132, overflow: "break", lineHeight: 14 },
    },
    tooltip: {
      trigger: "item",
      formatter: (p: { dataIndex: number }) => {
        const f = rows[p.dataIndex];
        const vintage = f.published_on ? `<br/>Published ${formatAklDate(`${f.published_on}T00:00:00+12:00`)}` : "";
        const note = f.qualification ? `<br/>${escapeHtml(f.qualification)}` : "";
        return `${escapeHtml(f.institution.name)}<br/><b>${show(f.value ?? 0)}</b> ${escapeHtml(group.horizon_label)}${vintage}${note}`;
      },
    },
    series: [{
      type: "scatter", name: hollow ? `Scenario: ${group.scenario ?? ""}` : "Central forecast",
      symbol: "circle", symbolSize: 12,
      data: rows.map((f, i) => [f.value, i]),
      itemStyle: hollow ? { color: theme.surface, borderColor: ink, borderWidth: 2 } : { color: ink, borderColor: theme.surface, borderWidth: 2 },
      label: { show: true, position: "right", distance: 8, color: theme.text, formatter: (p: { value: [number, number] }) => show(p.value[0]) },
      emphasis: { scale: 1.3 },
      ...(observation ? {
        markLine: {
          silent: true, symbol: "none",
          lineStyle: { color: theme.series[1], width: 2, type: "solid" },
          // Canvas text, not HTML: drawn as written, so it is not escaped (escaping would show the entities).
          label: { color: theme.text, formatter: `${observation.label}: ${formatNumber(observation.value, { decimals: 1 })}${group.unit_label === "%" ? "%" : ""}`, position: "start" }, // the top: the category axis is inverted
          data: [{ xAxis: observation.value }],
        },
      } : {}),
    }],
  };
}
