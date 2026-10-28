import { useState } from "react";
import { ROUTE_META } from "@/seo/routes";
import { useDocumentTitle } from "@/seo/useDocumentTitle";
import { Link } from "react-router-dom";
import { ApiError } from "@/api/client";
import { useCpi } from "@/api/hooks";
import { isStaticMode } from "@/api/mode";
import type { CpiDashboard, Metric } from "@/api/types";
import { ChartCard } from "@/charts/ChartCard";
import {
  annualInflationOption, contributionCsvRows, contributionOption, CPI_RANGES, historyCsvRows,
  quarterlyInflationOption, rangeFilter, tradablesOption, type CpiRange, type Horizon,
} from "@/charts/cpi";
import { useChartTheme } from "@/charts/theme";
import { InsightList } from "@/components/InsightList";
import { EmptyState, QueryBoundary } from "@/components/QueryBoundary";
import { Segmented } from "@/components/Segmented";
import { formatAklDate, formatAklDateTime, formatNumber } from "@/lib/format";
import { Explorer } from "./inflation/Explorer";
import { CPI_HISTORY_COLUMNS, CPI_CONTRIBUTION_COLUMNS, CPI_TABLE_NOTE, fullMonth, points, rate } from "./inflation/format";

const LINKS = [
  ["Stats NZ: consumers price index topic", "https://www.stats.govt.nz/topics/consumers-price-index/"],
  ["Stats NZ: price index methods, September 2026 quarter", "https://www.stats.govt.nz/methods/price-index-methods-updates-for-the-september-2026-quarter/"],
  ["Stats NZ: monthly CPI progress", "https://www.stats.govt.nz/methods/monthly-consumers-price-index-updates-on-progress/"],
] as const;

function Tile({ label, metric }: { label: string; metric: Metric }) {
  const compare = (kind: "quarter" | "year") => {
    const c = kind === "quarter" ? metric.change_prior : metric.change_year_ago;
    if (!c) return null;
    const when = kind === "quarter" ? `in the ${fullMonth(c.comparison_period)} quarter` : `a year earlier (${fullMonth(c.comparison_period)} quarter)`;
    return <p key={kind} className="text-xs text-muted-foreground">vs {rate(c.previous)} {when} ({points(c.absolute)})</p>;
  };
  return (
    <article className="rounded-md border bg-card p-3" aria-label={label}>
      <h3 className="text-xs font-medium text-muted-foreground">{label}</h3>
      <p className="mt-1 text-3xl font-semibold leading-none tracking-tight">{rate(metric.value)}</p>
      <div className="mt-2 space-y-0.5">{compare("quarter")}{compare("year")}</div>
    </article>
  );
}

function Dashboard({ data }: { data: CpiDashboard }) {
  const theme = useChartTheme();
  const [range, setRange] = useState<CpiRange>("10y");
  const [band, setBand] = useState(true);
  const [horizon, setHorizon] = useState<Horizon>("annual");
  const [contribution, setContribution] = useState<"quarterly" | "annual">("quarterly");
  const a = data.analysis;
  const rel = a.release;
  const nsa = (slug: string) => data.series.find((s) => s.slug === slug && s.adjustment === "none")!;
  const all = nsa("all_groups");
  const visible = rangeFilter(all.points, range);
  const [annual, quarterly, tradables, non] = a.headline_metrics;
  const source = { label: `Stats NZ, ${rel.title}`, url: rel.page_url ?? null, updated: rel.published_at, captured: a.vintage_captured_at };
  const meta = { releaseKey: rel.release_key, sourceUrl: rel.page_url ?? null };
  const lastPoint = all.points.at(-1)!;
  const block = data.contributions.find((b) => b.horizon === contribution)!;
  const rangeOptions = CPI_RANGES.map((r) => ({ value: r.value, label: r.label }));
  const quarter = `${fullMonth(data.reference_period)} quarter`;
  const latestRate = (slug: string, key: "annual_pct" | "quarterly_pct") => {
    const v = nsa(slug).points.at(-1)?.[key];
    return v === null || v === undefined ? "n/a" : rate(v);
  };
  return (
    <div className="space-y-6">
      <p className="text-sm text-muted-foreground">
        Latest reference quarter: {fullMonth(data.reference_period)} · Published {formatAklDateTime(rel.published_at)}
      </p>

      <section aria-label="CPI key indicators" className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <h2 className="sr-only">CPI key indicators</h2>
        <Tile label="Annual CPI inflation" metric={annual} />
        <Tile label="Quarterly CPI inflation" metric={quarterly} />
        <Tile label="Tradables · annual" metric={tradables} />
        <Tile label="Non-tradables · annual" metric={non} />
      </section>

      <section aria-labelledby="cpi-history" className="space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h2 id="cpi-history" className="text-lg font-semibold">Headline CPI history</h2>
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex min-h-11 items-center gap-2 text-xs sm:min-h-0">
              <input type="checkbox" checked={band} onChange={(e) => setBand(e.target.checked)} />
              Show 1% to 3% reference band
            </label>
            <Segmented<CpiRange> label="History range" value={range} onChange={setRange} options={rangeOptions} />
          </div>
        </div>
        <div className="grid min-w-0 gap-5 xl:grid-cols-2">
          <ChartCard title="Annual CPI inflation" question={`${quarter}: annual inflation was ${rate(annual.value)}. How has it moved over time?`}
            unit="percent change from the same quarter a year earlier" source={source}
            caveat="The 1% to 3% band is a reference only and is not a forecast. Missing quarters are left as gaps."
            option={annualInflationOption(visible, theme, { band })} ariaLabel="Annual CPI inflation history" height={300}
            tableColumns={CPI_HISTORY_COLUMNS} tableNote={CPI_TABLE_NOTE}
            csvFilename="cpi-annual-inflation.csv" csvRows={historyCsvRows(all, visible, meta)} />
          <ChartCard title="Quarterly CPI inflation" question={`${quarter}: prices changed ${rate(quarterly.value)} on the previous quarter.`}
            unit="percent change from the previous quarter" source={source}
            caveat="Quarterly change is not annualised and is not comparable with annual change."
            option={quarterlyInflationOption(visible, theme)} ariaLabel="Quarterly CPI inflation history" height={300}
            tableColumns={CPI_HISTORY_COLUMNS} tableNote={CPI_TABLE_NOTE}
            csvFilename="cpi-quarterly-inflation.csv" csvRows={historyCsvRows(all, visible, meta)} />
        </div>
      </section>

      <section aria-labelledby="cpi-trad" className="space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h2 id="cpi-trad" className="text-lg font-semibold">Tradables versus non-tradables</h2>
          <Segmented<Horizon> label="Rate" value={horizon} onChange={setHorizon} options={[{ value: "annual", label: "Annual" }, { value: "quarterly", label: "Quarterly" }]} />
        </div>
        <ChartCard title={`Tradables and non-tradables · ${horizon}`}
          question={`${quarter}: tradables ${latestRate("tradables", horizon === "annual" ? "annual_pct" : "quarterly_pct")}, non-tradables ${latestRate("non_tradables", horizon === "annual" ? "annual_pct" : "quarterly_pct")}. Which is rising faster?`}
          unit="percent" source={source}
          caveat="Tradables are exposed to foreign competition; non-tradables are not. Both are on one percentage axis, so gaps are in percentage points. Non-tradables is not core inflation."
          option={tradablesOption(rangeFilter(nsa("tradables").points, range), rangeFilter(nsa("non_tradables").points, range), horizon, theme)}
          ariaLabel="Tradables and non-tradables inflation" height={320}
          tableColumns={CPI_HISTORY_COLUMNS} tableNote={CPI_TABLE_NOTE}
          csvFilename={`cpi-tradables-${horizon}.csv`}
          csvRows={[...historyCsvRows(nsa("tradables"), rangeFilter(nsa("tradables").points, range), meta), ...historyCsvRows(nsa("non_tradables"), rangeFilter(nsa("non_tradables").points, range), meta)]} />
      </section>

      <section aria-labelledby="cpi-drivers" className="space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 id="cpi-drivers" className="text-lg font-semibold">Inflation drivers</h2>
            <p className="text-sm text-muted-foreground">Published percentage-point contributions to the headline change. A group's price change, its contribution and its share of the movement are different measures.</p>
          </div>
          <Segmented<"quarterly" | "annual"> label="Contribution horizon" value={contribution} onChange={setContribution}
            options={[{ value: "quarterly", label: "Quarterly contribution" }, { value: "annual", label: "Annual contribution" }]} />
        </div>
        {block.available ? (
          <ChartCard title={`Contribution to ${contribution} CPI change, by group`}
            question={`${quarter}: which groups drove the ${contribution} change${block.headline_pct == null ? "" : ` of ${rate(block.headline_pct)}`}?`}
            unit="percentage points" source={source} caveat={block.note}
            option={contributionOption(block, theme)} ariaLabel="CPI group contributions" height={380}
            tableColumns={CPI_CONTRIBUTION_COLUMNS} tableNote="Source and release metadata are included in the CSV download; source and capture time are shown above."
            csvFilename={`cpi-contributions-${contribution}.csv`} csvRows={contributionCsvRows(block, meta)} />
        ) : (
          <EmptyState title="Group contributions unavailable" body={block.note} />
        )}
      </section>

      <section aria-labelledby="cpi-explorer" className="space-y-3">
        <h2 id="cpi-explorer" className="text-lg font-semibold">Component explorer</h2>
        <Explorer data={data} range={range} source={source} />
      </section>

      <section aria-labelledby="cpi-analysis" className="rounded-md border p-4">
        <h2 id="cpi-analysis" className="text-lg font-semibold">Latest release analysis</h2>
        <div className="mt-3"><InsightList insights={a.executive_summary} /></div>
        <div className="mt-3"><InsightList insights={a.context} /></div>
        <p className="mt-3 text-sm text-muted-foreground">{a.revisions.note}</p>
        {data.underlying.length > 0 && (
          <div className="mt-4 overflow-x-auto">
            <table aria-label="Official underlying measures" className="w-full text-left text-sm">
              <caption className="mb-1 text-left text-xs text-muted-foreground">
                Official Stats NZ measures from the release workbook: quarterly change (%), {fullMonth(data.reference_period)} quarter.
              </caption>
              <tbody>
                <tr className="border-t"><th scope="row" className="py-1 pr-4 font-normal">All groups (for comparison)</th><td className="py-1 text-right tabular-nums">{formatNumber(quarterly.value, { decimals: 1 })}</td></tr>
                {data.underlying.map((u) => (
                  <tr key={u.key} className="border-t">
                    <th scope="row" className="py-1 pr-4 font-normal">{u.name.replace(", quarterly percentage change", "")}</th>
                    <td className="py-1 text-right tabular-nums">{formatNumber(u.points.at(-1)!.value, { decimals: 1 })}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Link className="mt-3 inline-block text-sm underline underline-offset-2" to={`/releases/${rel.id}`}>Full release analysis</Link>
      </section>

      <section aria-labelledby="cpi-method" className="space-y-2">
        <h2 id="cpi-method" className="text-lg font-semibold">Methodology</h2>
        <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
          {[...a.methodology.definitions, ...a.methodology.notes].map((t) => <li key={t}>{t}</li>)}
        </ul>
        <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm underline underline-offset-2">
          {rel.page_url && <a href={rel.page_url} target="_blank" rel="noreferrer">Stats NZ release page</a>}
          {LINKS.map(([label, href]) => <a key={href} href={href} target="_blank" rel="noreferrer">{label}</a>)}
        </div>
        <p className="text-xs text-muted-foreground">
          Latest observation {fullMonth(lastPoint.period)} · published {formatAklDate(rel.published_at)} · data captured {formatAklDateTime(a.vintage_captured_at)}. {isStaticMode() ? "This site is updated after each verified Stats NZ release." : "Automatic refresh follows the official release calendar."} <Link className="underline" to="/health">Data health</Link>
        </p>
      </section>
    </div>
  );
}

export default function Inflation() {
  useDocumentTitle(ROUTE_META["/inflation"].title);
  const q = useCpi();
  const notFound = q.error instanceof ApiError && q.error.status === 404;
  return (
    <div className="space-y-6">
      <header>
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Prices and inflation</p>
        <h1 className="text-xl font-semibold tracking-tight">Inflation</h1>
      </header>
      {notFound ? (isStaticMode()
        ? <EmptyState title="CPI data has not been published yet" body="This dashboard appears once a Stats NZ consumers price index release has been verified and published here." />
        : <EmptyState title="CPI data has not been ingested yet" body="The next scheduled refresh or a CPI backfill will populate this dashboard. Check Data health for ingestion status." />
      ) : <QueryBoundary query={q}>{(d) => <Dashboard data={d} />}</QueryBoundary>}
    </div>
  );
}
