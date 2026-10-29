import { useId, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useForecastEvaluation, useForecastHistory } from "@/api/hooks";
import type { EvaluatedForecast, ForecastEvaluation, ForecastHistory, ForecastSeries, Ranking } from "@/api/types";
import { EChart } from "@/charts/EChart";
import { dateBounds, errorOption, revisionOption, type Outcome } from "@/charts/forecastTrack";
import { axisNote, forecastChartHeight, formatForecastValue, minSpanFor, valueRange } from "@/charts/forecasts";
import { useChartTheme } from "@/charts/theme";
import { ErrorState } from "@/components/QueryBoundary";
import { Skeleton } from "@/components/ui/skeleton";
import { formatCivilDate } from "@/lib/format";
import { matchedOutcomeFor, researchPath } from "@/lib/research";

const NAMES: Record<string, string> = { gdp: "GDP", cpi_inflation: "CPI inflation", ocr: "official cash rate", unemployment: "unemployment" };
const BANDS: Record<string, string> = { h0: "Same quarter or later", h1_2: "1 to 2 quarters ahead", h3_4: "3 to 4 quarters ahead", h5_8: "5 to 8 quarters ahead", h9: "9 or more quarters ahead" };
const pp = (v: number | null | undefined) => (v === null || v === undefined ? "" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(2).replace(/0$/, "")}`);
const Empty = ({ children }: { children: React.ReactNode }) => <p className="mt-4 rounded-md border border-dashed p-5 text-sm text-muted-foreground">{children}</p>;

const targetLabel = (s: ForecastSeries) => `${s.basis_label}, ${s.horizon_label}${s.kind === "scenario" ? `, scenario: ${s.scenario}` : ""}`;

/** The first-published official outcome for a CPI series, when the evaluation matched one of its forecasts. Never the latest quarter. */
function outcomeFor(series: ForecastSeries, evaluation: ForecastEvaluation | null | undefined): Outcome | null {
  const row = evaluation ? matchedOutcomeFor(series, evaluation.evaluated) : null;
  return row?.first ? { value: row.first.value, label: row.first.first_release ? "First published" : "Earliest stored" } : null;
}

function History({ data, evaluation }: { data: ForecastHistory; evaluation?: ForecastEvaluation | null }) {
  const theme = useChartTheme();
  const selectId = useId();
  const targets = useMemo(() => {
    const byKey = new Map<string, ForecastSeries[]>();
    for (const s of data.series) byKey.set(s.target_key, [...(byKey.get(s.target_key) ?? []), s]);
    return [...byKey.entries()];
  }, [data]);
  const richest = targets.reduce<string>((best, [key, list]) => {
    const n = list.reduce((a, s) => a + s.vintages.length, 0);
    const b = targets.find(([k]) => k === best)?.[1].reduce((a, s) => a + s.vintages.length, 0) ?? -1;
    return n > b ? key : best;
  }, targets[0]?.[0] ?? "");
  const [chosen, setChosen] = useState("");
  const key = targets.some(([k]) => k === chosen) ? chosen : richest;
  const panels = targets.find(([k]) => k === key)?.[1] ?? [];
  const outcomes = panels.map((s) => outcomeFor(s, evaluation));
  const outcomeLabels = [...new Set(outcomes.flatMap((o) => (o ? [o.label.toLowerCase()] : [])))];
  const unit = panels[0]?.unit_label ?? "%";
  const values = [...panels.flatMap((s) => s.vintages.map((v) => v.value)), ...outcomes.flatMap((o) => (o ? [o.value] : []))];
  const range = valueRange(values, minSpanFor(unit, values));
  const dates = dateBounds(panels);
  const note = axisNote(range, unit);
  if (targets.length === 0) return <Empty>No comparable forecast for this indicator is published here yet.</Empty>;
  return (
    <div className="mt-4">
      <div className="flex flex-col gap-1.5">
        <label htmlFor={selectId} className="text-xs font-medium text-muted-foreground">Target</label>
        <select id={selectId} value={key} onChange={(e) => setChosen(e.target.value)} className="h-9 max-w-full rounded-md border bg-background px-2.5 text-sm">
          {targets.map(([k, list]) => <option key={k} value={k}>{targetLabel(list[0])}</option>)}
        </select>
      </div>
      <div className="mt-4 grid gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-3">
        {panels.map((s, i) => (
          <figure key={s.key} aria-label={`${s.institution.name}: ${targetLabel(s)}`} className="border-t pt-3">
            <figcaption className="text-sm font-medium">{s.institution.name}</figcaption>
            <p className="text-xs text-muted-foreground">
              {s.vintages.length} vintage{s.vintages.length === 1 ? "" : "s"}; {s.n_revisions === 0 ? "no revision" : `${s.n_revisions} revision${s.n_revisions === 1 ? "" : "s"}, ${pp(s.total_revision)} points in all`}
            </p>
            <EChart option={revisionOption(s, theme, range, dates, outcomes[i])} height={180}
              ariaLabel={`${s.institution.name}, ${targetLabel(s)}: ${s.vintages.map((v) => `${formatForecastValue(v.value, unit)} published ${formatCivilDate(v.published_on)}`).join("; ")}.`} />
          </figure>
        ))}
      </div>
      <ul aria-label="Legend" className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground">
        <li className="inline-flex items-center gap-1.5"><span aria-hidden className="inline-block size-2.5 rounded-full bg-[var(--chart-1)]" />Forecast, by publication date</li>
        {outcomeLabels.length > 0 && <li className="inline-flex items-center gap-1.5"><span aria-hidden className="inline-block h-0.5 w-3 bg-[var(--chart-2)]" />Official outcome ({outcomeLabels.join(" or ")})</li>}
      </ul>
      {note && <p className="mt-1 text-xs text-muted-foreground">{note}</p>}
      <details className="mt-3 text-sm">
        <summary className="cursor-pointer text-xs font-medium text-accent-ink">Table view</summary>
        <div className="mt-2 overflow-x-auto">
          <table className="w-full min-w-[34rem] text-left text-sm">
            <caption className="sr-only">Vintages of {panels[0] ? targetLabel(panels[0]) : ""} by institution</caption>
            <thead className="text-xs text-muted-foreground"><tr>
              <th scope="col" className="py-1.5 pr-3 font-medium">Institution</th><th scope="col" className="py-1.5 pr-3 font-medium">Published</th>
              <th scope="col" className="py-1.5 pr-3 font-medium">Forecast</th><th scope="col" className="py-1.5 pr-3 font-medium">Change</th>
              <th scope="col" className="py-1.5 font-medium">Document</th>
            </tr></thead>
            <tbody className="divide-y">
              {panels.flatMap((s) => s.vintages.map((v) => (
                <tr key={`${s.key}-${v.summary_id}`}>
                  <th scope="row" className="py-2 pr-3 font-medium">{s.institution.name}</th>
                  <td className="py-2 pr-3">{formatCivilDate(v.published_on)}</td>
                  <td className="py-2 pr-3 tabular-nums">{formatForecastValue(v.value, unit)}</td>
                  <td className="py-2 pr-3 tabular-nums">{v.revision === null || v.revision === undefined ? "First" : v.revision === 0 ? "Unchanged" : pp(v.revision)}</td>
                  <td className="py-2"><Link className="hover:underline" to={researchPath(v.summary_id)}>{v.document_title}</Link></td>
                </tr>
              )))}
            </tbody>
          </table>
        </div>
      </details>
      {data.measure_changes.length > 0 && (
        <div className="mt-5">
          <h4 className="text-sm font-semibold">Changes of measure (not revisions)</h4>
          <ul className="mt-2 space-y-1.5 text-sm">
            {data.measure_changes.map((m) => (
              <li key={`${m.institution.key}-${m.to_summary_id}-${m.horizon_key}`} className="max-w-[72ch]">
                {m.institution.name}, {m.horizon_label}: {m.from_basis_label.toLowerCase()} ({formatCivilDate(m.from_published_on)}), then {m.to_basis_label.toLowerCase()} ({formatCivilDate(m.to_published_on)}). Different statistics, so the change is not a revision.
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function RankingView({ r }: { r: Ranking }) {
  if (!r.available) return <p className="mt-2 text-sm text-muted-foreground">No ranking ({r.measure_label.toLowerCase()}): {r.reason}</p>;
  return (
    <div className="mt-2 overflow-x-auto">
      <table className="w-full min-w-[28rem] text-left text-sm">
        <caption className="text-left text-xs text-muted-foreground">{r.measure_label}: {r.reason}</caption>
        <thead className="text-xs text-muted-foreground"><tr><th scope="col" className="py-1.5 pr-3 font-medium">Institution</th><th scope="col" className="py-1.5 pr-3 font-medium">Targets</th><th scope="col" className="py-1.5 pr-3 font-medium">MAE</th><th scope="col" className="py-1.5 pr-3 font-medium">RMSE</th><th scope="col" className="py-1.5 font-medium">Mean error</th></tr></thead>
        <tbody className="divide-y">{r.entries.map((e) => (
          <tr key={e.institution.key}><th scope="row" className="py-2 pr-3 font-medium">{e.institution.name}</th><td className="py-2 pr-3 tabular-nums">{e.n}</td><td className="py-2 pr-3 tabular-nums">{e.mae.toFixed(2)}</td><td className="py-2 pr-3 tabular-nums">{e.rmse.toFixed(2)}</td><td className="py-2 tabular-nums">{pp(e.mean_error)}</td></tr>
        ))}</tbody>
      </table>
    </div>
  );
}

/** The dashboard with each indicator's official Stats NZ figures, for outcomes the Outlook checks forecasts against. */
const OFFICIAL_PAGES: Record<string, string> = { cpi_inflation: "/inflation", gdp: "/gdp", unemployment: "/labour-market" };

function Evaluation({ data, indicator }: { data: ForecastEvaluation; indicator: string }) {
  const theme = useChartTheme();
  const name = NAMES[indicator] ?? indicator.replace(/_/g, " ");
  if (data.state === "no_official_series") {
    return <Empty>{data.unavailable_reason ?? `No official ${name} series is ingested here, so these forecasts are not checked against outcomes.`} Nothing is estimated in its place.</Empty>;
  }
  if (data.state === "nothing_to_evaluate") return <Empty>No {name} forecast is published here yet, so there is nothing to check.</Empty>;
  const matched = data.evaluated.filter((e) => e.status === "matched") as EvaluatedForecast[];
  const scored = matched.filter((e) => e.first?.first_release && e.error_first != null);
  const pending = data.evaluated.length - matched.length;
  const names = new Set(matched.map((e) => e.forecast.institution.key));
  return (
    <div className="mt-4">
      <p className="max-w-[72ch] text-sm text-muted-foreground">
        {matched.length} forecast{matched.length === 1 ? "" : "s"} matched to an official outcome, {pending} waiting for their quarter&rsquo;s release,
        {" "}{data.excluded.length} not evaluated. {data.actuals_as_of ? `Outcomes as of ${data.actuals_as_of}, published ${formatCivilDate(data.actuals_released_on)}` : indicator === "cpi_inflation" ? "No CPI release is stored yet" : `No official ${name} release is stored yet`}
        {data.vintages_from ? `; forecasts published ${formatCivilDate(data.vintages_from)} to ${formatCivilDate(data.vintages_to)}` : ""}.
      </p>
      {OFFICIAL_PAGES[data.indicator] && (
        <p className="mt-1 text-sm"><Link className="underline underline-offset-2" to={OFFICIAL_PAGES[data.indicator]}>Official {NAMES[data.indicator] ?? data.indicator} figures</Link></p>
      )}
      {matched.length === 0 ? <Empty>No forecast has an official outcome yet.</Empty> : scored.length === 0 ? (
        <Empty>First-published outcomes are unverified. Stored outcomes remain available below; first-published errors and accuracy statistics are not scored.</Empty>
      ) : (
        <figure aria-labelledby="errors-title" className="mt-4">
          <figcaption id="errors-title" className="text-sm font-medium">Forecast minus first-published outcome</figcaption>
          <EChart option={errorOption(scored, theme)} height={forecastChartHeight(names.size)}
            ariaLabel={`Forecast errors: ${scored.map((e) => `${e.forecast.institution.name} ${e.target_label} ${pp(e.error_first)} points`).join("; ")}.`} />
          <p className="text-xs text-muted-foreground">Right of zero: the forecast was too high. Left: too low.</p>
        </figure>
      )}
      {data.summaries.length > 0 && (
        <div className="mt-5 overflow-x-auto">
          <table className="w-full min-w-[34rem] text-left text-sm">
            <caption className="text-left text-sm font-semibold">Accuracy by institution and horizon</caption>
            <thead className="text-xs text-muted-foreground"><tr><th scope="col" className="py-1.5 pr-3 font-medium">Institution</th><th scope="col" className="py-1.5 pr-3 font-medium">Measure</th><th scope="col" className="py-1.5 pr-3 font-medium">Horizon</th><th scope="col" className="py-1.5 pr-3 font-medium">Outcomes</th><th scope="col" className="py-1.5 pr-3 font-medium">MAE</th><th scope="col" className="py-1.5 font-medium">RMSE</th></tr></thead>
            <tbody className="divide-y">{data.summaries.map((s) => (
              <tr key={`${s.institution.key}-${s.measure}-${s.band}`}>
                <th scope="row" className="py-2 pr-3 font-medium">{s.institution.name}</th><td className="py-2 pr-3">{s.measure_label}</td><td className="py-2 pr-3">{BANDS[s.band]}</td>
                <td className="py-2 pr-3 tabular-nums">{s.n}</td>
                {s.sufficient ? <><td className="py-2 pr-3 tabular-nums">{s.mae?.toFixed(2)}</td><td className="py-2 tabular-nums">{s.rmse?.toFixed(2)}</td></>
                  : <td colSpan={2} className="py-2 text-muted-foreground">Too few outcomes ({s.n} of {data.min_for_summary} needed)</td>}
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
      <div className="mt-5">
        <h4 className="text-sm font-semibold">Ranking</h4>
        {data.rankings.length === 0 ? <p className="mt-2 text-sm text-muted-foreground">No ranking: no forecast has an outcome yet.</p> : data.rankings.map((r) => <RankingView key={r.measure} r={r} />)}
      </div>
      {matched.length > 0 && (
        <details className="mt-4 text-sm">
          <summary className="cursor-pointer text-xs font-medium text-accent-ink">Matched forecasts ({matched.length})</summary>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full min-w-[44rem] text-left text-sm">
              <caption className="sr-only">Forecasts matched to official outcomes</caption>
              <thead className="text-xs text-muted-foreground"><tr><th scope="col" className="py-1.5 pr-3 font-medium">Institution</th><th scope="col" className="py-1.5 pr-3 font-medium">Target</th><th scope="col" className="py-1.5 pr-3 font-medium">Published</th><th scope="col" className="py-1.5 pr-3 font-medium">Forecast</th><th scope="col" className="py-1.5 pr-3 font-medium">Stored baseline</th><th scope="col" className="py-1.5 pr-3 font-medium">Latest</th><th scope="col" className="py-1.5 font-medium">Error</th></tr></thead>
              <tbody className="divide-y">{matched.map((e) => (
                <tr key={`${e.forecast.summary_id}-${e.measure}-${e.target_quarter}`}>
                  <th scope="row" className="py-2 pr-3 font-medium">{e.forecast.institution.name}</th>
                  <td className="py-2 pr-3">{e.target_label}, {e.measure_label.toLowerCase()}</td>
                  <td className="py-2 pr-3">{formatCivilDate(e.forecast.published_on)}</td>
                  <td className="py-2 pr-3 tabular-nums">{formatForecastValue(e.forecast.value ?? 0, "%")}</td>
                  <td className="py-2 pr-3 tabular-nums">{formatForecastValue(e.first?.value ?? 0, "%")}{e.first && !e.first.first_release ? " (earliest stored)" : ""}</td>
                  <td className="py-2 pr-3 tabular-nums">{formatForecastValue(e.latest?.value ?? 0, "%")}{e.outcome_revision ? ` (revised ${pp(e.outcome_revision)})` : ""}</td>
                  <td className="py-2 tabular-nums">{e.error_first == null ? "Not scored" : pp(e.error_first)}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </details>
      )}
      {data.excluded.length > 0 && (
        <details className="mt-3 text-sm">
          <summary className="cursor-pointer text-xs font-medium text-accent-ink">Not evaluated ({data.excluded.length})</summary>
          <ul className="mt-2 divide-y">{data.excluded.map((x, i) => (
            <li key={i} className="py-2"><span className="font-medium">{x.forecast.institution.name}</span>: {x.forecast.indicator_label}, {x.forecast.horizon}. <span className="text-muted-foreground">{x.reason}</span></li>
          ))}</ul>
        </details>
      )}
      <p className="mt-4 max-w-[72ch] text-xs text-muted-foreground">{data.note}</p>
    </div>
  );
}

/** Section D: how forecasts changed over successive publications, and how the ones that can be checked turned out. */
export function ForecastTrack({ indicator }: { indicator: string }) {
  const history = useForecastHistory(indicator);
  const evaluation = useForecastEvaluation(indicator);
  const name = NAMES[indicator] ?? indicator.replace(/_/g, " ");
  const heading = (
    <>
      <h2 id="track-title" className="type-section">Forecast history and track record</h2>
      <p className="mt-1.5 max-w-[65ch] text-sm text-muted-foreground">
        How each institution&rsquo;s {name} forecasts changed from one publication to the next, and, where an official series exists, how they compared with the outcome.
      </p>
    </>
  );
  if (history.isLoading || evaluation.isLoading) return <section aria-labelledby="track-title">{heading}<Skeleton className="mt-5 h-48 w-full" /></section>;
  const failed = history.isError ? history : evaluation.isError ? evaluation : null;
  if (failed) return <section aria-labelledby="track-title">{heading}<div className="mt-5"><ErrorState error={failed.error} onRetry={() => void failed.refetch()} /></div></section>;
  if (!history.data) return null; // research not published: the comparison above already explains why
  return (
    <section aria-labelledby="track-title">
      {heading}
      <h3 className="type-card mt-6">How forecasts changed</h3>
      <History data={history.data} evaluation={evaluation.data} />
      <h3 className="type-card mt-10">Forecasts against outcomes</h3>
      {evaluation.data ? <Evaluation data={evaluation.data} indicator={indicator} /> : <Empty>Not available.</Empty>}
      <details className="mt-6 max-w-[72ch] text-sm">
        <summary className="cursor-pointer text-xs font-medium text-accent-ink">How forecasts are checked</summary>
        <ul className="mt-2 list-disc space-y-1.5 pl-5 text-muted-foreground">
          <li>CPI, GDP and the unemployment rate have official Stats NZ series here; the Official Cash Rate does not (no approved source). A forecast is checked only on the measure it states and only for the quarter it names: for CPI, annual change, annual average change, or quarterly change with its seasonal adjustment stated; for GDP, real quarterly growth, annual average growth, or the seasonally adjusted annual change of a quarter; for unemployment, the seasonally adjusted rate for a quarter. GDP growth and the unemployment rate are Stats NZ&rsquo;s seasonally adjusted headline series.</li>
          <li>The outcome is the first published figure for that quarter, with the latest figure beside it. A forecast published on or after that release is not checked.</li>
          <li>Scenarios, ambiguous wording and calendar or fiscal-year horizons are not checked, and each says why.</li>
          <li>Averages need at least {evaluation.data?.min_for_summary ?? 4} distinct target quarters in a horizon band, each scored on the institution&rsquo;s latest forecast in that band. A ranking needs at least {evaluation.data?.min_for_ranking ?? 8} targets that every ranked institution forecast at the same horizon. No significance test is run.</li>
        </ul>
      </details>
    </section>
  );
}
