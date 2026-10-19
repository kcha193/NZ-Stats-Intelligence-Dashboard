import type { EChartsCoreOption } from "echarts/core";
import type { CpiContributionBlock, CpiPoint, CpiSeries } from "@/api/types";
import { escapeHtml, formatNumber, monthLabel } from "@/lib/format";
import { zoomedRange } from "./ect";
import type { ChartTheme } from "./theme";

export type CpiRange = "3y" | "5y" | "10y" | "full";
export const CPI_RANGES: { value: CpiRange; label: string; quarters: number | null }[] = [
  { value: "3y", label: "3 years", quarters: 12 },
  { value: "5y", label: "5 years", quarters: 20 },
  { value: "10y", label: "10 years", quarters: 40 },
  { value: "full", label: "Full history", quarters: null },
];
export type Horizon = "annual" | "quarterly";
export type ComponentMode = "index" | "quarterly" | "annual";
type Row = { period: string; value: number | null };
type Meta = { releaseKey: string; sourceUrl: string | null };

export function addQuarters(period: string, n: number): string {
  const [y, m] = period.split("-").map(Number);
  const idx = y * 12 + (m - 1) + n * 3;
  return `${String(Math.floor(idx / 12)).padStart(4, "0")}-${String((idx % 12) + 1).padStart(2, "0")}`;
}

/** Every quarter from the first to the last period, so a missing quarter keeps its place and a line breaks there. */
export function quarterAxis(periods: string[]): string[] {
  const sorted = [...new Set(periods)].sort();
  if (sorted.length < 2 || !sorted.every((p) => /^\d{4}-(03|06|09|12)$/.test(p))) return sorted;
  const out: string[] = [];
  for (let p = sorted[0]; p <= sorted[sorted.length - 1]; p = addQuarters(p, 1)) out.push(p);
  return out;
}

/** The last N quarters up to and including the latest point; `full` keeps everything. */
export function rangeFilter<T extends { period: string }>(points: T[], range: CpiRange): T[] {
  const quarters = CPI_RANGES.find((r) => r.value === range)?.quarters ?? null;
  if (quarters === null || points.length === 0) return points;
  const last = points.reduce((a, p) => (p.period > a ? p.period : a), points[0].period);
  const first = addQuarters(last, -(quarters - 1));
  return points.filter((p) => p.period >= first);
}

const pct = (v: number, decimals = 1) => `${formatNumber(v, { decimals })}%`;
const quarterLabel = (p: string) => `Quarter ended ${monthLabel(p)}`;
const yearTick = (p: string) => (p.endsWith("-03") ? p.slice(0, 4) : "");
const zeroLine = (theme: ChartTheme) => ({
  silent: true, symbol: "none", label: { show: false }, lineStyle: { color: theme.muted, width: 1 }, data: [{ yAxis: 0 }],
});

function axes(periods: string[], theme: ChartTheme, yName: string, yExtra: object = {}) {
  return {
    xAxis: {
      type: "category", data: periods, boundaryGap: true,
      axisLabel: { interval: 0, hideOverlap: true, color: theme.muted, formatter: yearTick },
      axisTick: { interval: (_: number, v: string) => v.endsWith("-03") },
      axisLine: { lineStyle: { color: theme.muted } },
    },
    yAxis: {
      type: "value", name: yName, nameLocation: "end", nameTextStyle: { color: theme.muted, align: "left" },
      axisLabel: { color: theme.muted, formatter: (v: number) => pct(v, 0) },
      splitLine: { lineStyle: { color: theme.grid } }, ...yExtra,
    },
  };
}

function rateTooltip(name: string, byPeriod: Map<string, number | null>) {
  return {
    trigger: "axis" as const,
    formatter: (params: { axisValue: string }[] | { axisValue: string }) => {
      const p = String((Array.isArray(params) ? params[0] : params).axisValue);
      const v = byPeriod.get(p);
      const shown = v === null || v === undefined ? "Not available" : pct(v);
      return `${quarterLabel(p)}<br/>${escapeHtml(name)}: <b>${shown}</b>`;
    },
  };
}

const rates = (points: CpiPoint[], key: "annual_pct" | "quarterly_pct"): Row[] =>
  points.map((p) => ({ period: p.period, value: p[key] ?? null }));

function lineRates(name: string, data: Row[], yName: string, theme: ChartTheme, band = false): EChartsCoreOption {
  const periods = quarterAxis(data.map((r) => r.period));
  const byPeriod = new Map(data.map((r) => [r.period, r.value]));
  const latest = [...data].reverse().find((r) => r.value !== null);
  const color = theme.series[0];
  return {
    aria: { enabled: true }, animation: false, textStyle: { color: theme.text },
    grid: { left: 56, right: 56, top: 32, bottom: 28 },
    tooltip: rateTooltip(name, byPeriod),
    ...axes(periods, theme, yName),
    series: [{
      name, type: "line", showSymbol: false, connectNulls: false,
      lineStyle: { width: 2, color }, itemStyle: { color },
      data: periods.map((p) => byPeriod.get(p) ?? null),
      markLine: zeroLine(theme),
      ...(latest ? { markPoint: {
        symbol: "circle", symbolSize: 9, itemStyle: { color },
        label: { show: true, position: "top", color: theme.text, formatter: () => pct(latest.value as number) },
        data: [{ coord: [latest.period, latest.value] }],
      } } : {}),
      ...(band ? { markArea: {
        silent: true, itemStyle: { color: theme.grid, opacity: 0.4 },
        label: { show: true, position: "insideTopRight", color: theme.muted, formatter: "1% to 3% target band (reference)" },
        data: [[{ yAxis: 1 }, { yAxis: 3 }]],
      } } : {}),
    }],
  };
}

function barRates(name: string, data: Row[], yName: string, theme: ChartTheme): EChartsCoreOption {
  const periods = quarterAxis(data.map((r) => r.period));
  const byPeriod = new Map(data.map((r) => [r.period, r.value]));
  return {
    aria: { enabled: true }, animation: false, textStyle: { color: theme.text },
    grid: { left: 56, right: 24, top: 32, bottom: 28 },
    tooltip: rateTooltip(name, byPeriod),
    ...axes(periods, theme, yName),
    series: [{
      name, type: "bar", barMaxWidth: 14, markLine: zeroLine(theme),
      data: periods.map((p) => {
        const v = byPeriod.get(p);
        return v === null || v === undefined ? null : { value: v, itemStyle: { color: v < 0 ? theme.negative : theme.positive } };
      }),
    }],
  };
}

export const annualInflationOption = (points: CpiPoint[], theme: ChartTheme, opts: { band?: boolean } = {}) =>
  lineRates("Annual CPI inflation", rates(points, "annual_pct"), "Annual change (%)", theme, opts.band);

export const quarterlyInflationOption = (points: CpiPoint[], theme: ChartTheme) =>
  barRates("Quarterly CPI inflation", rates(points, "quarterly_pct"), "Quarterly change (%)", theme);

export function tradablesOption(tradables: CpiPoint[], non: CpiPoint[], horizon: Horizon, theme: ChartTheme): EChartsCoreOption {
  const key = horizon === "annual" ? "annual_pct" : "quarterly_pct";
  const sets = [["Tradables", rates(tradables, key)], ["Non-tradables", rates(non, key)]] as const;
  const periods = quarterAxis(sets.flatMap(([, r]) => r.map((x) => x.period)));
  const maps = sets.map(([, r]) => new Map(r.map((x) => [x.period, x.value])));
  return {
    aria: { enabled: true }, animation: false, textStyle: { color: theme.text },
    grid: { left: 56, right: 112, top: 32, bottom: 28 },
    tooltip: {
      trigger: "axis",
      formatter: (params: { axisValue: string }[]) => {
        const p = String(params[0].axisValue);
        const lines = sets.map(([n], i) => {
          const v = maps[i].get(p);
          return `${n}: <b>${v === null || v === undefined ? "Not available" : pct(v)}</b>`;
        });
        return `${quarterLabel(p)}<br/>${lines.join("<br/>")}`;
      },
    },
    ...axes(periods, theme, horizon === "annual" ? "Annual change (%)" : "Quarterly change (%)"),
    series: sets.map(([name], i) => {
      const color = theme.series[i];
      return {
        name, type: "line", showSymbol: false, connectNulls: false,
        lineStyle: { width: 2, color }, itemStyle: { color },
        endLabel: { show: true, formatter: "{a}", color: theme.text },
        data: periods.map((p) => maps[i].get(p) ?? null),
        ...(i === 0 ? { markLine: zeroLine(theme) } : {}),
      };
    }),
  };
}

export function contributionOption(block: CpiContributionBlock, theme: ChartTheme): EChartsCoreOption {
  const items = [...block.items].sort((a, b) => b.points - a.points);
  const signed = (v: number) => formatNumber(v, { signed: true, decimals: 2 });
  const floor = Math.floor(Math.min(0, ...items.map((i) => i.points)) * 12) / 10;
  return {
    aria: { enabled: true }, animation: false, textStyle: { color: theme.text },
    grid: { left: 4, right: 64, top: 28, bottom: 8, containLabel: true },
    tooltip: {
      trigger: "item",
      formatter: (p: { name: string; value: number }) => `${escapeHtml(p.name)}: <b>${signed(p.value)}</b> percentage points`,
    },
    xAxis: {
      type: "value", name: "Percentage points", nameLocation: "end", nameTextStyle: { color: theme.muted, align: "left" },
      min: floor, axisLabel: { color: theme.muted, hideOverlap: true, formatter: (v: number) => formatNumber(v, { decimals: 1 }) },
      splitLine: { lineStyle: { color: theme.grid } },
    },
    yAxis: { type: "category", inverse: true, data: items.map((i) => i.group), axisLabel: { color: theme.text, width: 120, overflow: "break" } },
    series: [{
      type: "bar", barMaxWidth: 18,
      label: { show: true, position: "right", color: theme.text, formatter: (p: { value: number }) => signed(p.value) },
      markLine: { silent: true, symbol: "none", label: { show: false }, lineStyle: { color: theme.muted }, data: [{ xAxis: 0 }] },
      data: items.map((i) => ({ name: i.group, value: i.points, itemStyle: { color: i.points < 0 ? theme.negative : theme.series[0] } })),
    }],
  };
}

/** Padded axis bounds for an index level series (never below zero), or null when there is nothing to draw. */
export function indexAxis(points: CpiPoint[]): { min: number; max: number } | null {
  return points.length ? zoomedRange(points.map((p) => ({ period: p.period, value: p.index, status: "final" }))) : null;
}

export function componentOption(series: CpiSeries, mode: ComponentMode, range: CpiRange, theme: ChartTheme): EChartsCoreOption {
  const points = rangeFilter(series.points, range);
  if (mode === "annual") return lineRates(series.name, rates(points, "annual_pct"), "Annual change (%)", theme);
  if (mode === "quarterly") return barRates(series.name, rates(points, "quarterly_pct"), "Quarterly change (%)", theme);
  const periods = quarterAxis(points.map((p) => p.period));
  const byPeriod = new Map(points.map((p) => [p.period, p.index]));
  return {
    aria: { enabled: true }, animation: false, textStyle: { color: theme.text },
    grid: { left: 56, right: 56, top: 32, bottom: 28 },
    tooltip: {
      trigger: "axis",
      formatter: (params: { axisValue: string }[]) => {
        const p = String(params[0].axisValue);
        const v = byPeriod.get(p);
        const shown = v === undefined ? "Not available" : formatNumber(v);
        return `${quarterLabel(p)}<br/>${escapeHtml(series.name)}: <b>${shown}</b> (June 2017 = 1000)`;
      },
    },
    ...axes(periods, theme, "Index (June 2017 = 1000)", {
      ...(indexAxis(points) ?? {}), axisLabel: { color: theme.muted, formatter: (v: number) => formatNumber(v) },
    }),
    series: [{
      name: series.name, type: "line", showSymbol: false, connectNulls: false,
      lineStyle: { width: 2, color: theme.series[0] }, itemStyle: { color: theme.series[0] },
      data: periods.map((p) => byPeriod.get(p) ?? null),
    }],
  };
}

export function historyCsvRows(series: CpiSeries, points: CpiPoint[], meta: Meta) {
  return points.map((p) => ({
    period: p.period, index: p.index, quarterly_pct: p.quarterly_pct, annual_pct: p.annual_pct,
    series_key: series.key, series_name: series.name, unit: series.unit, adjustment: series.adjustment,
    source_reference: series.source_reference, base: "June 2017 quarter (=1000)",
    release_key: meta.releaseKey, source_url: meta.sourceUrl ?? "",
  }));
}

export function contributionCsvRows(block: CpiContributionBlock, meta: Meta) {
  return block.items.map((i) => ({
    horizon: block.horizon, rank: i.rank, group: i.group, group_slug: i.slug, contribution_percentage_points: i.points,
    unit: block.unit, reference_period: block.reference_period, sum_percentage_points: block.sum_points,
    headline_change_percent: block.headline_pct, gap_percentage_points: block.gap_points,
    release_key: meta.releaseKey, source_url: meta.sourceUrl ?? "",
  }));
}
