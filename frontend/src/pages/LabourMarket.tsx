import { useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "@/api/client";
import { useLabourMarket } from "@/api/hooks";
import { isStaticMode } from "@/api/mode";
import type { LabourDashboard } from "@/api/types";
import { ChartCard } from "@/charts/ChartCard";
import { CPI_RANGES, type CpiRange } from "@/charts/cpi";
import { firstLatestOption, firstLatestRows, rateOption } from "@/charts/macro";
import { useChartTheme } from "@/charts/theme";
import { InsightList } from "@/components/InsightList";
import { MetricTiles } from "@/components/MetricTiles";
import { EmptyState, QueryBoundary } from "@/components/QueryBoundary";
import { Segmented } from "@/components/Segmented";
import { formatAklDateTime, monthLabel } from "@/lib/format";
import { ROUTE_META } from "@/seo/routes";
import { useDocumentTitle } from "@/seo/useDocumentTitle";

const RATES = [
  { value: "hlfs.rate.unemployment.sa", label: "Unemployment" },
  { value: "hlfs.rate.employment.sa", label: "Employment" },
  { value: "hlfs.rate.participation.sa", label: "Participation" },
  { value: "hlfs.rate.underutilisation.sa", label: "Underutilisation" },
];

function Dashboard({ data }: { data: LabourDashboard }) {
  const [rate, setRate] = useState(RATES[0].value);
  const [range, setRange] = useState<CpiRange>("10y");
  const theme = useChartTheme();
  const a = data.analysis;
  const rel = a.release;
  const series = new Map(data.series.map((s) => [s.key, s]));
  const selected = series.get(rate)!;
  const lci = series.get("lci.all_wages.pct_yoy")!;
  const revisions = data.revisions[0];
  const source = { label: `Stats NZ, ${rel.title}`, url: rel.page_url, updated: rel.published_at, captured: a.vintage_captured_at };
  const meta = { releaseKey: rel.release_key, sourceUrl: selected.source_url ?? null };
  const rows = (s: typeof selected) => s.points.map((p) => ({ period: p.period, value: p.value, unit: s.unit, survey: s.survey,
    measure: s.measure, adjustment: s.adjustment, status: p.status, series_key: s.key, release_key: meta.releaseKey, source_url: meta.sourceUrl ?? "" }));
  const lciInsight = a.context.filter((i) => i.id === "lci");
  return (
    <div className="space-y-5">
      <header>
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Household Labour Force Survey and Labour Cost Index</p>
        <h1 className="text-xl font-semibold tracking-tight">Labour market</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Reference period: {monthLabel(data.reference_period)} quarter · Published {formatAklDateTime(data.published_at)} · HLFS rates seasonally adjusted
        </p>
      </header>
      <MetricTiles label="Labour market key indicators" metrics={a.headline_metrics} />
      <section aria-label="Labour market rates" className="space-y-3">
        <div className="flex flex-wrap items-end gap-3">
          <Segmented label="Rate" value={rate} onChange={setRate} options={RATES} />
          <Segmented label="History window" value={range} onChange={(v) => setRange(v as CpiRange)} options={CPI_RANGES.map(({ value, label }) => ({ value, label }))} />
        </div>
        <ChartCard
          title={selected.name}
          question="How has this rate moved? One rate per chart, on its own scale."
          unit="percent" source={source}
          caveat="HLFS is a sample survey: small quarterly movements may not be statistically significant. Seasonally adjusted history is re-estimated every quarter."
          option={rateOption(selected, range, theme)} ariaLabel="Labour market rate history"
          csvFilename="labour-market-rate.csv" csvRows={rows(selected)}
        />
      </section>
      {revisions?.available ? (
        <ChartCard
          title="Unemployment rate: stored baseline and latest"
          question="How have recent unemployment rates changed across stored vintages?"
          unit="percent" source={source} caveat={revisions.note}
          option={firstLatestOption(revisions, theme, "%")} ariaLabel="Unemployment rate, stored baseline and latest"
          csvFilename="unemployment-first-published-latest.csv" csvRows={firstLatestRows(revisions, meta)}
        />
      ) : (
        <EmptyState title="Revisions need two releases" body={revisions?.note ?? "Only one labour market release is stored."} />
      )}
      <section aria-labelledby="lci-heading" className="space-y-3">
        <h2 id="lci-heading" className="text-lg font-semibold">Wage rates: Labour Cost Index</h2>
        <p className="text-sm text-muted-foreground">A different survey from the HLFS. The LCI measures the price of labour for the same job; it is not average earnings.</p>
        <ChartCard
          title={lci.name}
          question="How fast are salary and wage rates rising? All sectors, change from the same quarter a year earlier."
          unit="percent" source={source} caveat="Not seasonally adjusted. Average earnings (Quarterly Employment Survey) are a different measure and are not shown."
          option={rateOption(lci, range, theme)} ariaLabel="Labour Cost Index annual change"
          csvFilename="lci-annual-change.csv" csvRows={rows(lci)}
        />
      </section>
      <section aria-labelledby="labour-analysis" className="rounded-md border p-4">
        <h2 id="labour-analysis" className="text-lg font-semibold">Latest release analysis</h2>
        <div className="mt-3"><InsightList insights={a.executive_summary} /></div>
        {lciInsight.length > 0 && <div className="mt-3"><InsightList insights={lciInsight} /></div>}
        <div className="mt-3 flex flex-wrap gap-x-5 text-sm underline underline-offset-2">
          <Link to={`/releases/${rel.id}`}>Full release analysis</Link>
          <Link to="/economic-outlook">Compare with forecasts</Link>
        </div>
      </section>
      <section aria-labelledby="labour-method" className="space-y-2">
        <h2 id="labour-method" className="text-lg font-semibold">Source and methodology</h2>
        <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">{data.caveats.map((t) => <li key={t}>{t}</li>)}</ul>
        <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm underline underline-offset-2">
          {rel.page_url && <a href={rel.page_url} target="_blank" rel="noreferrer">Official Stats NZ release</a>}
          {selected.source_url && <a href={selected.source_url} target="_blank" rel="noreferrer">Official labour market ZIP</a>}
        </div>
        <p className="text-xs text-muted-foreground">Data captured {formatAklDateTime(data.captured_at)}. {isStaticMode() ? "This site is updated after each verified Stats NZ release." : "Automatic refresh follows the official release calendar."} <Link className="underline" to="/health">Data health</Link></p>
      </section>
    </div>
  );
}

export default function LabourMarket() {
  useDocumentTitle(ROUTE_META["/labour-market"].title);
  const q = useLabourMarket();
  if (q.error instanceof ApiError && q.error.status === 404) return isStaticMode()
    ? <EmptyState title="Labour market data has not been published yet" body="This dashboard appears once a Stats NZ labour market release has been verified and published here." />
    : <EmptyState title="Labour market data has not been ingested yet" body="The next labour market release, or a deliberate backfill, will populate this dashboard. Check Data health for ingestion status." />;
  return <QueryBoundary query={q}>{(d) => <Dashboard data={d} />}</QueryBoundary>;
}
