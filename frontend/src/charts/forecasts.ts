import type { EChartsCoreOption } from "echarts/core";
import type { ForecastGroup } from "@/api/types";
import { escapeHtml, formatAklDate, formatNumber } from "@/lib/format";
import type { ChartTheme } from "./theme";

/** The latest Stats NZ observation of the same statistic, drawn as a reference line: an observation, not a forecast. */
export type Observation = { value: number; label: string };

const ROW_HEIGHT = 44;
const AXIS_BAND = 72;

export const forecastChartHeight = (rows: number) => Math.max(140, rows * ROW_HEIGHT + AXIS_BAND);

/** A value axis that always includes zero, with a little room past the furthest mark for its label. */
export function valueRange(values: number[]): { min: number; max: number } {
  const lo = Math.min(0, ...values);
  const hi = Math.max(0, ...values);
  const pad = Math.max((hi - lo) * 0.15, 0.5);
  const step = (v: number, dir: 1 | -1) => (dir > 0 ? Math.ceil(v * 2) / 2 : Math.floor(v * 2) / 2);
  return { min: lo < 0 ? step(lo - pad, -1) : 0, max: hi > 0 || lo === 0 ? step(hi + pad, 1) : 0 };
}

export const formatForecastValue = (value: number, unitLabel: string): string =>
  unitLabel === "%" ? `${formatNumber(value, { decimals: 2 }).replace(/0$/, "")}%` : `${formatNumber(value, { decimals: 2 }).replace(/\.?0+$/, "")} ${unitLabel}`;

export function forecastOption(group: ForecastGroup, theme: ChartTheme, observation?: Observation | null): EChartsCoreOption {
  const rows = group.rows.map((r) => r.forecast);
  const values = rows.map((f) => f.value ?? 0);
  const range = valueRange(observation ? [...values, observation.value] : values);
  const hollow = group.kind === "scenario";
  const ink = theme.series[0];
  const show = (v: number) => formatForecastValue(v, group.unit_label);
  return {
    aria: { enabled: true }, animation: false, textStyle: { color: theme.text },
    grid: { left: 8, right: 56, top: observation ? 32 : 16, bottom: 40, containLabel: true },
    xAxis: {
      type: "value", min: range.min, max: range.max,
      axisLabel: { color: theme.muted, formatter: (v: number) => `${formatNumber(v, { decimals: Number.isInteger(v) ? 0 : 1 })}${group.unit_label === "%" ? "%" : ""}` },
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
