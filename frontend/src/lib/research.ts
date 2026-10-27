import type { EvaluatedForecast, ForecastGroup, ForecastSeries, Kpi, ResearchItem } from "@/api/types";
import type { FeedParams } from "@/api/hooks";
import type { Observation } from "@/charts/forecasts";

/** Shared helpers for the economic outlook pages. */

export const researchPath = (id: number) => `/economic-outlook/research/${id}`;

export const PAGE_SIZE = 10;
export type GroupBy = "date" | "institution" | "topic";
export type Sort = NonNullable<FeedParams["sort"]>;

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const monthOf = (day: string | null | undefined) => {
  const m = /^(\d{4})-(\d{2})/.exec(day ?? "");
  return m ? `${MONTHS[Number(m[2]) - 1]} ${m[1]}` : "Date not stated";
};
const topicLabel = (key: string) => key.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

/** Groups in the order the items arrive (the chosen sort), so grouping never reorders the feed's ranking. */
export function groupItems(items: ResearchItem[], by: GroupBy, topicLabels: Record<string, string> = {}): { label: string; items: ResearchItem[] }[] {
  const groups = new Map<string, ResearchItem[]>();
  for (const item of items) {
    const label = by === "date" ? monthOf(item.document.published_on)
      : by === "institution" ? item.institution.name
      : item.topics.length ? (topicLabels[item.topics[0]] ?? topicLabel(item.topics[0])) : "No topic";
    groups.set(label, [...(groups.get(label) ?? []), item]);
  }
  return [...groups].map(([label, list]) => ({ label, items: list }));
}

/**
 * The latest month a horizon key can end in, as YYYY-MM: exact for a quarter, month or year to; the December of a calendar
 * year; and for a split (fiscal) year "2026/27", no earlier than January of the second year. Null if not recognised.
 */
export function horizonEnd(key: string): string | null {
  const [kind, value = ""] = key.split(":");
  if (["quarter", "month", "year_to"].includes(kind) && /^\d{4}-\d{2}$/.test(value)) return value;
  if (kind === "calendar" && /^\d{4}$/.test(value)) return `${value}-12`;
  if (kind === "split" && /^\d{4}\/\d{2}$/.test(value)) return `${Number(value.slice(0, 4)) + 1}-01`;
  return null;
}

/** The official CPI measures the evaluation scores forecasts against (`MEASURES` in the backend's `research/outcomes.py`). */
export type CpiMeasure = "annual_change" | "annual_average_change" | "quarterly_change_nsa" | "quarterly_change_sa";

/**
 * Comparison basis (the history's identifier) to the official evaluation measure. The two vocabularies differ, so
 * nothing is inferred from the strings: a basis not listed has no official outcome. The history leaves "seasonally
 * adjusted" out of the basis (it is a stated word, not a qualifier), so a quarterly change without a qualifier maps to the
 * seasonally adjusted measure only as a candidate: `matchedOutcomeFor` still requires the evaluation to have matched one
 * of this series' own forecasts on it, so an unlabelled quarterly change is never given an official figure.
 */
const CPI_MEASURE_BY_BASIS: ReadonlyMap<string, CpiMeasure> = new Map<string, CpiMeasure>([
  ["annual_change", "annual_change"],
  ["annual_average_change", "annual_average_change"],
  ["quarterly_change:unadjusted", "quarterly_change_nsa"],
  ["quarterly_change", "quarterly_change_sa"],
]);

export function cpiMeasureFor(series: Pick<ForecastSeries, "indicator" | "basis">): CpiMeasure | null {
  return series.indicator === "cpi_inflation" ? (CPI_MEASURE_BY_BASIS.get(series.basis) ?? null) : null;
}

/**
 * The evaluation row that gives a central series its official outcome: matched, on the measure its basis maps to, for the
 * quarter its horizon ends, and for one of this series' own vintages. Null when any of these fails (a scenario is never
 * scored; an unsupported or ambiguous basis, a pending target or another institution's forecast gives no outcome).
 */
export function matchedOutcomeFor(series: ForecastSeries, evaluated: readonly EvaluatedForecast[]): EvaluatedForecast | null {
  const measure = cpiMeasureFor(series);
  const end = horizonEnd(series.horizon_key);
  if (series.kind !== "central" || measure === null || end === null) return null;
  const own = new Set(series.vintages.map((v) => v.summary_id));
  return evaluated.find((e) => e.status === "matched" && e.measure === measure && e.target_quarter === end && own.has(e.forecast.summary_id)) ?? null;
}

/**
 * The official reference applies only to the same statistic (annual CPI change, in percent) and only to a target that
 * ends after the latest observed quarter: an earlier target has its own outcome, which the latest quarter never stands in
 * for (the track record shows it).
 */
export function observationFor(group: ForecastGroup, cpi: Kpi | undefined): (Observation & { publishedAt: string; period: string }) | null {
  if (!cpi || group.indicator !== "cpi_inflation" || group.basis !== "annual_change" || group.unit !== "percent") return null;
  const end = horizonEnd(group.horizon_key);
  if (end === null || end <= cpi.metric.period) return null;
  const m = cpi.metric;
  return { value: m.value, label: "Latest Stats NZ", publishedAt: cpi.published_at, period: m.period_label };
}


/** Only an absolute https address without credentials becomes a link; anything else is shown as plain text. */
export function safeHttpsUrl(value: string | null | undefined): string | null {
  try {
    const u = new URL(value ?? "");
    return u.protocol === "https:" && !u.username && !u.password ? u.href : null;
  } catch {
    return null;
  }
}
