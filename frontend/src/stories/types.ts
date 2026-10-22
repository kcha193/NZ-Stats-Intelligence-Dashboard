import type { CpiContributionBlock, CpiSeries, Insight, SeriesData } from "@/api/types";

export type StoryCategory = "inflation" | "spending" | "migration";

export const CATEGORY_LABEL: Record<StoryCategory, string> = {
  inflation: "Inflation and prices",
  spending: "Consumer spending",
  migration: "International migration",
};

export type Sign = "positive" | "negative" | "neutral";

/** The one number a story is built around, already formatted at its published precision. */
export type KeyStat = { value: string; unit: string; label: string; sign: Sign };

export type Provenance = {
  releaseId: number | null;
  releaseKey: string;
  title: string;
  publishedAt: string;
  capturedAt: string;
  pageUrl: string | null;
  status: string;
  seriesSlug: string;
};

/** One published value a story relies on. */
export type EvidenceRow = {
  label: string; seriesKey: string; period: string; value: number; unit: string; status: string; releaseKey: string;
};

/** Inline SVG thumbnail data. `line` is a time series; `bars` is a signed or level ranking. */
export type Thumb =
  | { kind: "line"; values: (number | null)[]; zero: boolean }
  | { kind: "bars"; items: { label: string; value: number }[] };

export type Figure =
  | { kind: "cpi-annual"; series: CpiSeries }
  | { kind: "cpi-contributions"; blocks: CpiContributionBlock[] }
  | { kind: "cpi-tradables"; tradables: CpiSeries; nonTradables: CpiSeries }
  | { kind: "ect-retail"; change: SeriesData; level: SeriesData }
  | { kind: "ect-industries"; items: IndustryMove[]; period: string }
  | { kind: "mig-net"; series: SeriesData }
  | { kind: "mig-flows"; arrivals: SeriesData; departures: SeriesData }
  | { kind: "mig-citizenship"; nonNz: SeriesData; nz: SeriesData };

export type IndustryMove = {
  name: string; seriesKey: string; period: string; previousPeriod: string; current: number; previous: number; percent: number;
};

export type Story = {
  id: string;
  template: string;
  category: StoryCategory;
  /** Lower comes first among stories published at the same instant. */
  priority: number;
  headline: string;
  dek: string;
  stat: KeyStat;
  referencePeriod: string;
  referenceLabel: string;
  dataStatus: string;
  provenance: Provenance;
  dashboard: { to: string; label: string };
  explanation: string[];
  context: string[];
  caveats: string[];
  methodology: string[];
  evidence: EvidenceRow[];
  insights: Insight[];
  thumb: Thumb;
  figure: Figure;
};
