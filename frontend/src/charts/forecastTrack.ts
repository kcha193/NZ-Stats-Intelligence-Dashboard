import type { EChartsCoreOption } from "echarts/core";
import type { EvaluatedForecast, ForecastSeries } from "@/api/types";
import { escapeHtml, formatNumber } from "@/lib/format";
import { formatForecastValue, type ValueRange } from "./forecasts";
import type { ChartTheme } from "./theme";

/** The official outcome for the target, drawn as a reference line on every panel: an observation, not a forecast. */
export type Outcome = { value: number; label: string };

const day = (d: string | null | undefined) => (d ? Date.parse(`${d}T00:00:00Z`) : NaN);
const signed = (v: number, unit: string) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${formatForecastValue(Math.abs(v), unit)}`;

/**
 * One institution's vintages for one target: a step-free line through each publication's forecast, on a value axis and a
 * time axis shared by every panel of the target (small multiples, one colour; the outcome in the observation colour).
 */
export function revisionOption(
  series: ForecastSeries, theme: ChartTheme, range: ValueRange, dates: { min: number; max: number }, outcome?: Outcome | null,
): EChartsCoreOption {
  const dated = series.vintages.filter((v) => !Number.isNaN(day(v.published_on)));
  const unit = series.unit_label;
  return {
    aria: { enabled: true }, animation: false, textStyle: { color: theme.text },
    grid: { left: 8, right: 16, top: outcome ? 28 : 12, bottom: 28, containLabel: true },
    xAxis: {
      type: "time", min: dates.min, max: dates.max,
      axisLabel: { color: theme.muted, hideOverlap: true, formatter: "{MMM} {yy}" },
      axisLine: { lineStyle: { color: theme.grid } }, splitLine: { show: false },
    },
    yAxis: {
      type: "value", min: range.min, max: range.max, interval: range.step,
      axisLabel: { color: theme.muted, formatter: (v: number) => `${formatNumber(v, { decimals: Number.isInteger(v) ? 0 : Number.isInteger(v * 2) ? 1 : 2 })}${unit === "%" ? "%" : ""}` },
      splitLine: { lineStyle: { color: theme.grid } },
    },
    tooltip: {
      trigger: "item",
      formatter: (p: { dataIndex: number }) => {
        const v = dated[p.dataIndex];
        const change = v.revision === null || v.revision === undefined ? "First vintage" : v.revision === 0 ? "Unchanged" : `Revised ${signed(v.revision, unit)}`;
        return `${escapeHtml(v.document_title)}<br/>Published ${escapeHtml(v.published_on ?? "")}<br/><b>${formatForecastValue(v.value, unit)}</b>. ${change}`;
      },
    },
    series: [{
      type: "line", name: series.institution.name, symbol: "circle", symbolSize: 9,
      lineStyle: { color: theme.series[0], width: 2 },
      itemStyle: { color: theme.series[0], borderColor: theme.surface, borderWidth: 2 },
      label: { show: true, position: "top", color: theme.text, formatter: (p: { value: [number, number] }) => formatForecastValue(p.value[1], unit) },
      data: dated.map((v) => [day(v.published_on), v.value]),
      ...(outcome ? {
        markLine: {
          silent: true, symbol: "none", lineStyle: { color: theme.series[1], width: 2, type: "solid" },
          // Canvas text, not HTML: drawn as written, so not escaped.
          label: { color: theme.text, position: "insideStartTop", formatter: `${outcome.label}: ${formatForecastValue(outcome.value, unit)}` },
          data: [{ yAxis: outcome.value }],
        },
      } : {}),
    }],
  };
}

/** Shared time bounds for a target's panels, with a little room either side. */
export function dateBounds(series: ForecastSeries[]): { min: number; max: number } {
  const all = series.flatMap((s) => s.vintages.map((v) => day(v.published_on))).filter((t) => !Number.isNaN(t));
  if (all.length === 0) return { min: 0, max: 1 };
  const pad = Math.max((Math.max(...all) - Math.min(...all)) * 0.08, 20 * 86_400_000);
  return { min: Math.min(...all) - pad, max: Math.max(...all) + pad };
}

/** Signed errors (forecast minus first-published outcome), one row per institution, one dot per forecast, a zero line. */
export function errorOption(rows: EvaluatedForecast[], theme: ChartTheme): EChartsCoreOption {
  const matched = rows.filter((r) => r.error_first !== null && r.error_first !== undefined);
  const names = [...new Map(matched.map((r) => [r.forecast.institution.key, r.forecast.institution.name])).values()];
  const reach = Math.max(0.5, ...matched.map((r) => Math.abs(r.error_first as number)));
  const edge = Math.ceil(reach * 1.25 * 4) / 4;
  return {
    aria: { enabled: true }, animation: false, textStyle: { color: theme.text },
    grid: { left: 8, right: 24, top: 12, bottom: 40, containLabel: true },
    xAxis: {
      type: "value", min: -edge, max: edge, name: "Forecast minus outcome (percentage points)", nameLocation: "middle", nameGap: 28,
      nameTextStyle: { color: theme.muted },
      axisLabel: { color: theme.muted, formatter: (v: number) => (v > 0 ? `+${v}` : `${v}`.replace("-", "−")) },
      splitLine: { lineStyle: { color: theme.grid } },
    },
    yAxis: { type: "category", inverse: true, data: names, axisTick: { show: false }, axisLine: { show: false }, axisLabel: { color: theme.text, width: 132, overflow: "break" } },
    tooltip: {
      trigger: "item",
      formatter: (p: { dataIndex: number }) => {
        const r = matched[p.dataIndex];
        const f = r.forecast;
        const ahead = r.horizon_quarters <= 0 ? "made in or after the quarter" : `${r.horizon_quarters} quarter${r.horizon_quarters === 1 ? "" : "s"} ahead`;
        return `${escapeHtml(f.institution.name)}, ${escapeHtml(r.target_label)}<br/>Forecast ${formatForecastValue(f.value ?? 0, "%")}, outcome ${formatForecastValue(r.first?.value ?? 0, "%")}`
          + `<br/><b>${signed(r.error_first as number, "percentage points")}</b>, ${ahead}<br/>Published ${escapeHtml(f.published_on ?? "")}`;
      },
    },
    series: [{
      type: "scatter", name: "Forecast error", symbol: "circle", symbolSize: 11,
      itemStyle: { color: theme.series[0], borderColor: theme.surface, borderWidth: 2 },
      data: matched.map((r) => [r.error_first, names.indexOf(r.forecast.institution.name)]),
      markLine: { silent: true, symbol: "none", lineStyle: { color: theme.muted, width: 1, type: "solid" }, label: { show: false }, data: [{ xAxis: 0 }] },
    }],
  };
}
