import type { CpiDashboard, CpiPoint, CpiSeries } from "@/api/types";
import { addQuarters } from "@/charts/cpi";
import { formatNumber } from "@/lib/format";
import { provenanceOf, releaseCaveats } from "./common";
import { direction, lastAtLeast, lastAtMost, ppShort, quarterName, rate, signOf } from "./text";
import type { EvidenceRow, Glance, Sign, Story } from "./types";

const DASHBOARD = { to: "/inflation", label: "Explore the inflation dashboard" };
/** The adapter stores every contribution with unknown status (the release does not label them), so none is called final. */
const CONTRIBUTION_STATUS = "unknown";
const BAND_CAVEAT = "The 1% to 3% band is drawn for reference only and is not a forecast.";

type Rate = { period: string; value: number };
const annualRates = (s: CpiSeries): Rate[] =>
  s.points.filter((p): p is CpiPoint & { annual_pct: number } => p.annual_pct != null).map((p) => ({ period: p.period, value: p.annual_pct }));
const at = (rates: Rate[], period: string) => rates.find((r) => r.period === period);

function yearAgoText(latest: number, yearAgo: Rate): string {
  const gap = Number(latest.toFixed(1)) - Number(yearAgo.value.toFixed(1));
  const where = direction(latest, yearAgo.value, 1);
  const tail = where === "flat" ? "the same rate as now" : `${formatNumber(Math.abs(gap), { decimals: 1 })} percentage points ${where === "up" ? "lower" : "higher"} than now`;
  return `A year earlier, in the ${quarterName(yearAgo.period)}, annual inflation was ${rate(yearAgo.value)}, ${tail}.`;
}

/** The persisted series key of a group's contribution, as the backend names it: `cpi.contrib.q.transport`. */
export const contributionKey = (horizon: "quarterly" | "annual", slug: string) => `cpi.contrib.${horizon === "annual" ? "a" : "q"}.${slug}`;

type Contribution = { slug: string; group: string; points: number };

/** Groups ordered by how strongly they drive the headline: those moving with it first, largest first. A headline that
 * rounds to zero has no direction, so size alone decides. */
function drivingOrder<T extends Contribution>(items: T[], dir: "up" | "down" | "flat"): T[] {
  return [...items].sort((x, y) => (dir === "down" ? x.points - y.points : dir === "up" ? y.points - x.points : Math.abs(y.points) - Math.abs(x.points)));
}

/** Annual change in words, from the sign of the displayed rate: "4.1% higher", "0.5% lower" or "unchanged". */
function yearOnYear(annual: number, quarter: string): string {
  const dir = direction(annual, 0, 1);
  return dir === "flat"
    ? `Consumer prices in the ${quarter} were unchanged from a year earlier`
    : `Consumer prices were ${rate(Math.abs(annual))} ${dir === "up" ? "higher" : "lower"} in the ${quarter} than a year earlier`;
}

/** What a price level did over a period, from the sign of the displayed rate: "rose 4.9%", "fell 1.1%" or "were unchanged". */
function moved(annual: number): string {
  const dir = direction(annual, 0, 1);
  return dir === "flat" ? "were unchanged" : `${dir === "up" ? "rose" : "fell"} ${rate(Math.abs(annual))}`;
}

/** The glance for annual inflation: the rate against last quarter's rate (in percentage points), and the price level
 * against a year earlier, which is what the annual rate itself measures. Never "prices fell" for a lower positive rate. */
function inflationGlance(latest: Rate, prior: Rate): Glance {
  const dir = direction(latest.value, prior.value, 1);
  const gap = Math.abs(Number(latest.value.toFixed(1)) - Number(prior.value.toFixed(1)));
  const since = `${rate(prior.value)} in the ${quarterName(prior.period)}`;
  const level = direction(latest.value, 0, 1);
  return {
    metric: "Inflation", value: rate(latest.value), measure: "annual change in consumer prices",
    comparison: dir === "flat"
      ? `Unchanged from ${since}`
      : `${dir === "up" ? "Up" : "Down"} ${formatNumber(gap, { decimals: 1 })} percentage points from ${since}`,
    plain: level === "flat"
      ? "Consumer prices were unchanged from a year earlier."
      : `Consumer prices were ${rate(Math.abs(latest.value))} ${level === "up" ? "higher" : "lower"} than a year earlier.`,
    direction: dir,
  };
}

export function buildCpiStories(data: CpiDashboard): Story[] {
  const nsa = (slug: string) => data.series.find((s) => s.slug === slug && s.adjustment === "none");
  const all = nsa("all_groups");
  if (!all) return [];
  const a = data.analysis;
  const period = data.reference_period;
  const base = {
    category: "inflation" as const,
    referencePeriod: period,
    referenceLabel: quarterName(period),
    dataStatus: "final",
    provenance: provenanceOf(a),
    dashboard: DASHBOARD,
    methodology: [...a.methodology.definitions, ...a.methodology.notes],
    insights: [...a.executive_summary, ...a.context],
  };
  const releaseKey = a.release.release_key;
  const evidence = (label: string, s: CpiSeries, r: Rate): EvidenceRow => ({
    label, seriesKey: s.key, period: r.period, value: r.value, unit: "percent (annual change, from index numbers)",
    status: "final", releaseKey,
  });
  const stories: Story[] = [];

  // 1. Annual inflation.
  const annual = annualRates(all);
  const latest = annual.at(-1);
  const prior = latest && at(annual, addQuarters(latest.period, -1));
  if (latest && latest.period === period && prior) {
    const yearAgo = at(annual, addQuarters(period, -4));
    const dir = direction(latest.value, prior.value, 1);
    const verb = { up: "rises to", down: "eases to", flat: "holds at" }[dir];
    const was = { up: "up from", down: "down from", flat: "the same as" }[dir];
    const high = latest.value >= prior.value ? lastAtLeast(annual) : lastAtMost(annual);
    const quarterly = all.points.at(-1)?.quarterly_pct;
    const tenYears = annual.filter((r) => r.period > addQuarters(period, -40));
    const peak = tenYears.reduce((m, r) => (r.value > m.value ? r : m), tenYears[0]);
    stories.push({
      ...base, id: `inflation-annual-${period}`, template: "inflation-annual", priority: 0,
      headline: `Annual inflation ${verb} ${rate(latest.value)}`,
      dek: `${yearOnYear(latest.value, quarterName(period))}, ${was} ${rate(prior.value)} in the ${quarterName(prior.period)}.`,
      stat: { value: rate(latest.value), unit: "annual change in the CPI", label: "All groups, not seasonally adjusted", sign: signOf(latest.value, 1) },
      explanation: [
        a.executive_summary[0]?.text ?? (quarterly == null ? "" : `Prices changed ${rate(quarterly)} within the quarter.`),
        "Annual inflation compares the price level in a quarter with the same quarter a year earlier, so seasonal patterns largely cancel out. The quarterly change compares adjacent quarters; the two are different measures and are not added together.",
      ].filter(Boolean),
      context: [
        ...(high ? [`Annual inflation was last this ${latest.value >= prior.value ? "high" : "low"} in the ${quarterName(high.period)} (${rate(high.value)}).`] : []),
        ...(yearAgo ? [yearAgoText(latest.value, yearAgo)] : []),
        ...(peak && peak.period !== latest.period ? [`The highest rate in the last ten years was ${rate(peak.value)}, in the ${quarterName(peak.period)}.`] : []),
      ],
      caveats: [...releaseCaveats(a), BAND_CAVEAT, "Official changes are calculated from the rounded published index numbers."],
      evidence: [
        evidence("Annual change, latest quarter", all, latest),
        evidence("Annual change, previous quarter", all, prior),
        ...(yearAgo ? [evidence("Annual change, a year earlier", all, yearAgo)] : []),
        ...(high ? [evidence(`Last ${latest.value >= prior.value ? "at or above" : "at or below"} the latest rate`, all, high)] : []),
      ],
      thumb: { kind: "line", name: "Annual CPI inflation", points: tenYears, zero: true, format: "pct", period: "quarter" },
      figure: { kind: "cpi-annual", series: all },
      glance: inflationGlance(latest, prior),
    });
  }

  // 2. Contributions to the quarterly change.
  const q = data.contributions.find((b) => b.horizon === "quarterly");
  if (q?.available && q.items.length && q.headline_pct != null) {
    const headline = q.headline_pct;
    // Direction is read from the headline as displayed; a driver moves with it and a countervailing group against it.
    const dir = direction(headline, 0, 1);
    const [top, second] = drivingOrder(q.items, dir);
    const largest = (d: typeof dir) => (d === "down" ? "largest downward contribution" : "largest contribution");
    const ofSign = (sign: Sign) => q.items.filter((i) => signOf(i.points, 2) === sign).sort((x, y) => Math.abs(y.points) - Math.abs(x.points));
    const yearBlock = data.contributions.find((b) => b.horizon === "annual");
    const yearHeadline = yearBlock?.headline_pct ?? null;
    const yearTop = yearBlock?.available && yearHeadline != null ? drivingOrder(yearBlock.items, direction(yearHeadline, 0, 1))[0] : undefined;
    const describe = (i: { group: string; points: number }) => `${i.group} (${ppShort(i.points)})`;
    let opposing: string;
    if (dir === "flat") {
      const [up, down] = [ofSign("positive")[0], ofSign("negative")[0]];
      opposing = `The headline change rounds to ${rate(headline)}, so no group is treated as driving prices up or down.${
        up && down ? ` Contributions pointed both ways: ${describe(up)} against ${describe(down)}.` : ""}`;
    } else {
      const against = ofSign(dir === "up" ? "negative" : "positive");
      opposing = against.length
        ? `${against.length === 1 ? "One group" : `${against.length} groups`} pulled the other way: ${against.map(describe).join(", ")}.`
        : `No group made a ${dir === "up" ? "negative" : "positive"} contribution this quarter.`;
    }
    stories.push({
      ...base, id: `inflation-drivers-${period}`, template: "inflation-drivers", priority: 1,
      headline: `${top.group} made the ${largest(dir)} to quarterly inflation of ${rate(headline)}`,
      dek: `${describe(top)}${second ? ` and ${describe(second)}` : ""} contributed most to the ${rate(headline)} change in consumer prices in the ${quarterName(period)}.`,
      stat: { value: ppShort(top.points), unit: "percentage points", label: `${top.group}, contribution to the quarterly change`, sign: signOf(top.points, 2) },
      explanation: [
        "A contribution is the part of the headline change that comes from one group: its own price change weighted by its share of household spending. It is measured in percentage points of the headline change.",
        q.note,
      ],
      context: [
        opposing,
        ...(yearTop && yearHeadline != null
          ? [`Over the year, ${describe(yearTop)} made the ${largest(direction(yearHeadline, 0, 1))} to annual inflation of ${rate(yearHeadline)}.`]
          : []),
      ],
      caveats: [...releaseCaveats(a), "Each bar is a contribution in percentage points, not the group's own price change."],
      evidence: [
        ...q.items.map((i) => ({
          label: `${i.group}, quarterly contribution`, seriesKey: contributionKey("quarterly", i.slug), period, value: i.points,
          unit: "percentage points", status: CONTRIBUTION_STATUS, releaseKey,
        })),
        ...(yearTop ? [{
          label: `${yearTop.group}, annual contribution`, seriesKey: contributionKey("annual", yearTop.slug), period: yearBlock?.reference_period ?? period,
          value: yearTop.points, unit: "percentage points", status: CONTRIBUTION_STATUS, releaseKey,
        }] : []),
      ],
      thumb: {
        kind: "bars", name: "Contribution to quarterly inflation, by group", format: "pp",
        items: [...q.items].sort((x, y) => y.points - x.points).map((i) => ({ label: i.group, value: i.points })),
      },
      figure: { kind: "cpi-contributions", blocks: data.contributions },
    });
  }

  // 3. Tradables versus non-tradables (annual).
  const trad = nsa("tradables");
  const non = nsa("non_tradables");
  if (trad && non) {
    const t = annualRates(trad);
    const n = annualRates(non);
    const tl = at(t, period);
    const nl = at(n, period);
    if (tl && nl) {
      const gap = Number(tl.value.toFixed(1)) - Number(nl.value.toFixed(1));
      const dir = direction(tl.value, nl.value, 1);
      const headline = dir === "up"
        ? `Tradables inflation (${rate(tl.value)}) runs ahead of non-tradables (${rate(nl.value)})`
        : dir === "down"
          ? `Non-tradables inflation (${rate(nl.value)}) runs ahead of tradables (${rate(tl.value)})`
          : `Tradables and non-tradables inflation are level at ${rate(tl.value)}`;
      // How long the current ordering has lasted, counted on displayed values.
      const order = (p: string) => {
        const x = at(t, p);
        const y = at(n, p);
        return x && y ? direction(x.value, y.value, 1) : null;
      };
      let run = 0;
      for (let p = period; order(p) === dir; p = addQuarters(p, -1)) run++;
      const tq = trad.points.at(-1)?.quarterly_pct;
      const nq = non.points.at(-1)?.quarterly_pct;
      stories.push({
        ...base, id: `inflation-tradables-${period}`, template: "inflation-tradables", priority: 2,
        headline,
        dek: `Prices of goods and services exposed to foreign competition ${moved(tl.value)} over the year to the ${quarterName(period)}; domestically driven prices ${moved(nl.value)}.`,
        stat: {
          value: ppShort(gap, 1), unit: "gap in annual inflation, tradables minus non-tradables",
          label: `Tradables ${rate(tl.value)} · non-tradables ${rate(nl.value)}`, sign: signOf(gap, 1),
        },
        explanation: [
          "Tradable goods and services are exposed to foreign competition, such as fuel and imported goods. Non-tradables face no foreign competition, such as rents, rates and many services.",
          ...(tq != null && nq != null ? [`In the quarter alone, tradables changed ${rate(tq)} and non-tradables ${rate(nq)}.`] : []),
        ],
        context: [
          dir === "flat"
            ? "The two rates are equal at the published precision."
            : `${dir === "up" ? "Tradables" : "Non-tradables"} inflation has been the higher of the two for ${run} quarter${run === 1 ? "" : "s"} in a row.`,
        ],
        caveats: [...releaseCaveats(a), "Non-tradables inflation is not core inflation. The gap is in percentage points."],
        evidence: [
          { label: "Tradables, annual change", seriesKey: trad.key, period, value: tl.value, unit: "percent", status: "final", releaseKey },
          { label: "Non-tradables, annual change", seriesKey: non.key, period, value: nl.value, unit: "percent", status: "final", releaseKey },
        ],
        thumb: {
          kind: "pair", name: "Annual inflation, tradables and non-tradables", format: "pct",
          items: [{ label: "Tradables", value: tl.value }, { label: "Non-tradables", value: nl.value }],
          gap: { label: "Gap", value: ppShort(gap, 1) },
        },
        figure: { kind: "cpi-tradables", tradables: trad, nonTradables: non },
      });
    }
  }
  return stories;
}
