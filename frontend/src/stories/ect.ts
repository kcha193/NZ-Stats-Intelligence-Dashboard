import type { EctDashboard, SeriesData } from "@/api/types";
import { formatNumber } from "@/lib/format";
import { provenanceOf, releaseCaveats } from "./common";
import { addMonths, direction, lastAtLeast, lastAtMost, monthName, signedRate, signOf } from "./text";
import type { IndustryMove, Story } from "./types";

const DASHBOARD = { to: "/electronic-card-transactions", label: "Explore the card spending dashboard" };
const NOMINAL = "Values are nominal: they include price changes, so higher spending does not necessarily mean more goods or services were bought.";

/** Industry series in the release, with the name used mid-sentence. */
const INDUSTRIES: [key: string, name: string, inText: string][] = [
  ["consumables", "Consumables", "consumables"], ["durables", "Durables", "durables"],
  ["hospitality", "Hospitality", "hospitality"], ["apparel", "Apparel", "apparel"],
  ["motor_vehicles", "Motor vehicles excl. fuel", "motor vehicles excluding fuel"], ["fuel", "Fuel", "fuel"],
  ["services", "Services", "services"], ["non_retail", "Non-retail excl. services", "non-retail excluding services"],
];

const unsigned = (v: number) => `${formatNumber(Math.abs(v), { decimals: 1 })}%`;
const billions = (millions: number) => `$${formatNumber(millions / 1000, { decimals: 2 })} billion`;

export function buildEctStories(data: EctDashboard): Story[] {
  const series = new Map(data.series.map((s) => [s.series.key, s]));
  const a = data.analysis;
  const releaseKey = a.release.release_key;
  const base = {
    category: "spending" as const,
    provenance: provenanceOf(a),
    dashboard: DASHBOARD,
    methodology: [...a.methodology.definitions, ...a.methodology.notes],
    insights: [...a.executive_summary, ...a.context],
  };
  const stories: Story[] = [];

  // 1. Retail spending, published seasonally adjusted monthly change.
  const change = series.get("ect.m.sa.retail.change");
  const level = series.get("ect.m.sa.retail.value");
  const metric = a.headline_metrics.find((m) => m.series_key === "ect.m.sa.retail.value");
  const latest = change?.points.at(-1);
  if (change && level && metric && latest && level.points.at(-1)?.period === latest.period) {
    const period = latest.period;
    const dir = direction(latest.value, 0, 1);
    const pts = change.points.map((p) => ({ period: p.period, value: p.value }));
    const prior = dir === "down" ? lastAtMost(pts) : dir === "up" ? lastAtLeast(pts) : null;
    const diff = metric.change_prior;
    const levelText = diff
      ? Math.round(Math.abs(diff.absolute)) === 0
        ? `about the same as in ${monthName(diff.comparison_period)}`
        : `$${formatNumber(Math.abs(diff.absolute))} million ${diff.absolute < 0 ? "less" : "more"} than in ${monthName(diff.comparison_period)}`
      : null;
    const year = metric.change_year_ago;
    const rev = a.revisions;
    const at = (d: SeriesData, p: string) => d.points.find((x) => x.period === p);
    const levelRow = (label: string, p: string) => {
      const x = at(level, p);
      return x ? [{ label, seriesKey: level.series.key, period: p, value: x.value, unit: "NZD million", status: x.status, releaseKey }] : [];
    };
    stories.push({
      ...base, id: `spending-retail-${period}`, template: "spending-retail", priority: 0,
      referencePeriod: period, referenceLabel: monthName(period), dataStatus: latest.status,
      headline: dir === "flat"
        ? `Retail card spending was unchanged in ${monthName(period)}`
        : `Retail card spending ${dir === "up" ? "rose" : "fell"} ${unsigned(latest.value)} in ${monthName(period)}`,
      dek: `Seasonally adjusted retail spending on electronic cards was ${billions(metric.value)}${levelText ? `, ${levelText}` : ""}.`,
      stat: { value: signedRate(latest.value), unit: "monthly change, seasonally adjusted", label: `Retail card spending, ${monthName(period)}`, sign: signOf(latest.value, 1) },
      explanation: [
        a.executive_summary[0]?.text ?? "",
        "The monthly change is published by Stats NZ from seasonally adjusted values, which remove regular calendar patterns such as Christmas so that one month can be compared with the next.",
      ].filter(Boolean),
      context: [
        ...(prior ? [`The last monthly ${dir === "down" ? "fall" : "rise"} at least this large was in ${monthName(prior.period)} (${signedRate(prior.value)}).`] : []),
        ...(year?.percent != null ? [`Compared with ${monthName(year.comparison_period)}, retail spending was ${unsigned(year.percent)} ${year.percent < 0 ? "lower" : "higher"}.`] : []),
        ...(rev.available && rev.n_revised > 0 ? [`${rev.n_revised} of ${rev.n_common} overlapping retail months were revised in this release, compared with ${rev.against_title}.`] : []),
      ],
      caveats: [...releaseCaveats(a), NOMINAL, "Seasonally adjusted estimates are re-estimated each month and can be revised."],
      evidence: [
        { label: "Retail monthly change, seasonally adjusted", seriesKey: change.series.key, period, value: latest.value, unit: "percent", status: latest.status, releaseKey },
        ...levelRow("Retail spending, seasonally adjusted", period),
        ...(diff ? levelRow("Retail spending, previous month", diff.comparison_period) : []),
        ...(year ? levelRow("Retail spending, a year earlier", year.comparison_period) : []),
      ],
      thumb: { kind: "line", values: change.points.slice(-24).map((p) => p.value), zero: true },
      figure: { kind: "ect-retail", change, level },
    });
  }

  // 2. Industry movements: seasonally adjusted, adjacent months, one release.
  const moves: IndustryMove[] = INDUSTRIES.flatMap(([key, name, inText]) => {
    const s = series.get(`ect.m.sa.${key}.value`);
    const cur = s?.points.at(-1);
    const prev = cur && s?.points.find((p) => p.period === addMonths(cur.period, -1));
    if (!s || !cur || !prev || prev.value <= 0) return [];
    return [{ name, inText, seriesKey: s.series.key, period: cur.period, previousPeriod: prev.period, current: cur.value, previous: prev.value, percent: (cur.value / prev.value - 1) * 100 }];
  });
  const period = moves[0]?.period;
  if (moves.length >= 2 && moves.every((m) => m.period === period)) {
    const sorted = [...moves].sort((x, y) => y.percent - x.percent);
    const top = sorted[0];
    // Direction comes from the sign at the displayed precision, so a clause never names an industry that did not move that way.
    const risers = sorted.filter((m) => signOf(m.percent, 1) === "positive");
    const fallers = sorted.filter((m) => signOf(m.percent, 1) === "negative").reverse();
    const [up, down] = [risers.length, fallers.length];
    const month = monthName(period);
    const previous = monthName(top.previousPeriod);
    const name = (m: { inText: string; percent: number }) => `${m.inText} (${signedRate(m.percent)})`;
    const clause = (group: IndustryMove[], verb: "rise" | "fall", past: string) =>
      group.length >= 2 ? `${name(group[0])} and ${name(group[1])} ${past} most` : group.length === 1 ? `${name(group[0])} was the only industry to ${verb}` : null;
    const clauses = [clause(risers, "rise", "rose"), clause(fallers, "fall", "fell")].filter((c): c is string => c !== null).join("; ");
    const headline = up && down
      ? `Spending on ${risers[0].inText} rose ${unsigned(risers[0].percent)} in ${month}; ${fallers[0].inText} fell ${unsigned(fallers[0].percent)}`
      : up
        ? `Card spending rose or held in every industry in ${month}, led by ${risers[0].inText} (${signedRate(risers[0].percent)})`
        : down
          ? `Card spending fell or held in every industry in ${month}, led by ${fallers[0].inText} (${signedRate(fallers[0].percent)})`
          : `Card spending was unchanged in every industry in ${month}`;
    const lead = up ? risers[0] : down ? fallers[0] : top;
    stories.push({
      ...base, id: `spending-industries-${period}`, template: "spending-industries", priority: 1,
      referencePeriod: period, referenceLabel: month, dataStatus: "final",
      headline,
      dek: clauses
        ? `${clauses.replace(/^./, (c) => c.toUpperCase())}, compared with ${previous}.`
        : `Seasonally adjusted spending was unchanged in every industry compared with ${previous}, at one decimal place.`,
      stat: {
        value: signedRate(lead.percent), unit: `monthly change in ${lead.inText} spending, seasonally adjusted`,
        label: `${up ? "Largest rise" : down ? "Largest fall" : "Largest movement"} of ${moves.length} industries`, sign: signOf(lead.percent, 1),
      },
      explanation: [
        `Each bar compares an industry's seasonally adjusted card spending in ${month} with ${previous}, both taken from the same release. Bars right of zero rose; bars left of zero fell.`,
      ],
      context: [`${up} of ${moves.length} industries recorded higher seasonally adjusted spending than in ${previous}.`],
      caveats: [...releaseCaveats(a), NOMINAL, "Industry series are seasonally adjusted separately, so they need not add up to the retail total."],
      evidence: moves.flatMap((m) => [
        { label: `${m.name}, ${monthName(m.period)}`, seriesKey: m.seriesKey, period: m.period, value: m.current, unit: "NZD million", status: "final", releaseKey },
        { label: `${m.name}, ${monthName(m.previousPeriod)}`, seriesKey: m.seriesKey, period: m.previousPeriod, value: m.previous, unit: "NZD million", status: "final", releaseKey },
      ]),
      thumb: { kind: "bars", items: sorted.map((m) => ({ label: m.name, value: m.percent })) },
      figure: { kind: "ect-industries", items: moves, period },
    });
  }
  return stories;
}
