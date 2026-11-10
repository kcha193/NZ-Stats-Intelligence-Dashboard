import { useId } from "react";
import type { BankConsensusGroup } from "@/api/bank";
import { EChart } from "@/charts/EChart";
import { bankConsensusOption } from "@/charts/bankConsensus";
import { formatForecastValue } from "@/charts/forecasts";
import { useChartTheme } from "@/charts/theme";
import { formatCivilDate } from "@/lib/format";
import { ADJUSTMENT_LABELS } from "./labels";

function Group({ g }: { g: BankConsensusGroup }) {
  const theme = useChartTheme();
  const titleId = useId();
  const show = (v: number | null | undefined) => formatForecastValue(v ?? 0, g.unit_label);
  const adjustment = ADJUSTMENT_LABELS[g.adjustment];
  const list = g.contributors.map((c) => `${c.name} ${show(c.value)}`).join(", ");
  const heading = `${g.indicator_name}, ${g.horizon_label}`;
  return (
    <figure aria-labelledby={titleId} className="border-t pt-5">
      <figcaption>
        <h4 id={titleId} className="type-card">{g.title}: {heading}</h4>
        <p className="mt-1 text-sm text-muted-foreground">
          {[g.basis_label, adjustment].filter(Boolean).join(", ")}, in {g.unit_label === "%" ? "percent" : g.unit_label}.
        </p>
        <p className="text-xs text-muted-foreground">{g.disclaimer}</p>
      </figcaption>
      {g.n >= 2 ? (
        <>
          <EChart option={bankConsensusOption(g, theme)} height={Math.max(180, 56 + (g.contributors.length + g.markers.length) * 34)} ariaLabel={`${heading}, ${g.basis_label}: ${list}.`} />
          <p className="mt-2 text-sm">
            Median {show(g.median)}, range {show(g.minimum)} to {show(g.maximum)} across {g.n} banks.
          </p>
        </>
      ) : (
        <p className="mt-3 text-sm text-muted-foreground">
          Only one bank has a comparable forecast for this target ({list}), so no comparison is drawn.
        </p>
      )}
      {g.markers.length > 0 && (
        <p className="mt-1 text-xs text-muted-foreground">
          Reference: {g.markers.map((m) => `${m.name} ${show(m.value)}`).join(", ")} (not part of the bank figures).
        </p>
      )}
      <table className="sr-only">
        <caption>{heading}: the values behind the chart</caption>
        <thead><tr><th scope="col">Institution</th><th scope="col">Forecast</th><th scope="col">Published</th></tr></thead>
        <tbody>
          {g.contributors.map((c) => (
            <tr key={c.key}><th scope="row">{c.name}</th><td>{show(c.value)}</td><td>{formatCivilDate(c.published_on)}</td></tr>
          ))}
          {g.markers.map((m) => (
            <tr key={m.key}><th scope="row">{m.name} (reference institution)</th><td>{show(m.value)}</td><td>{formatCivilDate(m.published_on)}</td></tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}

/** The banks' latest outlook forecasts for one indicator, one chart per measure and target. */
export function BankConsensusChart({ groups, indicator }: { groups: BankConsensusGroup[]; indicator: string }) {
  const mine = groups.filter((g) => g.indicator === indicator && g.kind === "central");
  if (mine.length === 0) return <p className="text-sm text-muted-foreground">No comparable bank forecasts for this indicator yet.</p>;
  return <div className="space-y-8">{mine.map((g) => <Group key={`${g.adjustment}|${g.key}`} g={g} />)}</div>;
}
