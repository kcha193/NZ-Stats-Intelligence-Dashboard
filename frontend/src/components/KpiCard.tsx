import type { ChangeOut, Kpi } from "@/api/types";
import { formatAklDate, formatNumber, formatPercent } from "@/lib/format";
import { formatMetricValue, isRate } from "@/lib/metric";
import { StatusBadge } from "./StatusBadge";

export function Delta({ change, unit }: { change: ChangeOut | null | undefined; unit: string }) {
  if (!change) return null;
  if (isRate(unit)) {
    return (
      <p className="text-xs text-muted-foreground">
        <span className="font-medium text-foreground">{formatNumber(change.absolute, { signed: true, decimals: 1 })}</span>{" "}
        percentage points {change.label}
      </p>
    );
  }
  return (
    <p className="text-xs text-muted-foreground">
      <span className="font-medium text-foreground">{formatNumber(change.absolute, { signed: true })}</span>{" "}
      {unit} ({formatPercent(change.percent)}) {change.label}
    </p>
  );
}

export function KpiCard({ kpi }: { kpi: Kpi }) {
  const m = kpi.metric;
  return (
    <article className="rounded-md border bg-card p-3" aria-label={m.label}>
      <p className="text-xs font-medium text-muted-foreground">{m.label}</p>
      <p className="mt-1 flex items-baseline gap-2">
        <span className="text-3xl font-semibold leading-none tracking-tight">{isRate(m.unit) ? formatMetricValue(m.value, m.unit) : formatNumber(m.value)}</span>
        {!isRate(m.unit) && <span className="text-xs text-muted-foreground">{m.unit}</span>}
      </p>
      <p className="mt-1 flex items-center gap-2 text-xs">
        <span>{m.period_label}</span>
        <StatusBadge status={m.status} />
      </p>
      <div className="mt-2 space-y-0.5">
        <Delta change={m.change_year_ago} unit={m.unit} />
        <Delta change={m.change_prior} unit={m.unit} />
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        Published {formatAklDate(kpi.published_at)} ·{" "}
        {kpi.source_url ? (
          <a className="underline underline-offset-2" href={kpi.source_url} target="_blank" rel="noreferrer">
            Source
          </a>
        ) : (
          "Source n/a"
        )}
      </p>
    </article>
  );
}
