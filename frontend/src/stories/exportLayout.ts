import { formatAklDate } from "@/lib/format";
import { CATEGORY_LABEL, type Story } from "./types";

/** Presentation formats: social landscape and a portrait card for slides and feeds. */
export const FORMATS = {
  landscape: { width: 1200, height: 675, label: "Landscape PNG (1200 × 675)" },
  portrait: { width: 1200, height: 1500, label: "Portrait PNG (1200 × 1500)" },
} as const;
export type ExportFormat = keyof typeof FORMATS;

export type Measure = (text: string, font: string) => number;
export type Role = "kicker" | "headline" | "stat" | "statUnit" | "statLabel" | "chartTitle" | "context" | "caveat" | "source" | "attribution";
export type Line = { role: Role; text: string; x: number; y: number; size: number; font: string; tone: "text" | "muted" | "accent" };
export type Rect = { x: number; y: number; w: number; h: number };
export type ExportLayout = { width: number; height: number; lines: Line[]; chart: Rect; rules: Rect[]; truncated: Role[] };

export type ExportText = {
  kicker: string; headline: string; stat: string; statUnit: string; statLabel: string;
  chartTitle: string; context: string; caveat: string; source: string; attribution: string;
};

const FAMILY = '"IBM Plex Sans Variable", "IBM Plex Sans", system-ui, sans-serif';
export const font = (size: number, weight = 400) => `${weight} ${size}px ${FAMILY}`;

/** Everything printed on the image, so it can be read without visiting the dashboard. */
export function exportText(story: Story, figure: { title: string; unit: string; caveat: string }, storyUrl: string): ExportText {
  const p = story.provenance;
  const flags = [story.dataStatus === "provisional" ? "provisional" : null, p.status === "corrected" ? "corrected release" : null].filter(Boolean);
  return {
    kicker: CATEGORY_LABEL[story.category].toUpperCase(),
    headline: story.headline,
    stat: story.stat.value,
    statUnit: story.stat.unit,
    statLabel: story.stat.label,
    chartTitle: figure.title,
    context: `Reference period: ${story.referenceLabel}${flags.length ? ` (${flags.join(", ")})` : ""}. Unit: ${figure.unit}.`,
    caveat: [p.status === "corrected" ? story.caveats[0] : null, figure.caveat].filter(Boolean).join(" "),
    source: `Source: Stats NZ, ${p.title}, published ${formatAklDate(p.publishedAt)}${p.pageUrl ? ` (${p.pageUrl})` : ""}. Licensed CC BY 4.0.`,
    attribution: `NZ Stats Intelligence (independent, not endorsed by Stats NZ) · ${storyUrl}`,
  };
}

/** Word wrap; a word wider than the line (a URL) is split by character so nothing runs off the edge. */
export function wrap(text: string, f: string, width: number, measure: Measure): string[] {
  const lines: string[] = [];
  let line = "";
  for (const word of text.split(/\s+/).filter(Boolean)) {
    const next = line ? `${line} ${word}` : word;
    if (measure(next, f) <= width) {
      line = next;
      continue;
    }
    if (line) lines.push(line);
    line = "";
    let rest = word;
    while (measure(rest, f) > width) {
      let n = rest.length - 1;
      while (n > 1 && measure(rest.slice(0, n), f) > width) n--;
      lines.push(rest.slice(0, n));
      rest = rest.slice(n);
    }
    line = rest;
  }
  if (line) lines.push(line);
  return lines;
}

/** Wraps to at most `max` lines; the last kept line ends with an ellipsis when text was dropped. */
function clamp(lines: string[], max: number, f: string, width: number, measure: Measure): { lines: string[]; cut: boolean } {
  if (lines.length <= max) return { lines, cut: false };
  const kept = lines.slice(0, max);
  let last = kept[max - 1];
  while (last && measure(`${last}…`, f) > width) last = last.slice(0, -1).trimEnd();
  kept[max - 1] = `${last}…`;
  return { lines: kept, cut: true };
}

type Spec = {
  pad: number; kicker: number; headline: number[]; headlineMax: number; stat: number[]; statUnit: number; statLabel: number;
  chartTitle: number; context: number; caveat: number; caveatMax: number; source: number; attribution: number;
};
const SPECS: Record<ExportFormat, Spec> = {
  landscape: { pad: 48, kicker: 15, headline: [36, 32, 28, 24, 22, 20], headlineMax: 5, stat: [64, 56, 48, 40], statUnit: 17, statLabel: 15,
    chartTitle: 18, context: 14, caveat: 14, caveatMax: 3, source: 14, attribution: 13 },
  portrait: { pad: 72, kicker: 20, headline: [60, 54, 48, 42, 36, 32], headlineMax: 4, stat: [120, 104, 88, 72], statUnit: 24, statLabel: 20,
    chartTitle: 26, context: 19, caveat: 19, caveatMax: 3, source: 19, attribution: 17 },
};
const LEAD = 1.25;

/** Appends wrapped lines to `into` from `y` downwards and returns the y below them. */
type EmitArgs = [role: Role, texts: string[], x: number, y: number, size: number, weight: number, tone: Line["tone"]];
function emit(into: Line[], ...[role, texts, x, y, size, weight, tone]: EmitArgs): number {
  texts.forEach((text, i) => into.push({ role, text, x, y: y + i * size * LEAD, size, font: font(size, weight), tone }));
  return y + texts.length * size * LEAD;
}

export function layoutExport(t: ExportText, format: ExportFormat, measure: Measure): ExportLayout {
  const { width, height } = FORMATS[format];
  const s = SPECS[format];
  const lines: Line[] = [];
  const truncated: Role[] = [];
  const put = (...args: EmitArgs) => emit(lines, ...args);
  const inner = width - s.pad * 2;

  // Footer, bottom-up: source then attribution, both full width and never shortened.
  const sourceLines = wrap(t.source, font(s.source), inner, measure);
  const attrLines = wrap(t.attribution, font(s.attribution), inner, measure);
  const footerTop = height - s.pad - (sourceLines.length * s.source + attrLines.length * s.attribution) * LEAD;
  put("attribution", attrLines, s.pad, put("source", sourceLines, s.pad, footerTop, s.source, 400, "muted"), s.attribution, 400, "muted");
  const rules: Rect[] = [{ x: 0, y: 0, w: width, h: 8 }, { x: s.pad, y: footerTop - 16, w: inner, h: 1 }];
  const bodyBottom = footerTop - 32;

  // The story column: landscape puts it beside the chart, portrait above it.
  const colW = format === "landscape" ? 380 : inner;
  const story = (headlineSize: number, statSize: number, commit: boolean) => {
    const target: Line[] = [];
    const add = (...args: EmitArgs) => emit(target, ...args);
    let y = s.pad;
    y = add("kicker", [t.kicker], s.pad, y, s.kicker, 600, "accent") + s.kicker * 0.6;
    const head = wrap(t.headline, font(headlineSize, 600), colW, measure);
    y = add("headline", head, s.pad, y, headlineSize, 600, "text") + headlineSize * 0.5;
    const statLine = add("stat", [t.stat], s.pad, y, statSize, 600, "text");
    let after: number;
    const besideX = s.pad + measure(t.stat, font(statSize, 600)) + 32;
    if (format === "portrait" && width - s.pad - besideX >= 360) {
      // Unit and label sit beside the big number, aligned to its top.
      const w = width - s.pad - besideX;
      const u = add("statUnit", wrap(t.statUnit, font(s.statUnit, 600), w, measure), besideX, y + statSize * 0.1, s.statUnit, 600, "text");
      after = Math.max(statLine, add("statLabel", wrap(t.statLabel, font(s.statLabel), w, measure), besideX, u + 4, s.statLabel, 400, "muted"));
    } else {
      const u = add("statUnit", wrap(t.statUnit, font(s.statUnit, 600), colW, measure), s.pad, statLine + 4, s.statUnit, 600, "text");
      after = add("statLabel", wrap(t.statLabel, font(s.statLabel), colW, measure), s.pad, u + 2, s.statLabel, 400, "muted");
    }
    if (commit) lines.push(...target);
    return { bottom: after, headLines: head.length };
  };
  // Largest headline and statistic that fit: the text is never cut, the type gets smaller instead.
  const statFits = (size: number) => measure(t.stat, font(size, 600)) <= colW;
  const statSize = s.stat.find(statFits) ?? s.stat.at(-1)!;
  const limit = format === "landscape" ? bodyBottom : height * 0.42;
  const headlineSize = s.headline.find((h) => {
    const r = story(h, statSize, false);
    return r.headLines <= s.headlineMax && r.bottom <= limit;
  }) ?? s.headline.at(-1)!;
  const storyBottom = story(headlineSize, statSize, true).bottom;

  // Chart panel: title, chart, then context and caveat beneath it.
  const panelX = format === "landscape" ? s.pad + colW + 40 : s.pad;
  const panelW = width - s.pad - panelX;
  let y = format === "landscape" ? s.pad : storyBottom + 40;
  y = put("chartTitle", wrap(t.chartTitle, font(s.chartTitle, 600), panelW, measure), panelX, y, s.chartTitle, 600, "text") + 8;
  const contextLines = wrap(t.context, font(s.context), panelW, measure);
  const caveat = clamp(wrap(t.caveat, font(s.caveat), panelW, measure), s.caveatMax, font(s.caveat), panelW, measure);
  if (caveat.cut) truncated.push("caveat");
  const notesH = (contextLines.length * s.context + caveat.lines.length * s.caveat) * LEAD;
  const chart = { x: panelX, y, w: panelW, h: Math.floor(bodyBottom - notesH - 12 - y) };
  const notesY = put("context", contextLines, panelX, chart.y + chart.h + 12, s.context, 400, "muted");
  put("caveat", caveat.lines, panelX, notesY, s.caveat, 400, "muted");
  return { width, height, lines, chart, rules, truncated };
}
