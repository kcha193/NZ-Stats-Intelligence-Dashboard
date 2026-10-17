import { Link } from "react-router-dom";
import { ApiError } from "@/api/client";
import { useOverview, useSeries } from "@/api/hooks";
import { ChartCard } from "@/charts/ChartCard";
import { statusNote } from "@/charts/exports";
import { lineOption, sliceYears } from "@/charts/options";
import { useChartTheme } from "@/charts/theme";
import { Freshness } from "@/components/Freshness";
import { KpiCard } from "@/components/KpiCard";
import { EmptyState, QueryBoundary } from "@/components/QueryBoundary";
import { ReleaseRow } from "@/components/ReleaseRow";
import { formatAklDateTime, formatNet, periodLabel } from "@/lib/format";

function TrendOverview() {
  const q = useSeries("mig.ry.net");
  const theme = useChartTheme();
  // After `discover` but before the first backfill the calendar is populated and no series exists yet.
  if (q.error instanceof ApiError && q.error.status === 404) {
    return (
      <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
        The year-ended net migration trend appears once the first release has been ingested.
      </p>
    );
  }
  return (
    <QueryBoundary query={q}>
      {(d) => {
        const pts = sliceYears(d.points.map((p) => ({ period: p.period, value: p.value, status: p.status })), 10);
        const last = pts[pts.length - 1];
        return (
          <ChartCard
            title={
              last
                ? `Year-ended net migration: ${formatNet(last.value)} (${periodLabel(last.period, "rolling_annual").replace(/^Y/, "y")}${statusNote([last.status])})`
                : "Year-ended net migration"
            }
            question="Where is annual net migration relative to the last ten years?"
            unit={d.series.unit} source={{ label: `Stats NZ, ${d.vintage.title}`, url: d.source_url, updated: d.vintage.published_at }}
            caveat={d.caveat} height={260}
            option={lineOption({ series: [{ name: "Year-ended net migration", points: pts, color: theme.series[0] }], unit: d.series.unit, frequency: "rolling_annual" }, theme)}
            ariaLabel="Year-ended net migration, last ten years"
            csvFilename="net-migration-year-ended.csv"
            csvRows={pts.map((p) => ({ period: p.period, value: p.value, status: p.status }))}
          />
        );
      }}
    </QueryBoundary>
  );
}

export default function Overview() {
  const q = useOverview();
  return (
    <QueryBoundary
      query={q}
      isEmpty={(d) => d.kpis.length === 0 && d.latest_releases.length === 0 && d.upcoming.length === 0}
      empty={<EmptyState title="No data has been ingested yet" body="Run `nzstats discover` then `nzstats backfill`, or wait for the next scheduled check. The Data health page shows what has been attempted." />}
    >
      {(d) => (
        <div className="space-y-5">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Economic overview</h1>
            <p className="text-sm text-muted-foreground">
              Latest official Stats NZ statistics. {d.data_updated_at
                ? `Migration data ingested ${formatAklDateTime(d.data_updated_at)}.`
                : "No migration data has been ingested yet."}
            </p>
          </div>
          {d.kpis.length > 0 && (
            <section aria-label="Key indicators" className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {d.kpis.slice(0, 8).map((k) => <KpiCard key={k.metric.series_key} kpi={k} />)}
            </section>
          )}
          <div className="grid gap-5 xl:grid-cols-12">
            <div className="space-y-5 xl:col-span-8">
              {d.featured && (
                <section aria-label="Featured release" className="rounded-md border p-4">
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Featured release</p>
                  <h2 className="mt-1 text-lg font-semibold">{d.featured.release.title}</h2>
                  {d.featured.first_insight && <p className="mt-1 text-sm">{d.featured.first_insight}</p>}
                  <Link className="mt-2 inline-block text-sm underline underline-offset-2" to={`/releases/${d.featured.release.id}`}>
                    Read the full release analysis
                  </Link>
                </section>
              )}
              <TrendOverview />
              <section aria-label="Upcoming releases" className="rounded-md border p-4">
                <h2 className="text-base font-semibold">Upcoming releases</h2>
                <ul className="mt-1 divide-y">{d.upcoming.slice(0, 6).map((r) => <ReleaseRow key={r.id} release={r} />)}</ul>
                <Link className="mt-2 inline-block text-sm underline underline-offset-2" to="/calendar">Full release calendar</Link>
              </section>
            </div>
            <div className="space-y-5 xl:col-span-4">
              <section aria-label="Latest releases" className="rounded-md border p-4">
                <h2 className="text-base font-semibold">Latest releases</h2>
                <ul className="mt-1 divide-y">{d.latest_releases.map((r) => <ReleaseRow key={r.id} release={r} />)}</ul>
              </section>
              <section aria-label="Data freshness" className="rounded-md border p-4">
                <h2 className="text-base font-semibold">Data freshness</h2>
                <div className="mt-2"><Freshness sources={d.freshness} /></div>
              </section>
            </div>
          </div>
          {d.inactive_categories.length > 0 && (
            <p className="text-xs text-muted-foreground">
              Not yet active (no verified source wired in): {d.inactive_categories.map((c) => c.name).join(", ")}.
            </p>
          )}
        </div>
      )}
    </QueryBoundary>
  );
}
