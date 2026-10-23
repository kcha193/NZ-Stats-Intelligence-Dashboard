import { useLayoutEffect, useRef, useState } from "react";
import type { Thumb, ThumbPoint } from "@/stories/types";
import { describeThumb, fmtValue, largestItems, peakBefore, periodName } from "@/stories/graphicText";

/**
 * Small editorial graphics, drawn as SVG with real text at true pixel size: the drawing is laid out for the width it
 * is given, so a label is never scaled below its set size in a narrow column.
 * One message and one encoding each; every value printed is a published value; the description repeats them for
 * assistive technology. Signed values diverge from a visible zero; counts of people start at zero.
 */
export type GraphicSize = "sm" | "lg";

/** Layout width before the container has been measured (and in tests). */
const WIDTH = { sm: 320, lg: 520 } as const;
const FONT = { sm: 11, lg: 12.5 } as const;
const C = {
  text: "var(--chart-text)", muted: "var(--chart-muted)", grid: "var(--chart-grid)", s1: "var(--chart-1)", s2: "var(--chart-2)",
  pos: "var(--chart-positive)", neg: "var(--chart-negative)",
};

type Props<K extends Thumb["kind"]> = { t: Extract<Thumb, { kind: K }>; size: GraphicSize; w: number };
const approxWidth = (text: string, fs: number) => text.length * fs * 0.56;
const present = (pts: ThumbPoint[]) => pts.map((p, i) => ({ ...p, i })).filter((p): p is typeof p & { value: number } => p.value !== null);

/** Keeps a label's box inside the graphic: start, middle or end anchor, whichever fits. */
function anchorFor(x: number, text: string, fs: number, w: number): { x: number; anchor: "start" | "middle" | "end" } {
  const half = approxWidth(text, fs) / 2;
  if (x - half < 0) return { x: Math.max(0, x - 4), anchor: "start" };
  if (x + half > w) return { x: Math.min(w, x + 4), anchor: "end" };
  return { x, anchor: "middle" };
}

function Line({ t, size, w }: Props<"line">) {
  const fs = FONT[size];
  const h = size === "lg" ? 236 : 124;
  const pts = present(t.points);
  if (pts.length < 2) return null;
  const vals = pts.map((p) => p.value);
  const lo = Math.min(...vals, ...(t.zero ? [0] : []));
  const hi = Math.max(...vals, ...(t.zero ? [0] : []));
  const padT = fs * 2.1;
  const padB = fs * 2;
  const padR = size === "lg" ? 92 : 70;
  const plotW = w - padR;
  const plotH = h - padT - padB;
  const x = (i: number) => (i / (t.points.length - 1)) * plotW;
  const y = (v: number) => padT + ((hi - v) / (hi - lo || 1)) * plotH;
  const signed = t.format === "people" && t.zero;
  let solid = "";
  let dashed = "";
  for (let k = 1; k < pts.length; k++) {
    const [a, b] = [pts[k - 1], pts[k]];
    if (b.i !== a.i + 1) continue; // a gap in the data stays a gap
    const seg = `M${x(a.i).toFixed(1)},${y(a.value).toFixed(1)}L${x(b.i).toFixed(1)},${y(b.value).toFixed(1)}`;
    if (b.provisional) dashed += seg;
    else solid += seg;
  }
  const last = pts.at(-1)!;
  const peak = peakBefore(t.points);
  const peakPt = peak ? pts.find((p) => p.period === peak.period) : undefined;
  const lastText = fmtValue(last.value, t.format, signed);
  const lastY = Math.min(Math.max(y(last.value), fs * 1.1), h - padB - fs * 1.2);
  const zeroY = y(0);
  const showZero = lo < 0 || t.zero;
  const peakLabel = peakPt && `Peak ${fmtValue(peakPt.value, t.format, signed)}, ${periodName(peakPt.period, t.period)}`;
  const peakPos = peakPt && peakLabel ? anchorFor(x(peakPt.i), peakLabel, fs, plotW) : null;
  const hasProvisional = pts.some((p) => p.provisional);
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="block h-auto w-full overflow-visible" role="img" aria-label={describeThumb(t)}>
      {showZero && (
        <>
          <line x1={0} x2={plotW + 6} y1={zeroY} y2={zeroY} stroke={C.muted} strokeWidth={1} strokeDasharray="2 3" />
          {(zeroY < lastY - fs * 1.6 || zeroY > lastY + fs * 2.8) && (
            <text x={plotW + 10} y={zeroY + fs * 0.35} fontSize={fs - 1} fill={C.muted}>0{t.format === "pct" ? "%" : ""}</text>
          )}
        </>
      )}
      <path d={solid} fill="none" stroke={C.s1} strokeWidth={size === "lg" ? 2.5 : 2} strokeLinejoin="round" strokeLinecap="round" />
      {dashed && <path d={dashed} fill="none" stroke={C.s1} strokeWidth={size === "lg" ? 2.5 : 2} strokeDasharray="3 3" strokeLinecap="round" />}
      {peakPt && peakPos && (
        <g>
          <circle cx={x(peakPt.i)} cy={y(peakPt.value)} r={2.75} fill={C.muted} />
          <text x={peakPos.x} y={Math.max(fs, y(peakPt.value) - 7)} textAnchor={peakPos.anchor} fontSize={fs} fill={C.muted}>{peakLabel}</text>
        </g>
      )}
      <circle cx={x(last.i)} cy={y(last.value)} r={size === "lg" ? 5 : 4} fill={C.s1} stroke="var(--background)" strokeWidth={1.5} />
      <text x={x(last.i) + 9} y={lastY + fs * 0.1} fontSize={fs + 3} fontWeight={650} fill={C.text}>{lastText}</text>
      <text x={x(last.i) + 9} y={lastY + fs * 1.25} fontSize={fs - 0.5} fill={C.muted}>{periodName(last.period, t.period)}</text>
      <text x={0} y={h - 3} fontSize={fs - 0.5} fill={C.muted}>{periodName(pts[0].period, t.period)}</text>
      {hasProvisional && (
        <g>
          <line x1={plotW * 0.48} x2={plotW * 0.48 + 14} y1={h - fs * 0.45 - 3} y2={h - fs * 0.45 - 3} stroke={C.s1} strokeWidth={2} strokeDasharray="3 3" />
          <text x={plotW * 0.48 + 18} y={h - 3} fontSize={fs - 0.5} fill={C.muted}>provisional</text>
        </g>
      )}
    </svg>
  );
}

function Columns({ t, size, w }: Props<"columns">) {
  const fs = FONT[size];
  const h = size === "lg" ? 188 : 124;
  const pts = present(t.points);
  if (!pts.length) return null;
  const vals = pts.map((p) => p.value);
  const lo = Math.min(0, ...vals);
  const hi = Math.max(0, ...vals);
  const padT = fs * 1.7;
  const padB = fs * 3.1;
  const plotH = h - padT - padB;
  const step = w / t.points.length;
  const bw = step * 0.66;
  const y = (v: number) => padT + ((hi - v) / (hi - lo || 1)) * plotH;
  const last = pts.at(-1)!;
  const max = pts.reduce((m, p) => (p.value > m.value ? p : m));
  const min = pts.reduce((m, p) => (p.value < m.value ? p : m));
  const label = (p: typeof last, strong: boolean) => {
    const text = fmtValue(p.value, t.format, true);
    const pos = anchorFor(p.i * step + step / 2, text, strong ? fs + 1.5 : fs - 0.5, w);
    const above = p.value >= 0;
    return (
      <text key={`l${p.period}`} x={pos.x} textAnchor={pos.anchor} fontSize={strong ? fs + 1.5 : fs - 0.5}
        fontWeight={strong ? 650 : 400} fill={strong ? C.text : C.muted}
        y={above ? y(p.value) - 4 : y(p.value) + (strong ? fs + 4 : fs + 2)}>{text}</text>
    );
  };
  const extremes = [max, min].filter((p) => p.period !== last.period && Math.abs(p.i - last.i) > 2 && p.value !== 0);
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="block h-auto w-full overflow-visible" role="img" aria-label={describeThumb(t)}>
      {pts.map((p) => {
        const top = y(Math.max(p.value, 0));
        return (
          <rect key={p.period} x={p.i * step + (step - bw) / 2} y={top} width={bw} height={Math.max(Math.abs(y(p.value) - y(0)), 1)} rx={1}
            fill={p.value < 0 ? C.neg : C.pos} opacity={p.provisional ? 0.5 : p.period === last.period ? 1 : 0.78} />
        );
      })}
      <line x1={0} x2={w} y1={y(0)} y2={y(0)} stroke={C.muted} strokeWidth={1} />
      {extremes.map((p) => label(p, false))}
      {label(last, true)}
      <text x={0} y={h - 3} fontSize={fs - 0.5} fill={C.muted}>{periodName(pts[0].period, t.period)}</text>
      <text x={w} y={h - 3} textAnchor="end" fontSize={fs - 0.5} fill={C.muted}>{periodName(last.period, t.period)}</text>
    </svg>
  );
}

/** Up to two lines of a label within `chars`; the second line ends with an ellipsis if text remains. */
function wrapLabel(text: string, chars: number): string[] {
  if (text.length <= chars) return [text];
  const words = text.split(" ");
  let first = "";
  while (words.length && `${first} ${words[0]}`.trim().length <= chars) first = `${first} ${words.shift()}`.trim();
  if (!first) first = words.shift() ?? "";
  const rest = words.join(" ");
  // The second line may run a little longer than the first before it is shortened.
  const room = chars + 4;
  return [first, rest.length > room ? `${rest.slice(0, room - 1).trimEnd()}…` : rest].filter(Boolean);
}

function Bars({ t, size, w }: Props<"bars">) {
  const fs = FONT[size];
  const items = largestItems(t.items, size === "lg" ? 13 : 6);
  const chars = w < 300 ? 18 : size === "lg" && w > 420 ? 30 : 22;
  const labels = items.map((i) => wrapLabel(i.label, chars));
  const twoLine = labels.some((l) => l.length > 1);
  const rowH = twoLine ? fs * 2.55 : fs * 2.05;
  const note = items.length < t.items.length ? `Largest ${items.length} of ${t.items.length} shown` : "";
  const h = items.length * rowH + (note ? fs * 1.9 : 2);
  const labelW = approxWidth("x".repeat(chars), fs) * 0.92;
  const areaX = labelW + 8;
  const room = fs * 4.6;
  const neg = Math.max(0, ...items.map((i) => -i.value));
  const pos = Math.max(0, ...items.map((i) => i.value));
  const negRoom = neg > 0 ? room : 0;
  const posRoom = pos > 0 ? room : 0;
  const scale = (w - areaX - negRoom - posRoom) / (neg + pos || 1);
  const zeroX = areaX + negRoom + neg * scale;
  const posFill = t.format === "pct" ? C.pos : C.s1;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="block h-auto w-full overflow-visible" role="img" aria-label={describeThumb(t)}>
      {items.map((it, n) => {
        const cy = n * rowH + rowH / 2;
        const bw = Math.max(Math.abs(it.value) * scale, 1.5);
        const value = fmtValue(it.value, t.format, true);
        const lines = labels[n];
        return (
          <g key={it.label}>
            <text x={labelW} textAnchor="end" fontSize={fs} fill={C.text} y={cy + fs * 0.35 - (lines.length - 1) * fs * 0.55}>
              {lines.map((l, k) => <tspan key={k} x={labelW} dy={k ? fs * 1.1 : 0}>{l}</tspan>)}
            </text>
            <rect x={it.value < 0 ? zeroX - bw : zeroX} y={cy - fs * 0.62} width={bw} height={fs * 1.24} rx={1.5} fill={it.value < 0 ? C.neg : posFill} />
            <text x={it.value < 0 ? zeroX - bw - 4 : zeroX + bw + 4} textAnchor={it.value < 0 ? "end" : "start"} y={cy + fs * 0.35}
              fontSize={fs} fontWeight={600} fill={C.text}>{value}</text>
          </g>
        );
      })}
      <line x1={zeroX} x2={zeroX} y1={0} y2={items.length * rowH} stroke={C.muted} strokeWidth={1} />
      {note && <text x={0} y={h - 3} fontSize={fs - 1} fill={C.muted}>{note}</text>}
    </svg>
  );
}

function Pair({ t, size, w }: Props<"pair">) {
  const fs = FONT[size];
  const [a, b] = t.items;
  if (t.format === "people") {
    // Counts start at zero, so bar length is the count.
    const max = Math.max(a.value, b.value, 1);
    const valueRoom = fs * 5.5;
    const rowH = fs * 3.4;
    const h = rowH * 2 + fs * 2.2;
    return (
      <svg viewBox={`0 0 ${w} ${h}`} className="block h-auto w-full overflow-visible" role="img" aria-label={describeThumb(t)}>
        {t.items.map((it, n) => {
          const top = n * rowH;
          const bw = Math.max(0, it.value) / max * (w - valueRoom);
          return (
            <g key={it.label}>
              <text x={0} y={top + fs} fontSize={fs} fill={C.muted}>{it.label}</text>
              <rect x={0} y={top + fs * 1.45} width={Math.max(bw, 1.5)} height={fs * 1.35} rx={1.5} fill={n === 0 ? C.s1 : C.s2} />
              <text x={bw + 6} y={top + fs * 2.55} fontSize={fs + 1.5} fontWeight={650} fill={C.text}>{fmtValue(it.value, t.format)}</text>
            </g>
          );
        })}
        <text x={0} y={h - 3} fontSize={fs} fill={C.text}>
          <tspan fill={C.muted}>{t.gap.label}: </tspan><tspan fontWeight={650}>{t.gap.value}</tspan>
        </text>
      </svg>
    );
  }
  // Rates: a dumbbell on one percentage axis that includes zero; the gap between the dots is in percentage points.
  const h = size === "lg" ? 132 : 108;
  const lo = Math.min(0, a.value, b.value);
  const hi = Math.max(0, a.value, b.value);
  const span = hi - lo || 1;
  const pad = w * 0.12;
  const x = (v: number) => pad + ((v - lo) / span) * (w - pad * 2);
  const axisY = h * 0.56;
  const [left, right] = a.value <= b.value ? [a, b] : [b, a];
  const close = x(right.value) - x(left.value) < fs * 9;
  const colour = (it: typeof a) => (it === a ? C.s1 : C.s2);
  const label = (it: typeof a, side: "left" | "right") => {
    const cx = x(it.value);
    const anchor = close ? (side === "left" ? "end" : "start") : "middle";
    const tx = close ? cx + (side === "left" ? 4 : -4) : cx;
    return (
      <g key={it.label}>
        <text x={tx} y={axisY - fs * 2.6} textAnchor={anchor} fontSize={fs} fill={C.muted}>{it.label}</text>
        <text x={tx} y={axisY - fs * 1.2} textAnchor={anchor} fontSize={fs + 3} fontWeight={650} fill={C.text}>{fmtValue(it.value, t.format)}</text>
      </g>
    );
  };
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="block h-auto w-full overflow-visible" role="img" aria-label={describeThumb(t)}>
      <line x1={pad * 0.4} x2={w - pad * 0.4} y1={axisY} y2={axisY} stroke={C.grid} strokeWidth={1} />
      <line x1={x(0)} x2={x(0)} y1={axisY - 5} y2={axisY + 5} stroke={C.muted} strokeWidth={1} />
      <text x={x(0)} y={axisY + fs * 1.6} textAnchor="middle" fontSize={fs - 1} fill={C.muted}>0%</text>
      <line x1={x(left.value)} x2={x(right.value)} y1={axisY} y2={axisY} stroke={C.muted} strokeWidth={3} strokeLinecap="round" />
      <circle cx={x(left.value)} cy={axisY} r={size === "lg" ? 7 : 6} fill={colour(left)} stroke="var(--background)" strokeWidth={1.5} />
      <circle cx={x(right.value)} cy={axisY} r={size === "lg" ? 7 : 6} fill={colour(right)} stroke="var(--background)" strokeWidth={1.5} />
      {label(left, "left")}
      {label(right, "right")}
      <text x={(x(left.value) + x(right.value)) / 2} y={h - 3} textAnchor="middle" fontSize={fs} fill={C.text}>
        <tspan fill={C.muted}>{t.gap.label} </tspan><tspan fontWeight={650}>{t.gap.value}</tspan>
      </text>
    </svg>
  );
}

function useWidth<T extends HTMLElement>(fallback: number) {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(fallback);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const read = () => {
      const w = Math.round(el.getBoundingClientRect().width);
      if (w > 0) setWidth(w);
    };
    read();
    const observer = new ResizeObserver(read);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

export function StoryGraphic({ thumb, size = "sm" }: { thumb: Thumb; size?: GraphicSize }) {
  const [ref, w] = useWidth<HTMLDivElement>(WIDTH[size]);
  const props = { size, w: Math.max(w, 220) };
  return (
    <div ref={ref} className="w-full min-w-0">
      {thumb.kind === "line" && <Line t={thumb} {...props} />}
      {thumb.kind === "columns" && <Columns t={thumb} {...props} />}
      {thumb.kind === "bars" && <Bars t={thumb} {...props} />}
      {thumb.kind === "pair" && <Pair t={thumb} {...props} />}
    </div>
  );
}
