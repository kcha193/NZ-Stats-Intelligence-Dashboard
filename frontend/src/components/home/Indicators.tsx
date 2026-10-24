import { useId, useState } from "react";
import { Link } from "react-router-dom";
import type { Kpi } from "@/api/types";
import { Delta } from "@/components/KpiCard";
import { StatusBadge } from "@/components/StatusBadge";
import { groupIndicators } from "@/lib/indicators";
import { formatAklDate, formatNumber } from "@/lib/format";
import { formatMetricValue, isRate } from "@/lib/metric";
import { TOPICS } from "@/stories/topics";

function IndicatorRow({ kpi }: { kpi: Kpi }) {
  const m = kpi.metric;
  return (
    <li>
      <article aria-label={m.label} className="grid gap-x-6 gap-y-1 py-3 sm:grid-cols-[minmax(0,1.3fr)_minmax(7rem,auto)_minmax(0,1.5fr)] sm:items-baseline">
        <div className="min-w-0">
          <p className="text-sm font-medium">{m.label}</p>
          <p className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            {m.period_label} <StatusBadge status={m.status} />
          </p>
        </div>
        <p className="flex items-baseline gap-1.5 sm:justify-end">
          <span className="text-2xl font-semibold tabular-nums tracking-tight">{isRate(m.unit) ? formatMetricValue(m.value, m.unit) : formatNumber(m.value)}</span>
          {!isRate(m.unit) && <span className="text-xs text-muted-foreground">{m.unit}</span>}
        </p>
        <div className="space-y-0.5">
          <Delta change={m.change_year_ago} unit={m.unit} />
          <Delta change={m.change_prior} unit={m.unit} />
          <p className="text-xs text-muted-foreground">
            Published {formatAklDate(kpi.published_at)}
            {kpi.source_url && <>{" · "}<a className="underline underline-offset-2" href={kpi.source_url} target="_blank" rel="noreferrer">Source</a></>}
          </p>
        </div>
      </article>
    </li>
  );
}

/**
 * Every indicator, grouped by topic. Collapsed, each topic shows its first indicator; one control reveals the rest.
 * Nothing is removed: the control only changes how much is visible at once.
 */
export function Indicators({ kpis }: { kpis: Kpi[] }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const groups = groupIndicators(kpis);
  const hidden = groups.reduce((n, g) => n + g.kpis.length - 1, 0);
  return (
    <section aria-labelledby="key-indicators">
      <h2 id="key-indicators" className="type-section">Key indicators</h2>
      <p className="mt-1.5 max-w-[65ch] text-sm text-muted-foreground">
        The latest value of every indicator on this site, with its period, status, comparisons and source.
      </p>
      <div id={id} className="mt-5 grid gap-x-10 gap-y-6">
        {groups.map((g) => (
          <div key={g.key}>
            <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-rule-strong/30 pb-2">
              <h3 className="flex items-center gap-2 font-display text-base font-semibold tracking-tight">
                {g.key !== "other" && <span aria-hidden className={`cat-rule ${TOPICS[g.key].tone}`} />}
                {g.title}
              </h3>
              {g.dashboard && <Link className="text-sm font-medium text-accent-ink underline-offset-4 hover:underline" to={g.dashboard.to}>{g.dashboard.label}</Link>}
            </div>
            <ul className="divide-y">
              {(open ? g.kpis : g.kpis.slice(0, 1)).map((k) => <IndicatorRow key={k.metric.series_key} kpi={k} />)}
            </ul>
          </div>
        ))}
      </div>
      {hidden > 0 && (
        <button
          type="button" aria-expanded={open} aria-controls={id} onClick={() => setOpen((o) => !o)}
          className="mt-5 rounded-md border px-4 py-2 text-sm font-medium hover:bg-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-ink"
        >
          {open ? "Show headline indicators only" : `Explore all ${kpis.length} indicators`}
        </button>
      )}
    </section>
  );
}
