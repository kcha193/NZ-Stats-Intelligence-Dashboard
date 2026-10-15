import type { EChartsCoreOption } from "echarts/core";
import { escapeHtml, formatNumber, monthLabel, periodLabel } from "@/lib/format";
import type { ChartTheme } from "./theme";

export type Frequency = "monthly" | "rolling_annual";
export type ChartPoint = { period: string; value: number; status: string };
export type LineSeriesInput = { name: string; points: ChartPoint[]; color: string; dashed?: boolean };

const axisNumber = (v: number) => (Math.abs(v) >= 1000 ? `${formatNumber(v / 1000, { decimals: v % 1000 === 0 ? 0 : 1 })}k` : formatNumber(v));
const yearTick = (v: string) => (v.endsWith("-01") ? v.slice(0, 4) : "");

/** Every month from the first to the last period given, so a month with no observation keeps its
 * place on a category axis (and a line breaks there) instead of the neighbours closing up. */
export function monthAxis(periods: string[]): string[] {
  const sorted = [...new Set(periods)].sort();
  if (sorted.length < 2 || !sorted.every((p) => /^\d{4}-\d{2}$/.test(p))) return sorted;
  const [y0, m0] = sorted[0].split("-").map(Number);
  const [y1, m1] = sorted[sorted.length - 1].split("-").map(Number);
  const n = (y1 - y0) * 12 + (m1 - m0);
  if (n > 2400) return sorted;
  return Array.from({ length: n + 1 }, (_, i) => {
    const idx = y0 * 12 + (m0 - 1) + i;
    return `${String(Math.floor(idx / 12)).padStart(4, "0")}-${String((idx % 12) + 1).padStart(2, "0")}`;
  });
}

export function sliceYears(points: ChartPoint[], years: number | null): ChartPoint[] {
  if (years === null || points.length === 0) return points;
  const last = points[points.length - 1].period;
  const [y, m] = last.split("-").map(Number);
  const cutoff = `${String(y - years).padStart(4, "0")}-${String(m).padStart(2, "0")}`;
  return points.filter((p) => p.period > cutoff);
}

/** How a point's status is shown next to its value. Unknown is not final, so it is never left blank. */
const statusFlag = (status: string | undefined): string =>
  status === "provisional" ? " (provisional)" : status === "unknown" ? " (status unknown)" : "";

/** Maximal runs of consecutive axis periods that are provisional, as [first, last]. A final period
 * between two provisional ones ends a run, so a band never covers a period that is not provisional. */
export function provisionalRuns(periods: string[], isProvisional: (period: string) => boolean): [string, string][] {
  const runs: [string, string][] = [];
  let start: string | null = null;
  periods.forEach((p, i) => {
    if (isProvisional(p)) {
      start ??= p;
      if (i === periods.length - 1 || !isProvisional(periods[i + 1])) {
        runs.push([start, p]);
        start = null;
      }
    }
  });
  return runs;
}

const provisionalArea = (runs: [string, string][], theme: ChartTheme) => ({
  silent: true, itemStyle: { color: theme.provisionalBand },
  label: { show: true, color: theme.muted, position: "insideTop", formatter: "Provisional" },
  data: runs.map(([from, to]) => [{ xAxis: from }, { xAxis: to }]),
});

function tooltip(series: LineSeriesInput[], unit: string, frequency: Frequency) {
  return {
    trigger: "axis" as const,
    formatter: (params: { axisValue: string; seriesName: string; value: number | null; marker: string }[] | { axisValue: string; seriesName: string; value: number | null; marker: string }) => {
      const list = Array.isArray(params) ? params : [params];
      const period = String(list[0].axisValue);
      const rows = list
        .filter((p) => p.value !== null && p.value !== undefined)
        .map((p) => {
          const pt = series.find((s) => s.name === p.seriesName)?.points.find((x) => x.period === period);
          return `${p.marker} ${escapeHtml(p.seriesName)}: <b>${formatNumber(Number(p.value))}</b> ${unit}${statusFlag(pt?.status)}`;
        });
      return `<div>${periodLabel(period, frequency)}</div>${rows.join("<br/>")}`;
    },
  };
}

export function lineOption(
  input: { series: LineSeriesInput[]; unit: string; frequency: Frequency },
  theme: ChartTheme,
): EChartsCoreOption {
  const periods = monthAxis(input.series.flatMap((s) => s.points.map((p) => p.period)));
  const values = input.series.flatMap((s) => s.points.map((p) => p.value));
  const nonNegative = values.every((v) => v >= 0);
  const provisional = provisionalRuns(periods, (p) => input.series.some((s) => s.points.some((x) => x.period === p && x.status === "provisional")));

  const series = input.series.map((s, i) => {
    const byPeriod = new Map(s.points.map((p) => [p.period, p.value]));
    const latest = s.points[s.points.length - 1];
    const entry: Record<string, unknown> = {
      name: s.name, type: "line", showSymbol: false, connectNulls: false,
      lineStyle: { width: 2, color: s.color, type: s.dashed ? "dashed" : "solid" },
      itemStyle: { color: s.color },
      data: periods.map((p) => byPeriod.get(p) ?? null),
    };
    if (latest) {
      entry.markPoint = {
        symbol: "circle", symbolSize: 9, itemStyle: { color: s.color },
        label: { show: true, position: "right", color: theme.text, formatter: () => formatNumber(latest.value) },
        data: [{ coord: [latest.period, latest.value] }],
      };
    }
    if (i === 0) {
      if (!nonNegative) {
        entry.markLine = {
          silent: true, symbol: "none", label: { show: false },
          lineStyle: { color: theme.muted, width: 1 }, data: [{ yAxis: 0 }],
        };
      }
      if (provisional.length) entry.markArea = provisionalArea(provisional, theme);
    }
    return entry;
  });

  return {
    aria: { enabled: true },
    animation: false,
    textStyle: { color: theme.text },
    grid: { left: 56, right: 72, top: input.series.length > 1 ? 36 : 24, bottom: 28 },
    legend: input.series.length > 1 ? { top: 0, textStyle: { color: theme.text } } : undefined,
    tooltip: tooltip(input.series, input.unit, input.frequency),
    xAxis: {
      type: "category", data: periods, boundaryGap: false,
      axisLabel: { interval: 0, hideOverlap: true, color: theme.muted, formatter: yearTick },
      axisTick: { interval: (_: number, v: string) => v.endsWith("-01") },
      axisLine: { lineStyle: { color: theme.grid } },
    },
    yAxis: {
      type: "value", min: nonNegative ? 0 : undefined,
      axisLabel: { color: theme.muted, formatter: axisNumber },
      splitLine: { lineStyle: { color: theme.grid } },
    },
    series,
  };
}

export function divergingBarOption(
  input: { name: string; points: ChartPoint[]; unit: string; frequency: Frequency },
  theme: ChartTheme,
): EChartsCoreOption {
  const periods = monthAxis(input.points.map((p) => p.period));
  const byPeriod = new Map(input.points.map((p) => [p.period, p]));
  return {
    aria: { enabled: true }, animation: false, textStyle: { color: theme.text },
    grid: { left: 56, right: 24, top: 24, bottom: 28 },
    tooltip: tooltip([{ name: input.name, points: input.points, color: theme.series[0] }], input.unit, input.frequency),
    xAxis: { type: "category", data: periods, axisLabel: { interval: 0, hideOverlap: true, color: theme.muted, formatter: yearTick }, axisTick: { interval: (_: number, v: string) => v.endsWith("-01") }, axisLine: { lineStyle: { color: theme.muted } } },
    yAxis: { type: "value", axisLabel: { color: theme.muted, formatter: axisNumber }, splitLine: { lineStyle: { color: theme.grid } } },
    series: [{
      name: input.name, type: "bar",
      data: periods.map((period) => {
        const p = byPeriod.get(period);
        return p === undefined ? null : {
          value: p.value,
          itemStyle: { color: p.value < 0 ? theme.negative : theme.positive, opacity: p.status === "provisional" ? 0.55 : 1 },
        };
      }),
    }],
  };
}

export function stackedPanelsOption(
  input: { monthly: ChartPoint[]; yearEnded: ChartPoint[]; unit: string },
  theme: ChartTheme,
): EChartsCoreOption {
  const periods = monthAxis([...input.monthly, ...input.yearEnded].map((p) => p.period));
  // Both series keep their full points: the monthly and year-ended statuses are different facts.
  const yearEnded = new Map(input.yearEnded.map((p) => [p.period, p]));
  const monthly = new Map(input.monthly.map((p) => [p.period, p]));
  const provisionalYearEnded = provisionalRuns(periods, (p) => yearEnded.get(p)?.status === "provisional");
  const axisBase = { type: "category" as const, data: periods, axisLabel: { interval: 0, hideOverlap: true, color: theme.muted, formatter: yearTick }, axisTick: { interval: (_: number, v: string) => v.endsWith("-01") } };
  const valueAxis = (gridIndex: number) => ({ type: "value" as const, gridIndex, axisLabel: { color: theme.muted, formatter: axisNumber }, splitLine: { lineStyle: { color: theme.grid } } });
  return {
    aria: { enabled: true }, animation: false, textStyle: { color: theme.text },
    title: [
      { text: "Monthly estimate", left: 56, top: 0, textStyle: { fontSize: 12, color: theme.text } },
      { text: "Year ended (rolling 12 months)", left: 56, top: "52%", textStyle: { fontSize: 12, color: theme.text } },
    ],
    grid: [
      { left: 56, right: 72, top: 24, height: "36%" },
      { left: 56, right: 72, top: "58%", height: "32%" },
    ],
    axisPointer: { link: [{ xAxisIndex: "all" }] },
    tooltip: {
      trigger: "axis",
      formatter: (params: { axisValue: string; seriesName: string; value: number | null; marker: string }[]) => {
        const period = String(params[0].axisValue);
        const rows = params.filter((p) => p.value !== null).map((p) => {
          const point = (p.seriesName.startsWith("Monthly") ? monthly : yearEnded).get(period);
          return `${p.marker} ${escapeHtml(p.seriesName)}: <b>${formatNumber(Number(p.value))}</b> ${input.unit}${statusFlag(point?.status)}`;
        });
        return `<div>${monthLabel(period)}</div>${rows.join("<br/>")}`;
      },
    },
    xAxis: [
      { ...axisBase, gridIndex: 0, axisLabel: { show: false }, axisLine: { lineStyle: { color: theme.muted } } },
      { ...axisBase, gridIndex: 1, boundaryGap: false },
    ],
    yAxis: [valueAxis(0), valueAxis(1)],
    series: [
      {
        name: "Monthly net migration", type: "bar", xAxisIndex: 0, yAxisIndex: 0,
        data: periods.map((p) => {
          const pt = monthly.get(p);
          return pt === undefined ? null : { value: pt.value, itemStyle: { color: pt.value < 0 ? theme.negative : theme.positive, opacity: pt.status === "provisional" ? 0.55 : 1 } };
        }),
      },
      {
        name: "Year-ended net migration", type: "line", xAxisIndex: 1, yAxisIndex: 1, showSymbol: false,
        lineStyle: { width: 2, color: theme.series[0] }, itemStyle: { color: theme.series[0] },
        data: periods.map((p) => yearEnded.get(p)?.value ?? null),
        markLine: { silent: true, symbol: "none", label: { show: false }, lineStyle: { color: theme.muted, width: 1 }, data: [{ yAxis: 0 }] },
        ...(provisionalYearEnded.length ? { markArea: provisionalArea(provisionalYearEnded, theme) } : {}),
      },
    ],
  };
}

export function rankedBarOption(
  input: { items: { name: string; value: number; provisional: boolean }[]; unit: string },
  theme: ChartTheme,
): EChartsCoreOption {
  const items = [...input.items].sort((a, b) => b.value - a.value);
  return {
    aria: { enabled: true }, animation: false, textStyle: { color: theme.text },
    grid: { left: 150, right: 56, top: 8, bottom: 24 },
    tooltip: {
      trigger: "item",
      formatter: (p: { name: string; value: number; data: { provisional: boolean } }) =>
        `${escapeHtml(p.name)}: <b>${formatNumber(p.value)}</b> ${input.unit}${p.data.provisional ? " (includes provisional months)" : ""}`,
    },
    xAxis: { type: "value", min: 0, axisLabel: { color: theme.muted, formatter: axisNumber }, splitLine: { lineStyle: { color: theme.grid } } },
    yAxis: { type: "category", inverse: true, data: items.map((i) => i.name), axisLabel: { color: theme.text }, axisLine: { lineStyle: { color: theme.muted } } },
    series: [{
      type: "bar", barMaxWidth: 18,
      label: { show: true, position: "right", color: theme.text, formatter: (p: { value: number }) => formatNumber(p.value) },
      data: items.map((i) => ({ value: i.value, provisional: i.provisional, itemStyle: { color: i.provisional ? theme.provisionalBar : theme.series[0] } })),
    }],
  };
}

export function revisionBarOption(
  input: { rows: { period: string; absolute: number }[]; unit: string },
  theme: ChartTheme,
): EChartsCoreOption {
  return {
    aria: { enabled: true }, animation: false, textStyle: { color: theme.text },
    grid: { left: 56, right: 24, top: 24, bottom: 40 },
    tooltip: {
      trigger: "axis",
      formatter: (params: { axisValue: string; value: number }[]) =>
        `${monthLabel(String(params[0].axisValue))}: <b>${formatNumber(params[0].value, { signed: true })}</b> ${input.unit} revision`,
    },
    xAxis: { type: "category", data: input.rows.map((r) => r.period), axisLabel: { color: theme.muted, rotate: 45, formatter: (v: string) => monthLabel(v) } },
    yAxis: { type: "value", axisLabel: { color: theme.muted, formatter: axisNumber }, splitLine: { lineStyle: { color: theme.grid } } },
    series: [{
      type: "bar",
      markLine: { silent: true, symbol: "none", label: { show: false }, lineStyle: { color: theme.muted, width: 1 }, data: [{ yAxis: 0 }] },
      data: input.rows.map((r) => ({ value: r.absolute, itemStyle: { color: r.absolute < 0 ? theme.negative : theme.positive } })),
    }],
  };
}
