import type { Metric } from "@/api/types";
import { formatNumber } from "@/lib/format";

const pct = (v: number) => `${v < 0 ? "−" : ""}${formatNumber(Math.abs(v), { decimals: 1 })}%`;

/** Published rates as headline tiles: each names its measure, period and the previous published figure. */
export function MetricTiles({ label, metrics }: { label: string; metrics: Metric[] }) {
  return (
    <section aria-label={label} className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {metrics.map((m) => (
        <article key={m.series_key} className="rounded-md border bg-card p-3">
          <h2 className="text-xs font-medium text-muted-foreground">{m.label}</h2>
          <p className="mt-1 text-2xl font-semibold tracking-tight">{pct(m.value)}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {m.period_label}
            {m.change_prior ? ` · ${m.change_prior.label}: ${pct(m.change_prior.previous)}` : ""}
          </p>
        </article>
      ))}
    </section>
  );
}
