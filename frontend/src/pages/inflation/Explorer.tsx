import { useState } from "react";
import type { CpiDashboard, CpiSeries } from "@/api/types";
import { ChartCard } from "@/charts/ChartCard";
import { componentOption, historyCsvRows, rangeFilter, type ComponentMode, type CpiRange } from "@/charts/cpi";
import { useChartTheme } from "@/charts/theme";
import { Segmented } from "@/components/Segmented";
import { formatNumber, monthLabel } from "@/lib/format";
import { fullMonth, plainName } from "./format";

const MODES = [
  { value: "annual", label: "Annual change" },
  { value: "quarterly", label: "Quarterly change" },
  { value: "index", label: "Index" },
] as const;
const ADJUSTMENT = { none: "Unadjusted", seasonally_adjusted: "Seasonally adjusted" } as const;
const HEADLINE = ["all_groups", "tradables", "non_tradables"];

type Source = { label: string; url: string | null; updated: string; captured: string };

export function Explorer({ data, range, source }: { data: CpiDashboard; range: CpiRange; source: Source }) {
  const theme = useChartTheme();
  const [slug, setSlug] = useState("food");
  const [mode, setMode] = useState<ComponentMode>("annual");
  const [requested, setAdjustment] = useState<keyof typeof ADJUSTMENT>("none");
  const latest = data.reference_period;
  const find = (s: string, adj: string) => data.series.find((x) => x.slug === s && x.adjustment === adj);
  const nsa = data.series.filter((s) => s.adjustment === "none");
  const sa = find(slug, "seasonally_adjusted");
  const hasSa = !!sa && sa.points.at(-1)?.period === latest;
  const adjustment = hasSa ? requested : "none";
  const series = (adjustment === "none" ? find(slug, "none") : sa) as CpiSeries;
  const groupsOf = (kind: string) => nsa.filter((s) => s.classification === kind);
  const optionGroups: [string, CpiSeries[]][] = [
    ["Headline and tradability", nsa.filter((s) => HEADLINE.includes(s.slug))],
    ["Groups", groupsOf("Level 1 group")],
    ["Selected housing, energy and food components", nsa.filter((s) => s.classification.startsWith("Level") && s.classification !== "Level 1 group")],
  ];
  const visible = rangeFilter(series.points, range);
  const last = series.points.at(-1);
  const meta = { releaseKey: data.analysis.release.release_key, sourceUrl: source.url };
  const modeLabel = MODES.find((m) => m.value === mode)!.label.toLowerCase();
  const table = groupsOf("Level 1 group")
    .flatMap((s) => (s.points.at(-1) ? [{ s, p: s.points.at(-1)! }] : []))
    .sort((a, b) => (b.p.annual_pct ?? -Infinity) - (a.p.annual_pct ?? -Infinity));
  const num = (v: number | null | undefined) => (v === null || v === undefined ? "n/a" : formatNumber(v, { decimals: 1 }));
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-3">
        <label className="grid gap-1 text-xs">
          CPI component
          <select className="rounded-md border bg-background px-2 py-1.5 text-sm" value={slug} onChange={(e) => setSlug(e.target.value)}>
            {optionGroups.map(([label, list]) => (
              <optgroup key={label} label={label}>
                {list.map((s) => <option key={s.slug} value={s.slug}>{plainName(s)}</option>)}
              </optgroup>
            ))}
          </select>
        </label>
        <Segmented<ComponentMode> label="Component view" value={mode} onChange={setMode} options={MODES} />
        {hasSa && (
          <Segmented<keyof typeof ADJUSTMENT> label="Adjustment" value={adjustment} onChange={setAdjustment}
            options={Object.entries(ADJUSTMENT).map(([value, label]) => ({ value: value as keyof typeof ADJUSTMENT, label }))} />
        )}
      </div>
      <ChartCard
        title={`${plainName(series)} · ${modeLabel} · ${ADJUSTMENT[adjustment as keyof typeof ADJUSTMENT].toLowerCase()}`}
        question={last ? `${fullMonth(last.period)} quarter: how has this component's price level moved?` : "How has this component moved?"}
        unit={mode === "index" ? "index (June 2017 = 1000)" : "percent"} source={source}
        caveat={mode === "index" ? "Axis does not start at zero. Index levels are published as rounded numbers." : "Percentage change in this component's prices; not its contribution to the headline change."}
        option={componentOption(series, mode, range, theme)} ariaLabel="CPI component history" height={300}
        csvFilename={`cpi-${series.slug}-${adjustment}.csv`} csvRows={historyCsvRows(series, visible, meta)} />
      <p aria-label="Component source" className="text-xs text-muted-foreground">
        Stats NZ series {series.source_reference ?? "n/a"} · {series.classification} · {ADJUSTMENT[adjustment as keyof typeof ADJUSTMENT]} index · latest {last ? monthLabel(last.period) : "n/a"} ({series.status}).
        {adjustment === "seasonally_adjusted" && " Seasonally adjusted values are re-estimated every quarter and can be revised."}
      </p>
      <div className="overflow-x-auto" role="region" aria-label="Latest price change by group table" tabIndex={0}>
        <table aria-label="Latest price change by group" className="w-full text-left text-sm">
          <caption className="mb-1 text-left text-xs text-muted-foreground">
            Unadjusted price change by group, {fullMonth(latest)} quarter, sorted by annual change. Percent, not contribution.
          </caption>
          <thead>
            <tr className="text-xs text-muted-foreground">
              <th scope="col" className="py-1 pr-4 font-medium">Group</th>
              <th scope="col" className="py-1 pr-4 text-right font-medium">Quarterly change (%)</th>
              <th scope="col" className="py-1 pr-4 text-right font-medium">Annual change (%)</th>
              <th scope="col" className="py-1 text-right font-medium">Index</th>
            </tr>
          </thead>
          <tbody>
            {table.map(({ s, p }) => (
              <tr key={s.slug} className="border-t">
                <th scope="row" className="py-1 pr-4 font-normal">{plainName(s)}</th>
                <td className="py-1 pr-4 text-right tabular-nums">{num(p.quarterly_pct)}</td>
                <td className="py-1 pr-4 text-right tabular-nums">{num(p.annual_pct)}</td>
                <td className="py-1 text-right tabular-nums">{formatNumber(p.index)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
