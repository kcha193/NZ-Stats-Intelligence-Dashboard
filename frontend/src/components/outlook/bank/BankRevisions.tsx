import { useMemo } from "react";
import type { BankRevisions as Data } from "@/api/bank";
import type { ForecastSeries } from "@/api/types";
import { EChart } from "@/charts/EChart";
import { formatForecastValue, minSpanFor, valueRange } from "@/charts/forecasts";
import { dateBounds, revisionOption } from "@/charts/forecastTrack";
import { useChartTheme } from "@/charts/theme";
import { formatCivilDate } from "@/lib/format";
import { ADJUSTMENT_LABELS } from "./labels";

type Entry = { adjustment: Data["histories"][number]["adjustment"]; series: ForecastSeries };

function Panel({ s, range, dates }: { s: ForecastSeries; range: ReturnType<typeof valueRange>; dates: { min: number; max: number } }) {
  const theme = useChartTheme();
  const option = useMemo(() => revisionOption(s, theme, range, dates), [s, theme, range, dates]);
  const show = (v: number) => formatForecastValue(v, s.unit_label);
  const trail = s.vintages.map((v) => `${formatCivilDate(v.published_on)} ${show(v.value)}`).join(", ");
  const name = s.institution.name;
  if (s.vintages.length < 2) {
    const only = s.vintages[0];
    return <li className="text-sm">{name}: one forecast so far ({show(only.value)}, {formatCivilDate(only.published_on)}); a revision needs a second outlook report.</li>;
  }
  const total = s.total_revision ?? 0;
  const direction = total > 0 ? "up" : total < 0 ? "down" : "unchanged";
  return (
    <li>
      <p className="text-sm font-medium">{name}</p>
      <EChart option={option} height={150} ariaLabel={`${name} forecast revisions: ${trail}.`} />
      <p className="text-xs text-muted-foreground">
        {direction === "unchanged" ? "Unchanged" : `Revised ${direction} ${+Math.abs(total).toFixed(2)}${s.unit_label === "%" ? " percentage points" : ` ${s.unit_label}`}`} across {s.vintages.length} outlook reports.
      </p>
    </li>
  );
}

/** Each bank's forecast across successive outlook reports, per target. Different targets or measures never share a chart. */
export function BankRevisions({ data, indicator }: { data: Data; indicator: string }) {
  const entries: Entry[] = data.histories.flatMap((h) =>
    h.history.series.filter((s) => s.indicator === indicator && s.kind === "central").map((series) => ({ adjustment: h.adjustment, series })),
  );
  if (entries.length === 0) {
    return <p className="text-sm text-muted-foreground">No revision history to show yet: a revision needs two outlook reports from the same bank for the same target.</p>;
  }
  const targets = new Map<string, Entry[]>();
  for (const e of entries) targets.set(`${e.adjustment}|${e.series.target_key}`, [...(targets.get(`${e.adjustment}|${e.series.target_key}`) ?? []), e]);
  return (
    <div className="space-y-8">
      {[...targets.entries()].map(([key, group]) => {
        const all = group.flatMap((e) => e.series.vintages.map((v) => v.value));
        const first = group[0].series;
        const range = valueRange(all, minSpanFor(first.unit_label, all));
        const dates = dateBounds(group.map((e) => e.series));
        const adjustment = ADJUSTMENT_LABELS[group[0].adjustment];
        return (
          <section key={key} className="border-t pt-4">
            <h4 className="type-card">{first.indicator_name}, {first.horizon_label}</h4>
            <p className="text-sm text-muted-foreground">{[first.basis_label, adjustment].filter(Boolean).join(", ")}</p>
            <ul className="mt-3 grid gap-6 md:grid-cols-2">
              {group.map((e) => <Panel key={e.series.key} s={e.series} range={range} dates={dates} />)}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
