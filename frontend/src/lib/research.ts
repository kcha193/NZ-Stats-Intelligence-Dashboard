import type { ForecastGroup, Kpi, ResearchItem } from "@/api/types";
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
