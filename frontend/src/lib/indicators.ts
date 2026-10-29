import type { Kpi } from "@/api/types";
import { TOPICS } from "@/stories/topics";
import type { StoryCategory } from "@/stories/types";

export type IndicatorGroup = {
  key: StoryCategory | "growth" | "labour" | "other"; title: string; dashboard: { to: string; label: string } | null;
  tone: string | null; kpis: Kpi[];
};

const PREFIX: [StoryCategory, string][] = [["inflation", "cpi."], ["spending", "ect."], ["migration", "mig."]];
const GROUPS: { key: IndicatorGroup["key"]; prefixes: string[]; title: string; dashboard: IndicatorGroup["dashboard"]; tone: string | null }[] = [
  ...PREFIX.map(([key, prefix]) => ({ key, prefixes: [prefix], title: TOPICS[key].title, dashboard: TOPICS[key].dashboard, tone: TOPICS[key].tone })),
  // Official indicators without stories (Phase 4C): grouped with their dashboards, without a story topic colour.
  { key: "growth", prefixes: ["gdp."], title: "Economic growth", dashboard: { to: "/gdp", label: "Explore GDP" }, tone: null },
  { key: "labour", prefixes: ["hlfs.", "lci."], title: "Labour market", dashboard: { to: "/labour-market", label: "Explore the labour market" }, tone: null },
];
const inGroup = (k: Kpi, g: (typeof GROUPS)[number]) => g.prefixes.some((p) => k.metric.series_key.startsWith(p));

/** Every indicator, grouped by topic in reading order; the backend's order is kept within a group. Nothing is dropped. */
export function groupIndicators(kpis: Kpi[]): IndicatorGroup[] {
  const known = GROUPS.map((g) => ({ key: g.key, title: g.title, dashboard: g.dashboard, tone: g.tone, kpis: kpis.filter((k) => inGroup(k, g)) }));
  const other = kpis.filter((k) => !GROUPS.some((g) => inGroup(k, g)));
  return [...known, { key: "other" as const, title: "Other indicators", dashboard: null, tone: null, kpis: other }].filter((g) => g.kpis.length > 0);
}
