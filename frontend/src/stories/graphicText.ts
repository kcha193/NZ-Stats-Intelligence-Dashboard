import { formatNumber, monthLabel } from "@/lib/format";
import type { PeriodStyle, Thumb, ThumbPoint, ValueFormat } from "./types";

/** A value as a graphic prints it: rates to one decimal with %, contributions to two decimals in pp, people whole. */
export function fmtValue(v: number, format: ValueFormat, signed = false): string {
  if (format === "pp") return `${formatNumber(v, { signed: true, decimals: 2 })} pp`;
  if (format === "pct") return `${formatNumber(v, { signed, decimals: 1 })}%`;
  return formatNumber(Math.round(v), { signed });
}

export function periodName(period: string, style: PeriodStyle): string {
  return style === "year-ended" ? `YE ${monthLabel(period)}` : monthLabel(period);
}

const present = (points: ThumbPoint[]) => points.filter((p): p is ThumbPoint & { value: number } => p.value !== null);

/** The highest point before the latest one, when it is higher than the latest: the line's one contextual label. */
export function peakBefore(points: ThumbPoint[]): (ThumbPoint & { value: number }) | null {
  const pts = present(points);
  const last = pts.at(-1);
  if (!last || pts.length < 3) return null;
  const peak = pts.slice(0, -1).reduce((m, p) => (p.value > m.value ? p : m));
  return peak.value > last.value ? peak : null;
}

/** Text alternative for the graphic: the same numbers the graphic labels, in reading order. */
export function describeThumb(t: Thumb): string {
  switch (t.kind) {
    case "line": {
      const pts = present(t.points);
      const first = pts[0];
      const last = pts.at(-1);
      if (!first || !last) return t.name;
      const peak = peakBefore(t.points);
      const signed = t.format === "people" && t.zero;
      return [
        `${t.name}, ${periodName(first.period, t.period)} to ${periodName(last.period, t.period)}.`,
        `Latest ${fmtValue(last.value, t.format, signed)} (${periodName(last.period, t.period)}${last.provisional ? ", provisional" : ""}).`,
        ...(peak ? [`Peak ${fmtValue(peak.value, t.format, signed)} (${periodName(peak.period, t.period)}).`] : []),
      ].join(" ");
    }
    case "columns": {
      const pts = present(t.points);
      const last = pts.at(-1);
      if (!last) return t.name;
      const up = pts.filter((p) => Number(p.value.toFixed(1)) > 0).length;
      const down = pts.filter((p) => Number(p.value.toFixed(1)) < 0).length;
      return `${t.name}, last ${pts.length} periods: ${up} rises and ${down} falls. Latest ${fmtValue(last.value, t.format, true)} (${periodName(last.period, t.period)}).`;
    }
    case "bars":
      return `${t.name}: ${t.items.map((i) => `${i.label} ${fmtValue(i.value, t.format, true)}`).join(", ")}.`;
    case "pair":
      return `${t.name}: ${t.items.map((i) => `${i.label} ${fmtValue(i.value, t.format)}`).join("; ")}. ${t.gap.label}: ${t.gap.value}.`;
  }
}

/** For a compact graphic: at most `max` items, largest movements kept, original (ranked) order preserved. */
export function largestItems<T extends { value: number }>(items: T[], max: number): T[] {
  if (items.length <= max) return items;
  const keep = new Set([...items].sort((a, b) => Math.abs(b.value) - Math.abs(a.value)).slice(0, max));
  return items.filter((i) => keep.has(i));
}
