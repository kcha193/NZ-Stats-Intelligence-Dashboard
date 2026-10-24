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

/** How a graphic prints its numbers: rates in %, contributions and gaps in pp, migration in people. */
export type ValueFormat = "pct" | "pp" | "people";
/** How a graphic names a period: quarters and months by their month, year-ended totals as "YE Jul 2026". */
export type PeriodStyle = "quarter" | "month" | "year-ended";
export type ThumbPoint = { period: string; value: number | null; provisional?: boolean };

/**
 * The story's own small graphic: one message, one encoding, labelled directly.
 * - `line`: a level or rate over time, with the latest value and the peak in range labelled.
 * - `columns`: signed changes over time on a zero baseline (growth rates, never levels).
 * - `bars`: a signed ranking, diverging from zero (contributions, industry changes, net flows).
 * - `pair`: two measures of the same unit side by side, with their difference stated (a dumbbell for rates, bars for
 *   counts of people, which start at zero).
 */
export type Thumb =
  | { kind: "line"; name: string; points: ThumbPoint[]; zero: boolean; format: ValueFormat; period: PeriodStyle }
  | { kind: "columns"; name: string; points: ThumbPoint[]; format: ValueFormat; period: PeriodStyle }
  | { kind: "bars"; name: string; items: { label: string; value: number }[]; format: ValueFormat }
  | { kind: "pair"; name: string; items: [{ label: string; value: number }, { label: string; value: number }]; format: ValueFormat;
      gap: { label: string; value: string } };

/**
 * A headline measure in plain language, for "the economy at a glance". Every string is built from the story's own
 * published values by the builder; nothing is added at render time.
 */
export type Glance = {
  /** Short name of the measure: "Inflation". */
  metric: string;
  value: string;
  /** What the number measures, with its comparator: "annual change in consumer prices". */
  measure: string;
  /** Movement against the appropriate comparator, with that comparator named. */
  comparison: string;
  /** One sentence a reader with no statistics background can repeat accurately. */
  plain: string;
  direction: "up" | "down" | "flat";
};

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
  name: string; inText: string; seriesKey: string; period: string; previousPeriod: string; current: number; previous: number; percent: number;
  /** Publication status of the two points compared, as the source reports them. */
  status: string; previousStatus: string;
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
  /** Present only on the headline story of each category. */
  glance?: Glance;
};
