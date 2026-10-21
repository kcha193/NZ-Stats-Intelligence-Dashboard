import { Link, useParams } from "react-router-dom";
import { useRelease } from "@/api/hooks";
import type { ReleaseAnalysis as Analysis } from "@/api/types";
import { InsightList } from "@/components/InsightList";
import { KpiCard } from "@/components/KpiCard";
import { EmptyState, QueryBoundary } from "@/components/QueryBoundary";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { formatAklDateTime, formatNumber, formatPercent, monthLabel } from "@/lib/format";
import { formatChange, formatMetricValue, isRate } from "@/lib/metric";

// CPI has annual and quarterly all-groups metrics under one series key, so the label disambiguates.
const metricKey = (m: { series_key: string; label: string }) => `${m.series_key}|${m.label}`;

function MetricsTable({ analysis }: { analysis: Analysis }) {
  return (
    <table className="w-full text-left text-sm">
      <caption className="sr-only">Headline metrics</caption>
      <thead>
        <tr className="border-b text-xs text-muted-foreground">
          <th scope="col" className="py-1 pr-3 font-medium">Measure</th>
          <th scope="col" className="py-1 pr-3 text-right font-medium">Value (unit)</th>
          <th scope="col" className="py-1 pr-3 font-medium">Period</th>
          <th scope="col" className="py-1 pr-3 text-right font-medium">Change vs prior period</th>
          <th scope="col" className="py-1 pr-3 text-right font-medium">Change vs year earlier</th>
          <th scope="col" className="py-1 font-medium">Status</th>
        </tr>
      </thead>
      <tbody>
        {analysis.headline_metrics.map((m) => (
          <tr key={metricKey(m)} className="border-b last:border-0">
            <th scope="row" className="py-1.5 pr-3 font-normal">{m.label}</th>
            <td className="py-1.5 pr-3 text-right font-medium">{formatMetricValue(m.value, m.unit)}{isRate(m.unit) ? null : <> <span className="text-xs text-muted-foreground">{m.unit}</span></>}{m.std_error !== null ? <span className="block text-xs text-muted-foreground">SE {formatNumber(m.std_error)}</span> : null}</td>
            <td className="py-1.5 pr-3">{m.period_label}</td>
            <td className="py-1.5 pr-3 text-right">{m.change_prior ? formatChange(m.change_prior, m.unit) : "n/a"}</td>
            <td className="py-1.5 pr-3 text-right">{m.change_year_ago ? formatChange(m.change_year_ago, m.unit) : "n/a"}</td>
            <td className="py-1.5"><StatusBadge status={m.status} /></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// CPI values are fractional: index points to 2 dp (as in the revision table), contributions to 3 dp,
// rates to 1 dp. Other categories publish whole numbers here.
const correctionDecimals = (seriesKey: string, unit: string) =>
  !seriesKey.startsWith("cpi.") ? 0 : unit === "index" ? 2 : unit === "percentage points" ? 3 : 1;

function Analysis({ analysis }: { analysis: Analysis }) {
  const rel = analysis.release;
  const indexRevisions = analysis.revisions.series_key.startsWith("cpi.");
  const revisionValue = (v: number) => formatNumber(v, { decimals: indexRevisions ? 2 : 0 });
  const cmp = analysis.previous_comparison;
  const rev = analysis.revisions;
  const corrections = analysis.corrections;
  return (
    <article className="space-y-6">
      <header>
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Release analysis</p>
        <h1 className="text-xl font-semibold tracking-tight">{rel.title}</h1>
        <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          Published {formatAklDateTime(rel.published_at)} <StatusBadge status={rel.status} />
        </p>
        {rel.headline && <p className="mt-2 text-sm">{rel.headline}</p>}
        <div className="mt-2 flex gap-2 print:hidden">
          <Button variant="outline" size="sm" onClick={() => window.print()}>Print or save as PDF</Button>
        </div>
      </header>

      <section aria-labelledby="exec"><h2 id="exec" className="text-lg font-semibold">Executive summary</h2><div className="mt-2"><InsightList insights={analysis.executive_summary} /></div></section>

      <section aria-labelledby="metrics">
        <h2 id="metrics" className="text-lg font-semibold">Headline metrics</h2>
        <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4 print:hidden">
          {analysis.headline_metrics.slice(0, 4).map((m) => (
            <KpiCard key={metricKey(m)} kpi={{ metric: m, release_id: rel.id, published_at: rel.published_at, source_url: rel.page_url }} />
          ))}
        </div>
        <div className="mt-3 overflow-x-auto"><MetricsTable analysis={analysis} /></div>
      </section>

      <section aria-labelledby="prev">
        <h2 id="prev" className="text-lg font-semibold">Since the previous release</h2>
        <p className="mt-1 text-sm text-muted-foreground">{cmp.note}</p>
        {cmp.available && (
          <div className="mt-2 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <caption className="sr-only">Change since the previous release, split into revision and new period</caption>
              <thead><tr className="border-b text-xs text-muted-foreground">
                <th scope="col" className="py-1 pr-3 font-medium">Measure</th>
                <th scope="col" className="py-1 pr-3 text-right font-medium">As published before</th>
                <th scope="col" className="py-1 pr-3 text-right font-medium">Revision of the previous period</th>
                <th scope="col" className="py-1 pr-3 text-right font-medium">Movement to new reference period</th>
                <th scope="col" className="py-1 text-right font-medium">Now</th>
              </tr></thead>
              <tbody>
                {cmp.decompositions.map((d) => {
                  const unit = analysis.headline_metrics.find((m) => m.series_key === d.series_key)?.unit ?? "";
                  const show = (v: number, signed = false) => isRate(unit) ? (signed ? `${formatNumber(v, { signed: true, decimals: 1 })} pp` : formatMetricValue(v, unit)) : formatNumber(v, { signed });
                  return (
                  <tr key={d.series_key} className="border-b last:border-0">
                    <th scope="row" className="py-1.5 pr-3 font-normal">{d.label}<span className="block text-xs text-muted-foreground">{monthLabel(d.previous_period)} → {monthLabel(d.new_period)}</span></th>
                    <td className="py-1.5 pr-3 text-right">{show(d.previous_published_value)}</td>
                    <td className="py-1.5 pr-3 text-right">{show(d.revision_component, true)} <span className="text-xs text-muted-foreground">(revision of {monthLabel(d.previous_period)})</span></td>
                    <td className="py-1.5 pr-3 text-right">{show(d.new_period_component, true)} <span className="text-xs text-muted-foreground">(new reference period {monthLabel(d.new_period)})</span></td>
                    <td className="py-1.5 text-right font-medium">{show(d.new_value)}</td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section aria-labelledby="ctx"><h2 id="ctx" className="text-lg font-semibold">Historical context</h2><div className="mt-2"><InsightList insights={analysis.context} /></div></section>

      <section aria-labelledby="rev">
        <h2 id="rev" className="text-lg font-semibold">Revision analysis</h2>
        <p className="mt-1 text-sm text-muted-foreground">{rev.note}</p>
        {rev.available && (
          <>
            <p className="mt-1 text-sm">{rev.n_revised} of {rev.n_common} overlapping periods were revised{rev.mean_abs !== null ? `; mean absolute revision ${formatNumber(rev.mean_abs, { decimals: indexRevisions ? 2 : 1 })} ${indexRevisions ? "index points" : (analysis.headline_metrics.find(m => m.series_key === rev.series_key)?.unit ?? '')}` : ""}.</p>
            {rev.largest.length > 0 && (
              <table className="mt-2 w-full text-left text-sm">
                <caption className="sr-only">Largest revisions to {analysis.headline_metrics.find(m => m.series_key === rev.series_key)?.label ?? rev.series_key}</caption>
                <thead><tr className="border-b text-xs text-muted-foreground">
                  <th scope="col" className="py-1 pr-3 font-medium">{indexRevisions ? "Quarter" : "Month"}</th><th scope="col" className="py-1 pr-3 text-right font-medium">Original</th>
                  <th scope="col" className="py-1 pr-3 text-right font-medium">Revised</th><th scope="col" className="py-1 pr-3 text-right font-medium">Revision</th>
                  <th scope="col" className="py-1 font-medium">Status change</th>
                </tr></thead>
                <tbody>
                  {rev.largest.map((r) => (
                    <tr key={r.period} className="border-b last:border-0">
                      <th scope="row" className="py-1.5 pr-3 font-normal">{monthLabel(r.period)}</th>
                      <td className="py-1.5 pr-3 text-right">{revisionValue(r.original)}</td>
                      <td className="py-1.5 pr-3 text-right">{revisionValue(r.revised)}</td>
                      <td className="py-1.5 pr-3 text-right">{formatNumber(r.absolute, { signed: true, decimals: indexRevisions ? 2 : 0 })} ({formatPercent(r.percent)})</td>
                      <td className="py-1.5">{r.original_status} → {r.revised_status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        )}
      </section>

      <section aria-labelledby="corrections">
        <h2 id="corrections" className="text-lg font-semibold">Corrections within this publication</h2>
        <p className="mt-1 text-sm text-muted-foreground">{corrections.note}</p>
        {corrections.available && (
          <>
            <p className="mt-1 text-xs text-muted-foreground">
              Earlier capture: {corrections.against_captured_at ? formatAklDateTime(corrections.against_captured_at) : "not recorded"}.
              Current capture: {formatAklDateTime(corrections.captured_at)}.
            </p>
            {corrections.series.map((s) => {
              const decimals = correctionDecimals(s.series_key, s.unit);
              return (
              <div key={s.series_key} className="mt-3">
                <h3 className="text-sm font-semibold">{s.label}: {s.n_changed} changed {s.n_changed === 1 ? "period" : "periods"}</h3>
                <div className="mt-1 overflow-x-auto" role="region" aria-label={`${s.label} corrections`} tabIndex={0}>
                  <table className="w-full text-left text-sm">
                    <caption className="sr-only">{s.label} corrections, values in {s.unit}</caption>
                    <thead><tr className="border-b text-xs text-muted-foreground">
                      <th scope="col" className="py-1 pr-3">Period</th>
                      <th scope="col" className="py-1 pr-3">Earlier ({s.unit})</th>
                      <th scope="col" className="py-1 pr-3">Current ({s.unit})</th>
                      <th scope="col" className="py-1 pr-3">Status change</th>
                      <th scope="col" className="py-1 pr-3">Standard error change</th>
                      <th scope="col" className="py-1">Source release month change</th>
                    </tr></thead>
                    <tbody>{s.changes.map((r) => (
                      <tr key={r.period} className="border-b last:border-0">
                        <th scope="row" className="py-1.5 pr-3 font-normal">{monthLabel(r.period)}</th>
                        <td className="pr-3">{r.original === null ? "Not present" : formatNumber(r.original, { decimals })}</td>
                        <td className="pr-3">{r.revised === null ? "Not present" : formatNumber(r.revised, { decimals })}</td>
                        <td className="pr-3">{r.original_status ?? "not present"} → {r.revised_status ?? "not present"}</td>
                        <td className="pr-3">SE {r.original_std_error === null ? "not supplied" : formatNumber(r.original_std_error)} → SE {r.revised_std_error === null ? "not supplied" : formatNumber(r.revised_std_error)}</td>
                        <td>{r.original_released_in ?? "not supplied"} → {r.revised_released_in ?? "not supplied"}</td>
                      </tr>
                    ))}</tbody>
                  </table>
                </div>
              </div>
              );
            })}
          </>
        )}
      </section>

      <section aria-labelledby="interp">
        <h2 id="interp" className="text-lg font-semibold">Interpretation</h2>
        <p className="mt-1 text-xs text-muted-foreground">Observations are arithmetic on published values. Inferences are labelled and never identify causes.</p>
        <div className="mt-2"><InsightList insights={analysis.interpretation} /></div>
      </section>

      <section aria-labelledby="src">
        <h2 id="src" className="text-lg font-semibold">Source and methodology</h2>
        {analysis.methodology.source_url && (
          <p className="mt-1 text-sm"><a className="underline underline-offset-2" href={analysis.methodology.source_url} target="_blank" rel="noreferrer">View the original Stats NZ publication</a></p>
        )}
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
          {[...analysis.methodology.definitions, ...analysis.methodology.notes].map((t, i) => <li key={i}>{t}</li>)}
        </ul>
        <p className="mt-2 text-xs text-muted-foreground">Analysis generated {formatAklDateTime(analysis.vintage_captured_at)} from this release's official data files. Source: Stats NZ (CC BY 4.0).</p>
      </section>
    </article>
  );
}

export default function ReleaseAnalysis() {
  const param = useParams().id ?? "";
  const parsed = /^\d+$/.test(param) ? Number(param) : Number.NaN;
  const valid = Number.isSafeInteger(parsed) && parsed > 0;
  const q = useRelease(valid ? parsed : Number.NaN); // NaN keeps the query disabled
  if (!valid) {
    return (
      <div className="space-y-3">
        <EmptyState title="That release was not found" body="The release address is not valid." />
        <p><Link className="text-sm underline underline-offset-2" to="/calendar">Back to the release calendar</Link></p>
      </div>
    );
  }
  return (
    <QueryBoundary query={q}>
      {(d) =>
        d.analysis ? (
          <Analysis analysis={d.analysis} />
        ) : (
          <div className="space-y-3">
            <h1 className="text-xl font-semibold tracking-tight">{d.release.title}</h1>
            <p className="text-sm text-muted-foreground">Published or scheduled {formatAklDateTime(d.release.published_at)}</p>
            <EmptyState title="No analysis is available for this release yet" body={d.unavailable_reason ?? "Unknown reason."} />
            {d.release.page_url && <a className="text-sm underline underline-offset-2" href={d.release.page_url} target="_blank" rel="noreferrer">Open the Stats NZ page</a>}
            <p><Link className="text-sm underline underline-offset-2" to="/calendar">Back to the release calendar</Link></p>
          </div>
        )
      }
    </QueryBoundary>
  );
}
