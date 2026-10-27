import type { Kpi, Overview, ReleaseSummary } from "@/api/types";
import { TOPICS } from "@/stories/topics";
import type { StoryCategory } from "@/stories/types";
import { formatNumber } from "./format";

/**
 * The economic pulse: one headline indicator per topic, from the verified Stats NZ data the overview already serves.
 * Sentences are built from the published value and comparison only. They say what changed, never why.
 */

export type Freshness = { state: "current" | "stale"; label: string; detail: string };

export type PulseItem = {
  key: StoryCategory;
  title: string;
  kpi: Kpi;
  value: string;
  unitNote: string;
  sentence: string;
  freshness: Freshness;
  next: ReleaseSummary | null;
  dashboard: { to: string; label: string };
};

const DAY_MS = 86_400_000;

/** Headline series per topic, the release series it comes from, and how long until a newer release is normally out. */
const HEADLINES: { key: StoryCategory; series: string; slug: string; maxAgeDays: number }[] = [
  { key: "inflation", series: "cpi.index.nsa.all_groups", slug: "consumers-price-index", maxAgeDays: 105 },
  { key: "spending", series: "ect.m.sa.retail.value", slug: "electronic-card-transactions", maxAgeDays: 45 },
  { key: "migration", series: "mig.ry.net", slug: "international-migration", maxAgeDays: 45 },
];

const pct = (v: number) => `${formatNumber(Math.abs(v), { decimals: 1 })}%`;
const lowerFirst = (s: string) => s.charAt(0).toLowerCase() + s.slice(1);
const since = (label: string) => label.replace(/^vs\s+/, "").replace(/\s*\(a year earlier\)$/, "");

function inflation(k: Kpi): [string, string, string] {
  const m = k.metric;
  const prev = m.change_year_ago?.previous;
  const trend = prev === undefined || prev === null ? "" : `, ${m.value >= prev ? "up" : "down"} from ${formatNumber(prev, { decimals: 1 })}% a year before`;
  const sentence = `Consumer prices were ${pct(m.value)} ${m.value >= 0 ? "higher" : "lower"} than a year earlier in the ${lowerFirst(m.period_label)}${trend}.`;
  return [`${formatNumber(m.value, { decimals: 1 })}%`, "annual change, all groups", sentence];
}

function spending(k: Kpi): [string, string, string] {
  const m = k.metric;
  const c = m.change_prior ?? m.change_year_ago;
  const amount = `$${formatNumber(m.value)} million`;
  const diff = c && c.percent !== null ? `, ${pct(c.percent)} ${c.percent >= 0 ? "more" : "less"} than in ${since(c.label)}` : "";
  return [`$${formatNumber(m.value)}m`, "retail, seasonally adjusted, a month", `Retail card spending was ${amount} in ${m.period_label} (seasonally adjusted)${diff}.`];
}

function migration(k: Kpi): [string, string, string] {
  const m = k.metric;
  const n = formatNumber(Math.abs(m.value));
  const head = m.value >= 0 ? `Net migration added ${n} people` : `Net migration reduced the population by ${n} people`;
  const prev = m.change_year_ago?.previous;
  let trend = "";
  if (prev !== undefined && prev !== null) {
    const flipped = Math.sign(prev) !== Math.sign(m.value);
    const amount = flipped ? `${prev >= 0 ? "a gain" : "a loss"} of ${formatNumber(Math.abs(prev))}` : formatNumber(Math.abs(prev));
    trend = `, ${m.value >= prev ? "up" : "down"} from ${amount} a year earlier`;
  }
  return [formatNumber(m.value, { signed: true }), "people, net, year ended", `${head} in the ${lowerFirst(m.period_label)}${trend}.`];
}

const WRITERS: Record<StoryCategory, (k: Kpi) => [string, string, string]> = { inflation, spending, migration };

export function freshness(k: Kpi, now: Date, maxAgeDays = HEADLINES.find((h) => h.series === k.metric.series_key)?.maxAgeDays ?? 45): Freshness {
  const days = Math.floor((now.getTime() - Date.parse(k.published_at)) / DAY_MS);
  if (days <= maxAgeDays) return { state: "current", label: "Latest release", detail: `Published ${days} days ago.` };
  return {
    state: "stale",
    label: "May be out of date",
    detail: `Published ${days} days ago. A newer release is usually out by now; this site has not verified one yet.`,
  };
}

export function buildPulse(overview: Overview, now: Date): PulseItem[] {
  return HEADLINES.flatMap((h) => {
    const kpi = overview.kpis.find((k) => k.metric.series_key === h.series);
    if (!kpi) return [];
    const [value, unitNote, sentence] = WRITERS[h.key](kpi);
    const next = overview.upcoming.find((r) => r.series_slug === h.slug && Date.parse(r.published_at) > now.getTime()) ?? null;
    return [{
      key: h.key, title: TOPICS[h.key].title, kpi, value, unitNote, sentence,
      freshness: freshness(kpi, now, h.maxAgeDays), next, dashboard: TOPICS[h.key].dashboard,
    }];
  });
}
