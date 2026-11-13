import type { Divergence } from "@/api/bank";
import { ADJUSTMENT_LABELS } from "./labels";

const signed = (v: number) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${+Math.abs(v).toFixed(2)}`;
const points = (d: Divergence, v: number) => (d.unit_label === "%" ? `${+v.toFixed(2)} percentage points` : `${+v.toFixed(2)} ${d.unit_label}`);

/** Where banks disagree most: groups of three or more banks, widest spread first. Each bank is shown against the median. */
export function BankDivergence({ items, indicator }: { items: Divergence[]; indicator: string }) {
  const mine = items.filter((d) => d.indicator === indicator).sort((a, b) => b.spread - a.spread);
  if (mine.length === 0) {
    return <p className="text-sm text-muted-foreground">Divergence needs at least three banks with comparable forecasts for the same target.</p>;
  }
  return (
    <ol className="space-y-5">
      {mine.map((d) => (
        <li key={`${d.adjustment}|${d.group_key}`} className="border-t pt-3">
          <p className="font-medium">
            {d.indicator_name}, {d.horizon_label}: {d.basis_label}, {ADJUSTMENT_LABELS[d.adjustment] ?? "adjustment not stated"}
          </p>
          <p className="text-sm text-muted-foreground">Spread {points(d, d.spread)}; median {+d.median.toFixed(2)}{d.unit_label === "%" ? "%" : ` ${d.unit_label}`}. Banks are listed from the highest forecast to the lowest.</p>
          <ul className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-sm">
            {d.banks.map((b) => (
              <li key={b.key}>{b.name} <span className="tabular-nums">{signed(b.distance_from_median)}</span> from the median</li>
            ))}
          </ul>
        </li>
      ))}
    </ol>
  );
}
