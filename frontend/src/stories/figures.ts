import type { EChartsCoreOption } from "echarts/core";
import {
  annualInflationOption, contributionCsvRows, contributionOption, historyCsvRows, rangeFilter, tradablesOption,
  type CpiRange, type Horizon,
} from "@/charts/cpi";
import type { ChartTheme } from "@/charts/theme";
import { monthLabel } from "@/lib/format";
import { rate } from "./text";
import type { Story } from "./types";

export type FigureView = {
  title: string;
  question: string;
  unit: string;
  caveat: string;
  option: EChartsCoreOption;
  ariaLabel: string;
  csvFilename: string;
  csvRows: Record<string, string | number | null>[];
  height: number;
};

export type Variants = { label: string; options: { value: string; label: string }[]; initial: string };

const RANGE: Variants = { label: "History range", options: [{ value: "10y", label: "10 years" }, { value: "full", label: "Full history" }], initial: "10y" };

export function variantsOf(story: Story): Variants | null {
  switch (story.figure.kind) {
    case "cpi-annual":
      return RANGE;
    case "cpi-contributions":
      return { label: "Contribution horizon", options: [{ value: "quarterly", label: "Quarterly" }, { value: "annual", label: "Annual" }], initial: "quarterly" };
    case "cpi-tradables":
      return { label: "Rate", options: [{ value: "annual", label: "Annual" }, { value: "quarterly", label: "Quarterly" }], initial: "annual" };
    default:
      return null;
  }
}

type SeriesOpt = { series: Record<string, unknown>[] };

/** Adds a labelled point to the first series' annotations; the existing latest-value label is kept. */
export function annotate(option: EChartsCoreOption, coord: [string, number], text: string, color: string): EChartsCoreOption {
  const series = [...(option as SeriesOpt).series];
  const first = series[0];
  const markPoint: { data?: unknown[] } = (first.markPoint as { data?: unknown[] } | undefined) ?? { symbol: "circle", symbolSize: 7 } as { data?: unknown[] };
  series[0] = {
    ...first,
    markPoint: {
      ...markPoint,
      data: [
        ...(markPoint.data ?? []),
        { coord, symbolSize: 7, itemStyle: { color }, label: { show: true, position: "top", color, formatter: text } },
      ],
    },
  };
  return { ...option, series };
}

export function figureView(story: Story, variant: string, theme: ChartTheme): FigureView {
  const f = story.figure;
  const meta = { releaseKey: story.provenance.releaseKey, sourceUrl: story.provenance.pageUrl };
  const quarter = story.referenceLabel;
  switch (f.kind) {
    case "cpi-annual": {
      const points = rangeFilter(f.series.points, variant as CpiRange);
      const rates = points.filter((p) => p.annual_pct != null);
      const peak = rates.reduce((m, p) => ((p.annual_pct as number) > (m.annual_pct as number) ? p : m), rates[0]);
      let option = annualInflationOption(points, theme, { band: true });
      if (peak && peak.period !== points.at(-1)?.period) {
        option = annotate(option, [peak.period, peak.annual_pct as number], `Peak ${rate(peak.annual_pct as number)} (${monthLabel(peak.period)})`, theme.muted);
      }
      return {
        title: "Annual CPI inflation", question: `${quarter}: how does ${story.stat.value} compare with recent history?`,
        unit: "percent change from the same quarter a year earlier",
        caveat: "Shaded: 1% to 3% reference band, not a forecast. Missing quarters are left as gaps.",
        option, ariaLabel: `Annual CPI inflation, ${variant === "full" ? "full history" : "last ten years"}`, height: 340,
        csvFilename: "story-cpi-annual-inflation.csv", csvRows: historyCsvRows(f.series, points, meta),
      };
    }
    case "cpi-contributions": {
      const horizon = variant === "annual" ? "annual" : "quarterly";
      const block = f.blocks.find((b) => b.horizon === horizon);
      if (!block?.available) throw new Error(`${horizon} contributions unavailable`);
      return {
        title: `Contribution to ${horizon} CPI change, by group`,
        question: `${quarter}: which groups added to or subtracted from the ${horizon} change${block.headline_pct == null ? "" : ` of ${rate(block.headline_pct)}`}?`,
        unit: "percentage points", caveat: block.note,
        option: contributionOption(block, theme), ariaLabel: `Contributions to the ${horizon} CPI change, by group`, height: 400,
        csvFilename: `story-cpi-contributions-${horizon}.csv`, csvRows: contributionCsvRows(block, meta),
      };
    }
    case "cpi-tradables": {
      const horizon = (variant === "quarterly" ? "quarterly" : "annual") as Horizon;
      const t = rangeFilter(f.tradables.points, "10y");
      const n = rangeFilter(f.nonTradables.points, "10y");
      return {
        title: `Tradables and non-tradables inflation · ${horizon}`,
        question: `${quarter}: which is rising faster, prices set abroad or at home?`,
        unit: horizon === "annual" ? "percent change from the same quarter a year earlier" : "percent change from the previous quarter",
        caveat: "Both series are on one percentage axis, so the gap between them is in percentage points. Non-tradables is not core inflation.",
        option: tradablesOption(t, n, horizon, theme), ariaLabel: `Tradables and non-tradables ${horizon} inflation, last ten years`, height: 340,
        csvFilename: `story-cpi-tradables-${horizon}.csv`,
        csvRows: [...historyCsvRows(f.tradables, t, meta), ...historyCsvRows(f.nonTradables, n, meta)],
      };
    }
    default:
      throw new Error(`No figure for ${f.kind}`);
  }
}
