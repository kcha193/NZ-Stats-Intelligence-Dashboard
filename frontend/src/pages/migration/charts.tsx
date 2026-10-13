import { useState } from "react";
import type { PointOut, SeriesData } from "@/api/types";
import { QueryBoundary } from "@/components/QueryBoundary";
import { Segmented } from "@/components/Segmented";
import { ChartCard } from "@/charts/ChartCard";
import {
  divergingBarOption, lineOption, rankedBarOption, revisionBarOption, sliceYears,
  stackedPanelsOption, type ChartPoint,
} from "@/charts/options";
import { useChartTheme } from "@/charts/theme";
import { useCountries, useRevisions, useSeries } from "@/api/hooks";
import { formatNet, formatNumber, monthLabel, periodLabel } from "@/lib/format";

export type Range = 5 | 10 | null;

const toPoints = (d: SeriesData): ChartPoint[] =>
  d.points.map((p: PointOut) => ({ period: p.period, value: p.value, status: p.status }));
const csv = (d: SeriesData, points: ChartPoint[]) =>
  points.map((p) => ({ series: d.series.key, period: p.period, value: p.value, status: p.status, unit: d.series.unit }));
const source = (d: SeriesData) => ({ label: `Stats NZ, ${d.vintage.title}`, url: d.source_url, updated: d.vintage.published_at });
const latest = (pts: ChartPoint[]) => pts[pts.length - 1];
// "Year ended Jul 2026" -> "year ended Jul 2026": lowercase the sentence start only, never the month.
const lcFirst = (s: string) => s.charAt(0).toLowerCase() + s.slice(1);
const shortTitle = (t: string) => t.replace(/^International migration: /, "");

const FREQ_OPTIONS = [
  { value: "monthly", label: "Monthly" },
  { value: "rolling_annual", label: "Year ended" },
] as const;

function Frequency({ value, onChange, label }: { value: "monthly" | "rolling_annual"; onChange: (v: "monthly" | "rolling_annual") => void; label: string }) {
  return <Segmented value={value} onChange={onChange} options={FREQ_OPTIONS} label={label} />;
}

export function NetTrendChart({ range }: { range: Range }) {
  const [freq, setFreq] = useState<"monthly" | "rolling_annual">("rolling_annual");
  const q = useSeries(freq === "monthly" ? "mig.m.net" : "mig.ry.net");
  const theme = useChartTheme();
  return (
    <QueryBoundary query={q}>
      {(d) => {
        const pts = sliceYears(toPoints(d), range);
        const last = latest(pts);
        const what = freq === "monthly" ? "Monthly net migration" : "Year-ended net migration";
        const title = last
          ? `${what}: ${formatNet(last.value)} (${lcFirst(periodLabel(last.period, freq))})`
          : what;
        const option =
          freq === "monthly"
            ? divergingBarOption({ name: what, points: pts, unit: d.series.unit, frequency: "monthly" }, theme)
            : lineOption({ series: [{ name: what, points: pts, color: theme.series[0] }], unit: d.series.unit, frequency: "rolling_annual" }, theme);
        return (
          <ChartCard
            title={title}
            question="Is net migration a gain or a loss, and how has it moved over time?"
            unit={d.series.unit} source={source(d)} caveat={d.caveat}
            option={option} ariaLabel={`${what} chart`}
            csvFilename={`${d.series.key}.csv`} csvRows={csv(d, pts)}
            controls={<Frequency value={freq} onChange={setFreq} label="Net migration frequency" />}
          />
        );
      }}
    </QueryBoundary>
  );
}

export function ArrivalsDeparturesChart({ range }: { range: Range }) {
  const [freq, setFreq] = useState<"monthly" | "rolling_annual">("rolling_annual");
  const prefix = freq === "monthly" ? "mig.m" : "mig.ry";
  const arr = useSeries(`${prefix}.arrivals`);
  const dep = useSeries(`${prefix}.departures`);
  const theme = useChartTheme();
  if (!arr.data || !dep.data) return <QueryBoundary query={arr.isError ? arr : dep}>{() => null}</QueryBoundary>;
  const a = sliceYears(toPoints(arr.data), range);
  const d = sliceYears(toPoints(dep.data), range);
  const la = latest(a);
  const ld = latest(d);
  return (
    <ChartCard
      title={`Arrivals and departures, ${lcFirst(periodLabel(la.period, freq))}: ${formatNumber(la.value)} in, ${formatNumber(ld.value)} out`}
      question="Is the net result driven by more people arriving or fewer leaving?"
      unit="people" source={source(arr.data)} caveat={arr.data.caveat}
      option={lineOption({ series: [
        { name: "Migrant arrivals", points: a, color: theme.series[0] },
        { name: "Migrant departures", points: d, color: theme.series[1] },
      ], unit: "people", frequency: freq }, theme)}
      ariaLabel="Arrivals and departures chart"
      csvFilename={`arrivals-departures-${freq}.csv`}
      csvRows={a.map((p) => ({ period: p.period, arrivals: p.value, departures: d.find((x) => x.period === p.period)?.value ?? null, status: p.status }))}
      controls={<Frequency value={freq} onChange={setFreq} label="Arrivals and departures frequency" />}
    />
  );
}

export function MonthlyVsAnnualChart({ range }: { range: Range }) {
  const m = useSeries("mig.m.net");
  const y = useSeries("mig.ry.net");
  const theme = useChartTheme();
  if (!m.data || !y.data) return <QueryBoundary query={m.isError ? m : y}>{() => null}</QueryBoundary>;
  const monthly = sliceYears(toPoints(m.data), range);
  const yearEnded = sliceYears(toPoints(y.data), range);
  return (
    <ChartCard
      title="Monthly estimate versus year ended total of net migration, on separate scales"
      question="How do single-month swings relate to the rolling twelve-month total?"
      unit="people" source={source(m.data)}
      caveat="Monthly estimates and year-ended totals are different series: each panel has its own axis and they must not be compared directly."
      option={stackedPanelsOption({ monthly, yearEnded, unit: "people" }, theme)}
      ariaLabel="Monthly estimate and year-ended net migration chart" height={460}
      csvFilename="net-migration-monthly-and-year-ended.csv"
      csvRows={monthly.map((p) => ({ period: p.period, monthly_net: p.value, year_ended_net: yearEnded.find((x) => x.period === p.period)?.value ?? null, status: p.status }))}
    />
  );
}

const MEASURES = [
  { id: "net", label: "Net migration" },
  { id: "arrivals", label: "Arrivals" },
  { id: "departures", label: "Departures" },
] as const;

type Measure = (typeof MEASURES)[number]["id"];
const MEASURE_OPTIONS: { value: Measure; label: string }[] = MEASURES.map((m) => ({ value: m.id, label: m.label }));

export function CitizenshipChart({ range }: { range: Range }) {
  const [measure, setMeasure] = useState<Measure>("net");
  const nz = useSeries(`mig.ry.${measure}.nz`);
  const nonnz = useSeries(`mig.ry.${measure}.nonnz`);
  const theme = useChartTheme();
  if (!nz.data || !nonnz.data) return <QueryBoundary query={nz.isError ? nz : nonnz}>{() => null}</QueryBoundary>;
  // The pair is only comparable when both series come from the same ingested bundle.
  const sameBundle =
    nz.data.vintage.release_key === nonnz.data.vintage.release_key &&
    nz.data.vintage.captured_at === nonnz.data.vintage.captured_at;
  const a = sliceYears(toPoints(nonnz.data), range);
  const b = sliceYears(toPoints(nz.data), range);
  // Values are quoted for the latest period both series have, never an older point under a newer name.
  const shared = a.map((p) => p.period).filter((p) => b.some((x) => x.period === p));
  const at = shared[shared.length - 1];
  const label = MEASURES.find((m) => m.id === measure)!.label.toLowerCase();
  if (!sameBundle || at === undefined) {
    return (
      <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
        The year-ended {label} split by citizenship is not shown: the two series come from different releases or ingests, or share no period, so they are not combined.
      </p>
    );
  }
  return (
    <ChartCard
      title={`Year-ended ${label} by citizenship, ${lcFirst(periodLabel(at, "rolling_annual"))}: non-NZ citizens ${formatNumber(a.find((p) => p.period === at)!.value)}, NZ citizens ${formatNumber(b.find((p) => p.period === at)!.value)}`}
      question="Which citizens account for the year-ended result?"
      unit="people" source={source(nz.data)} caveat={nz.data.caveat}
      option={lineOption({ series: [
        { name: "Non-NZ citizens", points: a, color: theme.series[0] },
        { name: "NZ citizens", points: b, color: theme.series[1] },
      ], unit: "people", frequency: "rolling_annual" }, theme)}
      ariaLabel={`Year-ended ${label} by citizenship chart`}
      csvFilename={`citizenship-${measure}-year-ended.csv`}
      csvRows={a.map((p) => ({ period: p.period, non_nz_citizens: p.value, nz_citizens: b.find((x) => x.period === p.period)?.value ?? null, status: p.status }))}
      controls={
        <Segmented<Measure> value={measure} onChange={setMeasure} options={MEASURE_OPTIONS} label="Citizenship measure" />
      }
    />
  );
}

export function CountryChart() {
  const q = useCountries(12, 15);
  const theme = useChartTheme();
  return (
    <QueryBoundary query={q} isEmpty={(d) => !d.available} empty={<p className="text-sm text-muted-foreground">No country data has been ingested yet.</p>}>
      {(d) => (
        <>
          <ChartCard
            title={`Migrant arrivals by country of last permanent residence, ${monthLabel(d.period_start!)} to ${monthLabel(d.period_end!)}`}
            question="Which countries do arriving migrants come from?"
            unit="people (sum of 12 monthly estimates)"
            source={{ label: "Stats NZ, International migration (derived)", url: null, updated: null }}
            caveat={`${d.note} Lighter bars include provisional months. Regions are shown separately below.`}
            option={rankedBarOption({ items: d.countries.map((c) => ({ name: c.name, value: c.value, provisional: c.provisional })), unit: "people" }, theme)}
            ariaLabel="Arrivals by country of last permanent residence chart" height={420}
            csvFilename="arrivals-by-country.csv"
            csvRows={d.countries.map((c) => ({ country: c.name, arrivals_12m: c.value, share_percent: c.share_percent, prior_12m: c.prior_value, includes_provisional: c.provisional ? "yes" : "no" }))}
          />
          <p className="mt-2 text-xs text-muted-foreground">
            Derived total. Regions: {d.regions.map((r) => `${r.name} ${formatNumber(r.value)}`).join(" · ")}
            {d.unallocated ? ` · ${d.unallocated.name} ${formatNumber(d.unallocated.value)}` : ""}.
          </p>
        </>
      )}
    </QueryBoundary>
  );
}

export function RevisionChart() {
  const q = useRevisions("mig.m.net");
  const theme = useChartTheme();
  return (
    <QueryBoundary query={q}>
      {(d) => (
        <div className="space-y-2">
          {d.rows.length > 0 && d.base && d.compare ? (
            <ChartCard
              title={`Revisions to monthly net migration between the ${shortTitle(d.base.title)} and ${shortTitle(d.compare.title)} releases`}
              question="How much were earlier estimates revised?"
              unit="people (revised minus original)"
              source={{ label: `Stats NZ, ${d.compare.title}`, url: null, updated: d.compare.published_at }}
              caveat={d.coverage.note}
              option={revisionBarOption({ rows: d.rows.map((r) => ({ period: r.period, absolute: r.absolute })), unit: "people" }, theme)}
              ariaLabel="Revisions to monthly net migration chart"
              csvFilename="net-migration-revisions.csv"
              csvRows={d.rows.map((r) => ({ period: r.period, original: r.original, revised: r.revised, absolute: r.absolute, percent: r.percent, original_status: r.original_status, revised_status: r.revised_status }))}
            />
          ) : (
            <div className="rounded-md border p-4 text-sm">
              <h3 className="font-semibold">Revisions to monthly net migration</h3>
              <p className="mt-1 text-muted-foreground">{d.coverage.note}</p>
            </div>
          )}
        </div>
      )}
    </QueryBoundary>
  );
}
