import type { EChartsCoreOption } from "echarts/core";
import type { FirstLatestTable, GdpSeries, LabourSeries } from "@/api/types";
import { escapeHtml, formatNumber, monthLabel } from "@/lib/format";
import { barRates, type CpiRange, lineRates, rangeFilter } from "./cpi";
import type { ChartTheme } from "./theme";

type Meta = { releaseKey: string; sourceUrl: string | null };
const rows = (points: { period: string; value: number }[]) => points.map((p) => ({ period: p.period, value: p.value }));

/** One GDP growth measure per chart: quarterly growth as signed bars, the annual measures as a line. */
export function growthOption(series: GdpSeries, range: CpiRange, theme: ChartTheme): EChartsCoreOption {
  const data = rows(rangeFilter(series.points, range));
  return series.measure === "quarterly_change"
    ? barRates(series.name, data, "Quarterly change (%)", theme)
    : lineRates(series.name, data, series.measure === "annual_average_change" ? "Annual average change (%)" : "Annual change (%)", theme);
}

/** One labour market rate (or LCI change) per chart, on its own percent axis. */
export function rateOption(series: LabourSeries, range: CpiRange, theme: ChartTheme): EChartsCoreOption {
  return lineRates(series.name, rows(rangeFilter(series.points, range)), series.unit === "percent" ? "Percent" : series.unit, theme);
}

const LABELS = ["Stored baseline", "Latest"] as const;

/** First-published against latest value of each recent quarter: the revision, shown as paired bars. */
export function firstLatestOption(table: FirstLatestTable, theme: ChartTheme, unit: string): EChartsCoreOption {
  const ordered = [...table.rows].sort((a, b) => a.period.localeCompare(b.period));
  const fmt = (v: number) => `${formatNumber(v, { decimals: 1 })}${unit}`;
  const bar = (name: string, color: string, values: number[]) => ({
    name, type: "bar", barMaxWidth: 14, barGap: "20%", itemStyle: { color, borderRadius: [4, 4, 0, 0] }, data: values,
  });
  return {
    aria: { enabled: true }, animation: false, textStyle: { color: theme.text },
    grid: { left: 56, right: 24, top: 40, bottom: 28 },
    legend: { data: [...LABELS], top: 0, left: 56, textStyle: { color: theme.text } },
    tooltip: {
      trigger: "axis",
      formatter: (params: { dataIndex: number }[] | { dataIndex: number }) => {
        const r = ordered[(Array.isArray(params) ? params[0] : params).dataIndex];
        const basis = r.first_is_publication ? "first published" : "earliest stored";
        return `Quarter ended ${escapeHtml(monthLabel(r.period))}<br/>${fmt(r.first_value)} ${basis} (${escapeHtml(r.first_release)})`
          + `<br/>${fmt(r.latest_value)} latest (${escapeHtml(r.latest_release)})<br/>Revision: <b>${formatNumber(r.revision, { decimals: 1 })} points</b>`;
      },
    },
    xAxis: {
      type: "category", data: ordered.map((r) => r.period),
      axisLabel: { color: theme.muted, formatter: (p: string) => monthLabel(p) }, axisLine: { lineStyle: { color: theme.muted } },
    },
    yAxis: {
      type: "value", axisLabel: { color: theme.muted, formatter: (v: number) => fmt(v) },
      splitLine: { lineStyle: { color: theme.grid } },
    },
    series: [
      bar(LABELS[0], theme.series[1], ordered.map((r) => r.first_value)),
      bar(LABELS[1], theme.series[0], ordered.map((r) => r.latest_value)),
    ],
  };
}

export function firstLatestRows(table: FirstLatestTable, meta: Meta) {
  return [...table.rows].sort((a, b) => a.period.localeCompare(b.period)).map((r) => ({
    period: r.period, series_key: table.series_key, first_value: r.first_value,
    first_basis: r.first_is_publication ? "first published" : "earliest stored", first_release: r.first_release,
    latest_value: r.latest_value, latest_release: r.latest_release, revision: r.revision,
    release_key: meta.releaseKey, source_url: meta.sourceUrl ?? "",
  }));
}
