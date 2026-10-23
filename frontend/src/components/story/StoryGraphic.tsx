import type { Thumb } from "@/stories/types";

const W = 160;
const H = 56;
const PAD = 3;

function linePath(values: (number | null)[], y: (v: number) => number): string {
  const step = values.length > 1 ? (W - PAD * 2) / (values.length - 1) : 0;
  let d = "";
  let open = false;
  values.forEach((v, i) => {
    if (v === null) {
      open = false;
      return;
    }
    d += `${open ? "L" : "M"}${(PAD + i * step).toFixed(1)},${y(v).toFixed(1)}`;
    open = true;
  });
  return d;
}

/** A decorative thumbnail: the card's text states the finding, so the graphic is hidden from assistive tech. */
export function MiniChart({ thumb }: { thumb: Thumb }) {
  if (thumb.kind === "line") {
    const vals = [...thumb.values, ...(thumb.compare ?? [])].filter((v): v is number => v !== null);
    if (vals.length < 2) return null;
    const lo = Math.min(...vals, ...(thumb.zero ? [0] : []));
    const hi = Math.max(...vals, ...(thumb.zero ? [0] : []));
    const span = hi - lo || 1;
    const y = (v: number) => PAD + (1 - (v - lo) / span) * (H - PAD * 2);
    const lastIndex = thumb.values.length - 1;
    const last = thumb.values[lastIndex];
    const step = (W - PAD * 2) / lastIndex;
    return (
      <svg viewBox={`0 0 ${W} ${H}`} className="h-14 w-full" preserveAspectRatio="none" aria-hidden focusable="false">
        {lo < 0 && hi > 0 || thumb.zero ? (
          <line x1={0} x2={W} y1={y(0)} y2={y(0)} stroke="var(--chart-muted)" strokeWidth={1} strokeDasharray="2 3" vectorEffect="non-scaling-stroke" />
        ) : null}
        {thumb.compare && (
          <path d={linePath(thumb.compare, y)} fill="none" stroke="var(--chart-2)" strokeWidth={2} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
        )}
        <path d={linePath(thumb.values, y)} fill="none" stroke="var(--chart-1)" strokeWidth={2} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
        {last !== null && <circle cx={PAD + lastIndex * step} cy={y(last)} r={3} fill="var(--chart-1)" />}
      </svg>
    );
  }
  const items = thumb.items.slice(0, 8);
  // The zero line sits where the data puts it, so a tiny negative does not waste a third of the width.
  const neg = Math.max(0, ...items.map((i) => -i.value));
  const pos = Math.max(0, ...items.map((i) => i.value));
  const zeroX = PAD + (W - PAD * 2) * (neg / (neg + pos || 1));
  const scale = (W - PAD * 2) / (neg + pos || 1);
  const rowH = H / items.length;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-14 w-full" preserveAspectRatio="none" aria-hidden focusable="false">
      {items.map((i, n) => {
        const w = Math.max(Math.abs(i.value) * scale, 1);
        return (
          <rect key={i.label} x={i.value < 0 ? zeroX - w : zeroX} y={n * rowH + rowH * 0.18} width={w} height={rowH * 0.64} rx={1}
            fill={i.value < 0 ? "var(--chart-negative)" : "var(--chart-1)"} />
        );
      })}
      <line x1={zeroX} x2={zeroX} y1={0} y2={H} stroke="var(--chart-muted)" strokeWidth={1} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
