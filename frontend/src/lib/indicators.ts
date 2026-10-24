import type { Kpi } from "@/api/types";
import { TOPICS } from "@/stories/topics";
import type { StoryCategory } from "@/stories/types";

export type IndicatorGroup = { key: StoryCategory | "other"; title: string; dashboard: { to: string; label: string } | null; kpis: Kpi[] };

const PREFIX: [StoryCategory, string][] = [["inflation", "cpi."], ["spending", "ect."], ["migration", "mig."]];
const GROUPS = PREFIX.map(([key, prefix]) => ({ key, prefix, title: TOPICS[key].title, dashboard: TOPICS[key].dashboard }));

/** Every indicator, grouped by topic in reading order; the backend's order is kept within a group. Nothing is dropped. */
export function groupIndicators(kpis: Kpi[]): IndicatorGroup[] {
  const known = GROUPS.map((g) => ({ key: g.key, title: g.title, dashboard: g.dashboard, kpis: kpis.filter((k) => k.metric.series_key.startsWith(g.prefix)) }));
  const other = kpis.filter((k) => !GROUPS.some((g) => k.metric.series_key.startsWith(g.prefix)));
  return [...known, { key: "other" as const, title: "Other indicators", dashboard: null, kpis: other }].filter((g) => g.kpis.length > 0);
}
