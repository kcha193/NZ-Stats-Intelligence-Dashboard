import type { EChartsCoreOption } from "echarts/core";
import type { BankConsensusGroup } from "@/api/bank";
import { escapeHtml } from "@/lib/format";
import { formatForecastValue, minSpanFor, valueRange } from "./forecasts";
import type { ChartTheme } from "./theme";

/**
 * Where the banks stand on one measure and target: a dot per bank on a shared value axis, the group's own median (from
 * two banks) and range band (from three), and the reference institutions as diamonds that never move either. One
 * option per group: groups differ in measure, period or adjustment, so they never share an axis.
 */
export function bankConsensusOption(g: BankConsensusGroup, theme: ChartTheme): EChartsCoreOption {
  const banks = g.contributors;
  const refs = g.markers;
  const names = [...banks.map((b) => b.name), ...refs.map((r) => r.name)];
  const values = [...banks, ...refs].map((p) => p.value);
  const range = valueRange(values, minSpanFor(g.unit_label, values));
  const show = (v: number) => formatForecastValue(v, g.unit_label);
  const median = g.n >= 2 && g.median !== null && g.median !== undefined ? g.median : null;
  const band = g.n >= 3 && g.minimum !== null && g.minimum !== undefined && g.maximum !== null && g.maximum !== undefined;
  return {
    aria: { enabled: true }, animation: false, textStyle: { color: theme.text },
    grid: { left: 8, right: 56, top: 28, bottom: 36, containLabel: true },
    xAxis: {
      type: "value", min: range.min, max: range.max, interval: range.step,
      axisLabel: { color: theme.muted, formatter: (v: number) => formatForecastValue(v, g.unit_label) },
      splitLine: { lineStyle: { color: theme.grid } }, axisLine: { lineStyle: { color: theme.grid } },
    },
    yAxis: { type: "category", inverse: true, data: names, axisTick: { show: false }, axisLine: { show: false }, axisLabel: { color: theme.text, width: 140, overflow: "break" } },
    tooltip: {
      trigger: "item",
      formatter: (p: { dataIndex: number; seriesName: string }) => {
        const row = p.seriesName === "Reference" ? refs[p.dataIndex] : banks[p.dataIndex];
        return `${escapeHtml(row.name)}<br/><b>${show(row.value)}</b><br/>Published ${escapeHtml(row.published_on ?? "date not stated")}`
          + (p.seriesName === "Reference" ? "<br/>Reference only: not part of the bank figures" : "");
      },
    },
    series: [
      {
        type: "scatter", name: "Banks", symbol: "circle", symbolSize: 12,
        itemStyle: { color: theme.series[0], borderColor: theme.surface, borderWidth: 2 },
        data: banks.map((b, i) => [b.value, i]),
        ...(median !== null ? {
          markLine: {
            silent: true, symbol: "none", lineStyle: { color: theme.muted, width: 1, type: "dashed" },
            label: { color: theme.text, position: "insideEndTop", formatter: `Median ${show(median)}` },
            data: [{ xAxis: median }],
          },
        } : {}),
        ...(band ? {
          markArea: { silent: true, itemStyle: { color: theme.provisionalBand }, data: [[{ xAxis: g.minimum }, { xAxis: g.maximum }]] },
        } : {}),
      },
      ...(refs.length > 0 ? [{
        type: "scatter", name: "Reference", symbol: "diamond", symbolSize: 13,
        itemStyle: { color: theme.series[1], borderColor: theme.surface, borderWidth: 2 },
        data: refs.map((r, i) => [r.value, banks.length + i]),
      }] : []),
    ],
  };
}
