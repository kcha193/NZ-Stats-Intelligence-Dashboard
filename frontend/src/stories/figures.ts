import type { EChartsCoreOption } from "echarts/core";
import {
  annualInflationOption, contributionCsvRows, contributionOption, historyCsvRows, rangeFilter, tradablesOption,
  type CpiRange, type Horizon,
} from "@/charts/cpi";
import { ectChangeOption, ectHistoryOption, ectIndustryOption } from "@/charts/ect";
import { lineOption, sliceYears, type ChartPoint } from "@/charts/options";
import type { ChartTheme } from "@/charts/theme";
import type { CpiContributionBlock, SeriesData } from "@/api/types";
import { formatNumber, monthLabel } from "@/lib/format";
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
    case "cpi-contributions": {
      const options = contributionBlocks(story.figure.blocks).map((b) => ({ value: b.horizon, label: b.horizon === "annual" ? "Annual" : "Quarterly" }));
      return options.length ? { label: "Contribution horizon", options, initial: options[0].value } : null;
    }
    case "cpi-tradables":
      return { label: "Rate", options: [{ value: "annual", label: "Annual" }, { value: "quarterly", label: "Quarterly" }], initial: "annual" };
    case "ect-retail":
      return { label: "Measure", options: [{ value: "change", label: "Monthly change" }, { value: "level", label: "Spending level" }], initial: "change" };
    case "mig-net":
    case "mig-flows":
    case "mig-citizenship":
      return RANGE;
    default:
      return null;
  }
}

/** The horizons a release can chart, quarterly first. The two are published independently, so either may be missing. */
function contributionBlocks(blocks: CpiContributionBlock[]): CpiContributionBlock[] {
  return (["quarterly", "annual"] as const).flatMap((h) => blocks.filter((b) => b.horizon === h && b.available && b.items.length > 0).slice(0, 1));
}

type SeriesOpt = { series: Record<string, unknown>[] };

/** Adds a labelled point to the first series' annotations; the existing latest-value label is kept. */
export function annotate(
  option: EChartsCoreOption, coord: [string, number], text: string, color: string, position: "top" | "left" = "top",
): EChartsCoreOption {
  const series = [...(option as SeriesOpt).series];
  const first = series[0];
  const markPoint: { data?: unknown[] } = (first.markPoint as { data?: unknown[] } | undefined) ?? { symbol: "circle", symbolSize: 7 } as { data?: unknown[] };
  series[0] = {
    ...first,
    markPoint: {
      ...markPoint,
      data: [
        ...(markPoint.data ?? []),
        { coord, symbolSize: 7, itemStyle: { color }, label: { show: true, position, color, formatter: text } },
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
      const blocks = contributionBlocks(f.blocks);
      // A variant the release cannot chart (a stale selection, say) falls back to the first horizon it can.
      const block = blocks.find((b) => b.horizon === variant) ?? blocks[0];
      if (!block) {
        return {
          title: "Contribution to CPI change, by group", question: `${quarter}: which groups added to or subtracted from the change?`,
          unit: "percentage points", caveat: "Contributions by group are not available for this release.",
          option: {}, ariaLabel: "Contributions to the CPI change, by group: not available", height: 120,
          csvFilename: "story-cpi-contributions.csv", csvRows: [],
        };
      }
      const horizon = block.horizon;
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
    case "ect-retail": {
      const meta = ectMeta(story);
      if (variant === "level") {
        const points = sliceYears(toPoints(f.level), 3);
        return {
          title: "Retail card spending · seasonally adjusted", question: `${story.referenceLabel}: where does spending sit against the last three years?`,
          unit: "NZD million, seasonally adjusted",
          caveat: "The vertical axis does not start at zero, so small movements look larger. Values are nominal and include price changes.",
          option: ectHistoryOption({ name: "Retail, seasonally adjusted", points, frequency: "monthly" }, theme, "zoomed"),
          ariaLabel: "Retail card spending level, seasonally adjusted, last three years", height: 340,
          csvFilename: "story-ect-retail-level.csv", csvRows: seriesCsv(f.level, points, meta),
        };
      }
      const points = toPoints(f.change).slice(-24);
      return {
        title: "Retail card spending · monthly change", question: `${story.referenceLabel}: how does ${story.stat.value} compare with the last two years?`,
        unit: "percent change from the previous month, seasonally adjusted",
        caveat: "Monthly changes as published by Stats NZ (one decimal place). Seasonally adjusted values are revised as new months arrive.",
        option: ectChangeOption({ name: "Retail, seasonally adjusted", points }, theme),
        ariaLabel: "Retail card spending, monthly percentage change, last 24 months", height: 320,
        csvFilename: "story-ect-retail-change.csv", csvRows: seriesCsv(f.change, points, meta),
      };
    }
    case "ect-industries": {
      const meta = ectMeta(story);
      return {
        title: "Card spending by industry · monthly change", question: `${story.referenceLabel}: which industries rose and which fell?`,
        unit: "percent change from the previous month, seasonally adjusted",
        caveat: "Changes compare adjacent months within the same release. Industries are adjusted separately and need not sum to the retail total.",
        option: ectIndustryOption(f.items.map((i) => ({ name: i.name, value: i.percent })), theme, "percent"),
        ariaLabel: "Card spending by industry, monthly percentage change", height: 360,
        csvFilename: "story-ect-industries.csv",
        csvRows: [...f.items].sort((a, b) => b.percent - a.percent).map((i) => ({
          industry: i.name, series_key: i.seriesKey, period: i.period, previous_period: i.previousPeriod, value_nzd_million: i.current,
          previous_value_nzd_million: i.previous, change_percent: i.percent, unit: "percent", adjustment: "seasonally_adjusted",
          release_key: meta.releaseKey, source_url: meta.sourceUrl,
        })),
      };
    }
    case "mig-net": {
      const points = migWindow(f.series, variant);
      const peak = points.reduce((m, p) => (p.value > m.value ? p : m), points[0]);
      let option = lineOption({ series: [{ name: "Year-ended net migration", points, color: theme.series[0] }], unit: "people", frequency: "rolling_annual" }, theme);
      if (peak && peak.period !== points.at(-1)?.period) {
        // Left of the point, clear of the provisional band's label at the recent end.
        option = annotate(option, [peak.period, peak.value], `Peak ${formatNumber(peak.value)} (${monthLabel(peak.period)})`, theme.muted, "left");
      }
      return {
        title: "Year-ended net migration", question: `${story.referenceLabel}: how does ${story.stat.value} compare with the last decade?`,
        unit: "people", caveat: f.series.caveat, option, height: 340,
        ariaLabel: `Year-ended net migration, ${variant === "full" ? "full history" : "last ten years"}`,
        csvFilename: "story-migration-net.csv", csvRows: migCsv(f.series, points),
      };
    }
    case "mig-flows": {
      const a = migWindow(f.arrivals, variant);
      const d = migWindow(f.departures, variant);
      return {
        title: "Migrant arrivals and departures · year ended", question: `${story.referenceLabel}: are more people arriving, or fewer leaving?`,
        unit: "people", caveat: f.arrivals.caveat, height: 340,
        option: lineOption({ series: [
          { name: "Migrant arrivals", points: a, color: theme.series[0] },
          { name: "Migrant departures", points: d, color: theme.series[1] },
        ], unit: "people", frequency: "rolling_annual" }, theme),
        ariaLabel: "Year-ended migrant arrivals and departures", csvFilename: "story-migration-flows.csv",
        csvRows: [...migCsv(f.arrivals, a), ...migCsv(f.departures, d)],
      };
    }
    case "mig-citizenship": {
      const o = migWindow(f.nonNz, variant);
      const z = migWindow(f.nz, variant);
      return {
        title: "Net migration by citizenship · year ended", question: `${story.referenceLabel}: who is arriving and who is leaving, on balance?`,
        unit: "people", caveat: `Above zero is a net gain, below zero a net loss. ${f.nz.caveat}`, height: 340,
        option: lineOption({ series: [
          { name: "Non-New Zealand citizens", points: o, color: theme.series[0] },
          { name: "New Zealand citizens", points: z, color: theme.series[1] },
        ], unit: "people", frequency: "rolling_annual" }, theme),
        ariaLabel: "Year-ended net migration of New Zealand and non-New Zealand citizens", csvFilename: "story-migration-citizenship.csv",
        csvRows: [...migCsv(f.nonNz, o), ...migCsv(f.nz, z)],
      };
    }
  }
}

const toPoints = (d: SeriesData): ChartPoint[] => d.points.map((p) => ({ period: p.period, value: p.value, status: p.status }));
const migWindow = (d: SeriesData, variant: string) => sliceYears(toPoints(d), variant === "full" ? null : 10);
const ectMeta = (story: Story) => ({ releaseKey: story.provenance.releaseKey, sourceUrl: story.provenance.pageUrl ?? "" });
const seriesCsv = (d: SeriesData, points: ChartPoint[], meta: { releaseKey: string; sourceUrl: string }) =>
  points.map((p) => ({
    period: p.period, value: p.value, unit: d.series.unit, frequency: d.series.frequency, adjustment: d.series.adjustment,
    status: p.status, series_key: d.series.key, release_key: meta.releaseKey, source_url: d.source_url ?? meta.sourceUrl,
  }));
const migCsv = (d: SeriesData, points: ChartPoint[]) =>
  points.map((p) => ({
    series: d.series.key, name: d.series.name, period: p.period, value: p.value, status: p.status, unit: d.series.unit,
    release_key: d.vintage.release_key, source_url: d.source_url ?? "",
  }));
