import { useId, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useForecasts } from "@/api/hooks";
import type { ForecastComparison as Comparison, ForecastGroup, Kpi } from "@/api/types";
import { EChart } from "@/charts/EChart";
import { forecastChartHeight, forecastOption, formatForecastValue } from "@/charts/forecasts";
import { useChartTheme } from "@/charts/theme";
import { ErrorState } from "@/components/QueryBoundary";
import { Segmented } from "@/components/Segmented";
import { Skeleton } from "@/components/ui/skeleton";
import { formatAklDate, formatCivilDate } from "@/lib/format";
import { observationFor, researchPath } from "@/lib/research";

/** The indicators the comparison always offers, then any others that published forecasts mention. */
const CORE = [
  { value: "gdp", label: "GDP" }, { value: "cpi_inflation", label: "CPI" },
  { value: "ocr", label: "OCR" }, { value: "unemployment", label: "Unemployment" },
];
type Kind = "central" | "scenario";

function GroupView({ group, cpi }: { group: ForecastGroup; cpi?: Kpi }) {
  const theme = useChartTheme();
  const obs = useMemo(() => observationFor(group, cpi), [group, cpi]);
  const option = useMemo(() => forecastOption(group, theme, obs), [group, theme, obs]);
  const titleId = useId();
  const kind = group.kind === "scenario" ? `Scenario: ${group.scenario}` : "Central forecasts";
  const describe = group.rows.map((r) => `${r.forecast.institution.name} ${formatForecastValue(r.forecast.value ?? 0, group.unit_label)}`).join(", ");
  return (
    <figure aria-labelledby={titleId} className="border-t pt-5">
      <figcaption>
        <h3 id={titleId} className="type-card">{group.indicator_name}, {group.horizon_label}</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          {group.basis_label}, in {group.unit_label === "%" ? "percent" : group.unit_label}. {kind}. {group.note}
        </p>
      </figcaption>
      <EChart option={option} height={forecastChartHeight(group.rows.length)} ariaLabel={`${group.indicator_name}, ${group.horizon_label}, ${kind}: ${describe}.`} />
      <ul aria-label="Legend" className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground">
        <li className="inline-flex items-center gap-1.5">
          <span aria-hidden className={`inline-block size-2.5 rounded-full border-2 border-[var(--chart-1)] ${group.kind === "scenario" ? "" : "bg-[var(--chart-1)]"}`} />
          {group.kind === "scenario" ? "Scenario (hollow)" : "Central forecast"}
        </li>
        {obs && (
          <li className="inline-flex items-center gap-1.5">
            <span aria-hidden className="inline-block h-3 w-0.5 bg-[var(--chart-2)]" />
            Latest official observation
          </li>
        )}
      </ul>
      {obs && (
        <p className="mt-2 max-w-[72ch] text-xs leading-relaxed text-muted-foreground">
          Latest official observation: Stats NZ annual CPI inflation {formatForecastValue(obs.value, "%")} for the{" "}
          {obs.period.charAt(0).toLowerCase() + obs.period.slice(1)}, published {formatAklDate(obs.publishedAt)}. It is
          an observation of an earlier period, not a forecast, and it does not test any institution&rsquo;s explanation.
        </p>
      )}
      <details className="mt-3 text-sm">
        <summary className="cursor-pointer text-xs font-medium text-accent-ink">Table view</summary>
        <div className="mt-2 overflow-x-auto">
          <table className="w-full min-w-[34rem] text-left text-sm">
            <caption className="sr-only">{group.indicator_name}, {group.horizon_label}: forecasts by institution</caption>
            <thead className="text-xs text-muted-foreground">
              <tr><th scope="col" className="py-1.5 pr-3 font-medium">Institution</th><th scope="col" className="py-1.5 pr-3 font-medium">Forecast</th><th scope="col" className="py-1.5 pr-3 font-medium">As stated</th><th scope="col" className="py-1.5 pr-3 font-medium">Vintage</th><th scope="col" className="py-1.5 font-medium">Earlier vintages</th></tr>
            </thead>
            <tbody className="divide-y">
              {group.rows.map((r) => (
                <tr key={r.forecast.institution.key}>
                  <th scope="row" className="py-2 pr-3 font-medium"><Link className="hover:underline" to={researchPath(r.forecast.summary_id)}>{r.forecast.institution.name}</Link></th>
                  <td className="py-2 pr-3 tabular-nums">{formatForecastValue(r.forecast.value ?? 0, group.unit_label)}</td>
                  <td className="py-2 pr-3 text-muted-foreground">{r.forecast.indicator_label}, {r.forecast.horizon}{r.forecast.qualification ? `. ${r.forecast.qualification}` : ""}</td>
                  <td className="py-2 pr-3">{formatCivilDate(r.forecast.published_on)}</td>
                  <td className="py-2 text-muted-foreground">
                    {r.earlier_vintages.length === 0 ? "None" : r.earlier_vintages.map((e) => `${formatForecastValue(e.value ?? 0, group.unit_label)} (${formatCivilDate(e.published_on)})`).join(", ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}

function NotCompared({ data, indicator }: { data: Comparison; indicator: string }) {
  const list = data.excluded.filter((e) => e.forecast.indicator === indicator);
  if (list.length === 0) return null;
  return (
    <details className="mt-6 border-t pt-4 text-sm">
      <summary className="cursor-pointer font-medium">Not compared ({list.length})</summary>
      <p className="mt-2 max-w-[70ch] text-muted-foreground">These forecasts are published, but they cannot be lined up with others on a like-for-like basis.</p>
      <ul className="mt-3 divide-y">
        {list.map((e, i) => (
          <li key={i} className="py-2.5">
            <p><span className="font-medium">{e.forecast.institution.name}</span>: {e.forecast.indicator_label}, {e.forecast.horizon}
              {e.forecast.value !== null && e.forecast.value !== undefined ? `, ${e.forecast.value}${e.forecast.unit ? ` ${e.forecast.unit.replace(/_/g, " ")}` : ""}` : `, ${e.forecast.direction}`}</p>
            <p className="text-muted-foreground">{e.reason}</p>
          </li>
        ))}
      </ul>
    </details>
  );
}

/** Section C: explicit institutional forecasts, compared only like with like. */
export function ForecastComparison({ cpi }: { cpi?: Kpi }) {
  const [indicator, setIndicator] = useState("cpi_inflation");
  const [kind, setKind] = useState<Kind>("central");
  const [horizon, setHorizon] = useState("");
  const [chosen, setChosen] = useState<string[]>([]);
  const query = useForecasts({ indicator, institution: chosen.length ? chosen.join(",") : undefined });
  const horizonId = useId();

  const heading = (
    <>
      <h2 id="forecasts-title" className="type-section">Forecast comparison</h2>
      <p className="mt-1.5 max-w-[65ch] text-sm text-muted-foreground">
        Explicit forecasts from published research. Two forecasts share a chart only when the indicator, unit, statistical
        basis and horizon all match.
      </p>
    </>
  );
  if (query.isLoading) return <section aria-labelledby="forecasts-title">{heading}<Skeleton className="mt-5 h-48 w-full" /></section>;
  if (query.isError) return <section aria-labelledby="forecasts-title">{heading}<div className="mt-5"><ErrorState error={query.error} onRetry={() => void query.refetch()} /></div></section>;
  const d = query.data;
  if (!d || d.indicators.length === 0) {
    return (
      <section aria-labelledby="forecasts-title">
        {heading}
        <p className="mt-5 rounded-md border border-dashed p-5 text-sm text-muted-foreground">
          No forecasts are published here yet. They appear once research that states them passes the checks and is approved for publication.
        </p>
      </section>
    );
  }
  const options = [...CORE, ...d.indicators.filter((f) => !CORE.some((c) => c.value === f.value)).map((f) => ({ value: f.value, label: f.label }))];
  const horizons = [...new Map(d.groups.filter((g) => g.indicator === indicator).map((g) => [g.horizon_key, g.horizon_label])).entries()];
  const ofIndicator = d.groups.filter((g) => g.indicator === indicator); // the API filters too; this also covers placeholder data
  const groups = ofIndicator.filter((g) => g.kind === kind && (!horizon || g.horizon_key === horizon));
  const name = options.find((o) => o.value === indicator)?.label ?? indicator;
  const all = d.institutions.map((f) => f.value);
  // An empty selection means every institution; at least one always stays selected.
  const toggle = (key: string) => {
    const current = chosen.length ? chosen : all;
    const next = current.includes(key) ? current.filter((k) => k !== key) : [...current, key];
    if (next.length > 0) setChosen(next.length === all.length ? [] : next);
  };

  return (
    <section aria-labelledby="forecasts-title">
      {heading}
      <div className="mt-5 flex flex-wrap items-end gap-x-6 gap-y-3">
        <div className="max-w-full overflow-x-auto"><Segmented label="Indicator" value={indicator} onChange={(v) => { setIndicator(v); setHorizon(""); }} options={options} /></div>
        <Segmented<Kind> label="Forecast kind" value={kind} onChange={setKind} options={[{ value: "central", label: "Central" }, { value: "scenario", label: "Scenarios" }]} />
        <div className="flex flex-col gap-1.5">
          <label htmlFor={horizonId} className="text-xs font-medium text-muted-foreground">Horizon</label>
          <select id={horizonId} value={horizon} onChange={(e) => setHorizon(e.target.value)} className="h-9 rounded-md border bg-background px-2.5 text-sm">
            <option value="">All horizons</option>
            {horizons.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
          </select>
        </div>
      </div>
      <fieldset className="mt-4">
        <legend className="text-xs font-medium text-muted-foreground">Institutions</legend>
        <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1.5">
          {d.institutions.map((f) => (
            <label key={f.value} className="inline-flex items-center gap-2 text-sm">
              <input type="checkbox" checked={chosen.length === 0 || chosen.includes(f.value)} onChange={() => toggle(f.value)} className="size-4 accent-[var(--accent-ink)]" />
              {f.label}
            </label>
          ))}
        </div>
      </fieldset>
      <div className={`mt-6 space-y-8 ${query.isPlaceholderData ? "opacity-60" : ""}`}>
        {groups.length === 0 ? (
          <p className="rounded-md border border-dashed p-5 text-sm text-muted-foreground">
            No {kind === "scenario" ? "scenario" : "central"} {name} forecasts can be compared{horizon ? " for this horizon" : ""} with the current selection.
          </p>
        ) : groups.map((g) => <GroupView key={g.key} group={g} cpi={cpi} />)}
      </div>
      <NotCompared data={d} indicator={indicator} />
      <p className="mt-6 max-w-[72ch] text-xs text-muted-foreground">{d.note}</p>
    </section>
  );
}
