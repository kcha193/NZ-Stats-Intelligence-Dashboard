import type { BankForecast, BankForecasts } from "@/api/bank";
import type { ForecastGroup } from "@/api/types";
import { formatForecastValue } from "@/charts/forecasts";
import { ADJUSTMENT_LABELS, INDICATOR_NAMES, KIND_LABELS } from "./labels";

type Bank = { key: string; name: string };

type Adjustment = BankForecast["adjustment"];

/** Claims differing only in adjustment or scenario must not share a key, or a row would open another claim's evidence. */
const cellKey = (f: BankForecast["forecast"], adjustment: Adjustment) =>
  [f.summary_id, f.indicator_label, f.horizon, f.value, adjustment, f.scenario ?? ""].join("|");

function rowNote(group: ForecastGroup, adjustment: BankForecasts["comparison"][number]["adjustment"]): string {
  const parts = [group.basis_label, ADJUSTMENT_LABELS[adjustment], group.kind === "scenario" ? `scenario: ${group.scenario}` : null];
  return parts.filter(Boolean).join(", ");
}

/**
 * Forecasts by bank for one indicator: a row per target period, a column per bank, each cell the bank's latest forecast.
 * A dash is a forecast the bank did not make: nothing is filled in, interpolated or carried over.
 */
export function BankForecastTable({
  data, banks, indicator, onSelect,
}: {
  data: BankForecasts;
  banks: Bank[];
  indicator: string;
  onSelect?: (f: BankForecast) => void;
}) {
  const lookup = new Map(data.forecasts.map((f) => [cellKey(f.forecast, f.adjustment), f]));
  const rows = data.comparison.flatMap((c) =>
    c.comparison.groups.filter((g) => g.indicator === indicator).map((group) => ({ group, adjustment: c.adjustment })),
  );
  if (rows.length === 0) return <p className="text-sm text-muted-foreground">No bank forecast for this indicator yet.</p>;
  const name = INDICATOR_NAMES[indicator] ?? indicator;
  return (
    // `relative` makes this the containing block of the sr-only spans, so the scroller clips them instead of the page.
    <div role="region" aria-label={`${name} forecasts`} tabIndex={0} className="relative overflow-x-auto">
      <table className="w-full min-w-[32rem] border-collapse text-sm">
        <caption className="sr-only">
          {name} forecasts by bank, each bank&apos;s latest forecast, by target period. A dash means the bank has no current forecast for that period; a figure left out is listed below with its reason.
        </caption>
        <thead>
          <tr className="border-b-2 border-rule-strong text-left">
            <th scope="col" className="py-2 pr-4 font-medium">Target period</th>
            {banks.map((b) => <th key={b.key} scope="col" className="px-3 py-2 text-right font-medium">{b.name}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map(({ group, adjustment }) => (
            <tr key={`${adjustment}|${group.key}`} className="border-b">
              <th scope="row" className="py-3 pr-4 text-left font-normal">
                <span className="font-medium">{group.indicator_name}, {group.horizon_label}</span>
                <span className="block text-xs text-muted-foreground">{rowNote(group, adjustment)}</span>
              </th>
              {banks.map((b) => {
                const hit = group.rows.find((r) => r.forecast.institution.key === b.key);
                if (!hit) {
                  return (
                    <td key={b.key} className="px-3 py-3 text-right text-muted-foreground">
                      <span aria-hidden>–</span><span className="sr-only">No forecast</span>
                    </td>
                  );
                }
                const bf = lookup.get(cellKey(hit.forecast, adjustment));
                const shown = formatForecastValue(hit.forecast.value ?? 0, group.unit_label);
                const kind = bf ? KIND_LABELS[bf.report_kind] : null;
                return (
                  <td key={b.key} className="px-3 py-3 text-right tabular-nums">
                    <button
                      type="button"
                      aria-label={`${b.name}, ${group.horizon_label}: ${shown}${kind ? ` (${kind})` : ""}`}
                      onClick={() => bf && onSelect?.(bf)}
                      className="min-h-11 rounded px-2 underline decoration-dotted underline-offset-4 hover:bg-muted focus-visible:outline focus-visible:outline-2"
                    >
                      {shown}
                      {kind && <span className="block text-xs text-muted-foreground">{kind}</span>}
                    </button>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
