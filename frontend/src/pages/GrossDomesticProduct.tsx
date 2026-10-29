import { useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "@/api/client";
import { useGdp } from "@/api/hooks";
import { isStaticMode } from "@/api/mode";
import type { GdpDashboard } from "@/api/types";
import { ChartCard } from "@/charts/ChartCard";
import { CPI_RANGES, type CpiRange } from "@/charts/cpi";
import { firstLatestOption, firstLatestRows, growthOption } from "@/charts/macro";
import { useChartTheme } from "@/charts/theme";
import { InsightList } from "@/components/InsightList";
import { MetricTiles } from "@/components/MetricTiles";
import { EmptyState, QueryBoundary } from "@/components/QueryBoundary";
import { Segmented } from "@/components/Segmented";
import { formatAklDateTime, monthLabel } from "@/lib/format";
import { ROUTE_META } from "@/seo/routes";
import { useDocumentTitle } from "@/seo/useDocumentTitle";

const MEASURES = [
  { value: "gdp.production.cv.sa.pct_qoq", label: "Quarterly", note: "Seasonally adjusted change from the previous quarter." },
  { value: "gdp.production.cv.nsa.pct_annual_avg", label: "Annual average", note: "The four quarters to date against the four before them, from actual values. Stats NZ's release page calls this \"Annual growth\"." },
  { value: "gdp.production.cv.sa.pct_yoy", label: "Annual change of the quarter", note: "Seasonally adjusted change from the same quarter a year earlier. Not annual average growth." },
];

function Dashboard({ data }: { data: GdpDashboard }) {
  const [measure, setMeasure] = useState(MEASURES[0].value);
  const [range, setRange] = useState<CpiRange>("5y");
  const [table, setTable] = useState(0);
  const theme = useChartTheme();
  const a = data.analysis;
  const rel = a.release;
  const selected = data.series.find((s) => s.key === measure)!;
  const chosen = MEASURES.find((m) => m.value === measure)!;
  const revisions = data.revisions[table];
  const source = { label: `Stats NZ, ${rel.title}`, url: rel.page_url, updated: rel.published_at, captured: a.vintage_captured_at };
  const meta = { releaseKey: rel.release_key, sourceUrl: selected.source_url ?? null };
  return (
    <div className="space-y-5">
      <header>
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Economic growth</p>
        <h1 className="text-xl font-semibold tracking-tight">Gross domestic product</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Reference period: {monthLabel(data.reference_period)} quarter · Published {formatAklDateTime(data.published_at)} · Real (chain-volume, 2009/10 prices), production measure
        </p>
      </header>
      <MetricTiles label="GDP key indicators" metrics={a.headline_metrics} />
      <section aria-label="GDP growth" className="space-y-3">
        <div className="flex flex-wrap items-end gap-3">
          <Segmented label="Growth measure" value={measure} onChange={setMeasure} options={MEASURES.map(({ value, label }) => ({ value, label }))} />
          <Segmented label="History window" value={range} onChange={(v) => setRange(v as CpiRange)} options={CPI_RANGES.map(({ value, label }) => ({ value, label }))} />
        </div>
        <ChartCard
          title={`${selected.name}`}
          question={`How has real GDP changed? ${chosen.note}`}
          unit="percent" source={source}
          caveat="Published by Stats NZ to one decimal place and revised as new information arrives. Each measure is drawn on its own chart."
          option={growthOption(selected, range, theme)} ariaLabel="GDP growth history"
          csvFilename="gdp-growth.csv"
          csvRows={selected.points.map((p) => ({ period: p.period, value: p.value, unit: "percent", measure: selected.measure,
            adjustment: selected.adjustment, status: p.status, series_key: selected.key, release_key: meta.releaseKey, source_url: meta.sourceUrl ?? "" }))}
        />
      </section>
      <section aria-label="GDP revisions" className="space-y-3">
        <Segmented label="Revised measure" value={String(table)} onChange={(v) => setTable(Number(v))}
          options={data.revisions.map((_, i) => ({ value: String(i), label: i === 0 ? "Quarterly growth" : "Annual average growth" }))} />
        {revisions?.available ? (
          <ChartCard
            title={`${revisions.label}: first published and latest`}
            question="How much have recent quarters been revised since they were first published?"
            unit="percent" source={source} caveat={revisions.note}
            option={firstLatestOption(revisions, theme, "%")} ariaLabel="GDP growth, first published and latest"
            csvFilename="gdp-first-published-latest.csv" csvRows={firstLatestRows(revisions, meta)}
          />
        ) : (
          <EmptyState title="Revisions need two releases" body={revisions?.note ?? "Only one GDP release is stored."} />
        )}
      </section>
      <section aria-labelledby="gdp-analysis" className="rounded-md border p-4">
        <h2 id="gdp-analysis" className="text-lg font-semibold">Latest release analysis</h2>
        <div className="mt-3"><InsightList insights={a.executive_summary} /></div>
        <div className="mt-3"><InsightList insights={a.context} /></div>
        <div className="mt-3 flex flex-wrap gap-x-5 text-sm underline underline-offset-2">
          <Link to={`/releases/${rel.id}`}>Full release analysis</Link>
          <Link to="/economic-outlook">Compare with forecasts</Link>
        </div>
      </section>
      <section aria-labelledby="gdp-method" className="space-y-2">
        <h2 id="gdp-method" className="text-lg font-semibold">Source and methodology</h2>
        <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">{data.caveats.map((t) => <li key={t}>{t}</li>)}</ul>
        <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm underline underline-offset-2">
          {rel.page_url && <a href={rel.page_url} target="_blank" rel="noreferrer">Official Stats NZ release</a>}
          {selected.source_url && <a href={selected.source_url} target="_blank" rel="noreferrer">Official GDP CSV</a>}
        </div>
        <p className="text-xs text-muted-foreground">Data captured {formatAklDateTime(data.captured_at)}. {isStaticMode() ? "This site is updated after each verified Stats NZ release." : "Automatic refresh follows the official release calendar."} <Link className="underline" to="/health">Data health</Link></p>
      </section>
    </div>
  );
}

export default function GrossDomesticProduct() {
  useDocumentTitle(ROUTE_META["/gdp"].title);
  const q = useGdp();
  if (q.error instanceof ApiError && q.error.status === 404) return isStaticMode()
    ? <EmptyState title="GDP data has not been published yet" body="This dashboard appears once a Stats NZ GDP release has been verified and published here." />
    : <EmptyState title="GDP data has not been ingested yet" body="The next GDP release, or a deliberate backfill, will populate this dashboard. Check Data health for ingestion status." />;
  return <QueryBoundary query={q}>{(d) => <Dashboard data={d} />}</QueryBoundary>;
}
