import type { PointOut, ReleaseSummary, SeriesData } from "@/api/types";
import { formatNet, formatNumber } from "@/lib/format";
import { provenanceOfSeries, sameBundle, statusCaveats } from "./common";
import { addMonths, direction, monthName, people, signedPeople, signedRate, signOf, yearEndedName } from "./text";
import type { EvidenceRow, Story } from "./types";

export type MigrationInput = {
  net?: SeriesData; arrivals?: SeriesData; departures?: SeriesData; nz?: SeriesData; nonNz?: SeriesData;
  /** Release summaries that attach the release id, page and status to a series vintage. */
  releases: Pick<ReleaseSummary, "id" | "release_key" | "page_url" | "status">[];
};

const DASHBOARD = { to: "/migration", label: "Explore the migration dashboard" };
const PROVISIONAL = "Estimates for recent months are provisional and are revised as travellers' outcomes become known.";

/** A year-ended net figure in words, inside a sentence: "a net gain of 9,592" or "no net change". */
const netPhrase = (v: number) => (Math.round(v) === 0 ? "no net change" : `a ${formatNet(v)}`);

const latestOf = (d: SeriesData) => d.points.at(-1);
const atPeriod = (d: SeriesData, p: string) => d.points.find((x) => x.period === p);
const tenYears = (d: SeriesData, period: string) => d.points.filter((p) => p.period > addMonths(period, -120));

export function buildMigrationStories(input: MigrationInput): Story[] {
  // Each story takes its provenance from its own series: the latest vintage of one series can be an earlier release
  // than another's (a release may omit a chart), and a story is only as current as the bundle it was built from.
  const release = (d: SeriesData) => input.releases.find((r) => r.release_key === d.vintage.release_key);
  const provenanceOf = (d: SeriesData) => ({
    // A series that was ingested belongs to a published release; without its summary that is all that can be said.
    ...provenanceOfSeries(d, "international-migration", release(d)?.id ?? null, release(d)?.status ?? "published"),
    pageUrl: release(d)?.page_url ?? d.source_url ?? null,
  });
  const evidence = (label: string, d: SeriesData, p: PointOut): EvidenceRow => ({
    label, seriesKey: d.series.key, period: p.period, value: p.value, unit: d.series.unit, status: p.status, releaseKey: d.vintage.release_key,
  });
  const common = (d: SeriesData, p: PointOut) => {
    const provenance = provenanceOf(d);
    return {
      category: "migration" as const, referencePeriod: p.period, referenceLabel: `Year ended ${monthName(p.period)}`,
      dataStatus: p.status, provenance, dashboard: DASHBOARD, insights: [],
      methodology: [d.series.definition, "Net migration is long-term migrant arrivals minus long-term migrant departures."],
      caveats: [...statusCaveats(provenance.status), ...(p.status === "provisional" ? [PROVISIONAL] : []), d.caveat],
    };
  };
  const stories: Story[] = [];

  // 1. Year-ended net migration against the same measure a year earlier.
  const net = input.net;
  const n = net && latestOf(net);
  const n0 = net && n && atPeriod(net, addMonths(n.period, -12));
  if (net && n && n0) {
    const dir = direction(n.value, n0.value, 0);
    const v = people(Math.abs(n.value));
    const headline = n.value > 0 && n0.value > 0
      ? `Annual net migration gain ${{ up: "rises to", down: "narrows to", flat: "holds at" }[dir]} ${v}`
      : n.value < 0 && n0.value < 0
        ? `Annual net migration loss ${{ up: "narrows to", down: "widens to", flat: "holds at" }[dir]} ${v}`
        : n.value > 0 ? `Annual net migration returns to a gain of ${v}` : n.value < 0 ? `Annual net migration turns to a loss of ${v}` : "Annual net migration is balanced";
    const same = Math.sign(n.value) === Math.sign(n0.value) && n.value !== 0;
    const movement = same ? `${Math.abs(n.value) >= Math.abs(n0.value) ? "up" : "down"} from` : "compared with";
    const peak = tenYears(net, n.period).reduce((m, p) => (p.value > m.value ? p : m), n);
    stories.push({
      ...common(net, n), id: `migration-net-${n.period}`, template: "migration-net", priority: 0, headline,
      dek: `${Math.round(n.value) === 0 ? "Arrivals and departures were balanced" : n.value > 0 ? `New Zealand gained ${v} more migrants than it lost` : `New Zealand lost ${v} more migrants than it gained`} in the ${yearEndedName(n.period)}, ${movement} ${netPhrase(n0.value)} a year earlier.${n.status === "provisional" ? " The latest estimate is provisional." : ""}`,
      stat: {
        value: signedPeople(n.value), unit: `people, net migration in the ${yearEndedName(n.period)}`,
        label: `${n.status === "provisional" ? "Provisional" : "Final"} estimate${n.std_error != null ? `, standard error ${people(n.std_error)}` : ""}`,
        sign: signOf(n.value, 0),
      },
      explanation: [
        "Net migration counts long-term migrant arrivals minus departures. A traveller counts as a migrant if they spend 12 of the following 16 months in, or out of, New Zealand, so the most recent months are estimated before those outcomes are known.",
        `The year-ended total for ${monthName(n.period)} adds up the twelve months to ${monthName(n.period)}. It is compared here with the twelve months to ${monthName(n0.period)}, which do not overlap.`,
      ],
      context: peak.period !== n.period && peak.value > 0
        ? [`The largest annual net gain in the last ten years was ${people(peak.value)}, in the ${yearEndedName(peak.period)}.`]
        : [],
      evidence: [evidence("Net migration, latest year", net, n), evidence("Net migration, a year earlier", net, n0), ...(peak.period !== n.period ? [evidence("Ten-year high", net, peak)] : [])],
      thumb: { kind: "line", values: tenYears(net, n.period).map((p) => p.value), zero: true },
      figure: { kind: "mig-net", series: net },
    });
  }

  // 2. Arrivals against departures, each with its own year-earlier comparison.
  const { arrivals, departures } = input;
  if (arrivals && departures && sameBundle(arrivals, departures)) {
    const a = latestOf(arrivals);
    const d = latestOf(departures);
    const a0 = a && atPeriod(arrivals, addMonths(a.period, -12));
    const d0 = d && atPeriod(departures, addMonths(d.period, -12));
    if (a && d && a0 && d0 && a.period === d.period) {
      const pa = (a.value / a0.value - 1) * 100;
      const pd = (d.value / d0.value - 1) * 100;
      const part = (name: string, pct: number) => {
        const dir = direction(pct, 0, 1);
        return dir === "flat" ? `${name} are little changed` : `${name} ${dir === "up" ? "rise" : "fall"} ${formatNumber(Math.abs(pct), { decimals: 1 })}%`;
      };
      const gap = a.value - d.value;
      const line = (name: string, cur: PointOut, prev: PointOut, pct: number) =>
        `${name}: ${people(cur.value)}, ${cur.value >= prev.value ? "up" : "down"} ${people(Math.abs(cur.value - prev.value))} (${signedRate(pct)}) on the ${yearEndedName(prev.period)}.`;
      stories.push({
        ...common(arrivals, a), id: `migration-flows-${a.period}`, template: "migration-flows", priority: 1,
        dataStatus: a.status === "provisional" || d.status === "provisional" ? "provisional" : a.status,
        headline: `${part("Migrant arrivals", pa)} while ${part("departures", pd)}`,
        dek: `In the ${yearEndedName(a.period)}, ${people(a.value)} migrants arrived and ${people(d.value)} departed, so ${
          gap > 0 ? `arrivals exceeded departures by ${people(gap)}` : gap < 0 ? `departures exceeded arrivals by ${people(-gap)}` : "arrivals and departures were equal"}.`,
        stat: { value: people(a.value), unit: `migrant arrivals, ${yearEndedName(a.period)}`, label: `Departures: ${people(d.value)}`, sign: "neutral" },
        explanation: [
          "Arrivals and departures move net migration from both sides: a larger net gain can come from more people arriving, fewer leaving, or both.",
        ],
        context: [line("Arrivals", a, a0, pa), line("Departures", d, d0, pd)],
        evidence: [
          evidence("Arrivals, latest year", arrivals, a), evidence("Arrivals, a year earlier", arrivals, a0),
          evidence("Departures, latest year", departures, d), evidence("Departures, a year earlier", departures, d0),
        ],
        thumb: { kind: "line", values: tenYears(arrivals, a.period).map((p) => p.value), compare: tenYears(departures, d.period).map((p) => p.value), zero: false },
        figure: { kind: "mig-flows", arrivals, departures },
      });
    }
  }

  // 3. New Zealand citizens against citizens of other countries.
  const { nz, nonNz } = input;
  if (nz && nonNz && sameBundle(nz, nonNz)) {
    const z = latestOf(nz);
    const o = latestOf(nonNz);
    if (z && o && z.period === o.period) {
      // Numbers live in the statistic and the dek; the headline states the relationship.
      const headline = o.value > 0 && z.value < 0
        ? Math.abs(o.value) >= Math.abs(z.value)
          ? "Net loss of New Zealand citizens is offset by a larger gain of other citizens"
          : "Net loss of New Zealand citizens outweighs the gain of other citizens"
        : `Net migration by citizenship: New Zealand citizens ${signedPeople(z.value)}, other citizens ${signedPeople(o.value)}`;
      // How long New Zealand citizens' year-ended net has kept its current sign.
      let first = z;
      for (let i = nz.points.length - 2; i >= 0 && Math.sign(nz.points[i].value) === Math.sign(z.value); i--) first = nz.points[i];
      const net = input.net && sameBundle(input.net, nz) ? atPeriod(input.net, z.period) : undefined;
      const z0 = atPeriod(nz, addMonths(z.period, -12));
      const o0 = atPeriod(nonNz, addMonths(o.period, -12));
      stories.push({
        ...common(nz, z), id: `migration-citizenship-${z.period}`, template: "migration-citizenship", priority: 2,
        dataStatus: z.status === "provisional" || o.status === "provisional" ? "provisional" : z.status,
        headline,
        dek: `In the ${yearEndedName(z.period)}, New Zealand citizens recorded ${netPhrase(z.value)} and non-New Zealand citizens ${netPhrase(o.value)}.`,
        stat: {
          value: signedPeople(z.value), unit: `people, net migration of New Zealand citizens, ${yearEndedName(z.period)}`,
          label: `Non-New Zealand citizens: ${signedPeople(o.value)}`, sign: signOf(z.value, 0),
        },
        explanation: [
          "Stats NZ publishes migration for two citizenship groups: New Zealand citizens and everyone else (non-New Zealand citizens). Each group's net figure is its long-term arrivals minus its long-term departures.",
        ],
        context: [
          ...(first.period !== z.period && z.value !== 0
            ? [`Year-ended net migration of New Zealand citizens has been a ${z.value < 0 ? "loss" : "gain"} in every month since ${monthName(first.period)}.`]
            : []),
          ...(z0 && o0 ? [`A year earlier: New Zealand citizens, ${formatNet(z0.value)}; non-New Zealand citizens, ${formatNet(o0.value)}.`] : []),
          ...(net && net.value === z.value + o.value ? [`Together they make up the total ${formatNet(net.value)}.`] : []),
        ],
        evidence: [
          evidence("New Zealand citizens, latest year", nz, z), evidence("Non-New Zealand citizens, latest year", nonNz, o),
          ...(z0 ? [evidence("New Zealand citizens, a year earlier", nz, z0)] : []), ...(o0 ? [evidence("Non-New Zealand citizens, a year earlier", nonNz, o0)] : []),
        ],
        thumb: { kind: "line", values: tenYears(nonNz, o.period).map((p) => p.value), compare: tenYears(nz, z.period).map((p) => p.value), zero: true },
        figure: { kind: "mig-citizenship", nonNz, nz },
      });
    }
  }
  return stories;
}
