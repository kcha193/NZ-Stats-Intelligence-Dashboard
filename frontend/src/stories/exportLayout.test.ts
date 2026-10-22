import { describe, expect, it } from "vitest";
import type { CpiDashboard, EctDashboard, SeriesData } from "@/api/types";
import cpi from "@/test/fixtures/cpi.json";
import ect from "@/test/fixtures/ect.json";
import arrivals from "@/test/fixtures/series_arrivals_ry.json";
import departures from "@/test/fixtures/series_departures_ry.json";
import net from "@/test/fixtures/series_net_ry.json";
import nonNz from "@/test/fixtures/series_net_nonnz_ry.json";
import nz from "@/test/fixtures/series_net_nz_ry.json";
import { buildCpiStories } from "./cpi";
import { buildEctStories } from "./ect";
import { exportText, layoutExport, FORMATS, type ExportFormat, type Measure } from "./exportLayout";
import { buildMigrationStories } from "./migration";
import type { Story } from "./types";

// A deterministic stand-in for canvas text metrics: a generous average glyph width.
const measure: Measure = (text, font) => text.length * Number(/(\d+)px/.exec(font)![1]) * 0.56;

const stories: Story[] = [
  ...buildCpiStories(cpi as unknown as CpiDashboard),
  ...buildEctStories(ect as unknown as EctDashboard),
  ...buildMigrationStories({
    net: net as SeriesData, arrivals: arrivals as SeriesData, departures: departures as SeriesData,
    nz: nz as SeriesData, nonNz: nonNz as SeriesData, releases: [],
  }),
];
const figure = { title: "Chart title", unit: "percent", caveat: "Shaded band is a reference only, not a forecast." };

const overlaps = (a: { x: number; y: number; w: number; h: number }, b: { x: number; y: number; w: number; h: number }) =>
  a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;

describe.each(Object.keys(FORMATS) as ExportFormat[])("%s export layout", (format) => {
  it.each(stories.map((s) => [s.id, s] as const))("%s fits the canvas without overlaps or lost text", (_, story) => {
    const text = exportText(story, figure, "https://example.test/stories/" + story.id);
    const l = layoutExport(text, format, measure);
    expect([l.width, l.height]).toEqual([FORMATS[format].width, FORMATS[format].height]);
    for (const b of l.lines) {
      expect(b.x).toBeGreaterThanOrEqual(0);
      expect(b.x + measure(b.text, b.font)).toBeLessThanOrEqual(l.width + 0.5);
      expect(b.y).toBeGreaterThanOrEqual(0);
      expect(b.y + b.size).toBeLessThanOrEqual(l.height);
      expect(overlaps({ x: b.x, y: b.y, w: measure(b.text, b.font), h: b.size }, l.chart)).toBe(false);
    }
    expect(l.chart.w).toBeGreaterThan(format === "landscape" ? 560 : 1000);
    expect(l.chart.h).toBeGreaterThan(format === "landscape" ? 300 : 600);
    const joined = (role: string) => l.lines.filter((b) => b.role === role).map((b) => b.text).join(" ");
    // The headline, the statistic and the source are never shortened.
    expect(joined("headline")).toBe(story.headline);
    expect(joined("stat")).toBe(story.stat.value);
    expect(joined("source")).toBe(text.source);
    expect(text.source).toContain(story.provenance.title);
    expect(text.source).toMatch(/published \d+ \w{3} \d{4}/);
    expect(text.context).toContain(story.referenceLabel);
    expect(joined("attribution")).toContain("NZ Stats Intelligence");
  });
});

it("shrinks a long headline rather than cutting it, and only ever truncates the caveat", () => {
  const story = { ...stories[0], headline: "A very long headline ".repeat(8).trim() };
  const text = exportText(story, { ...figure, caveat: "A long caveat. ".repeat(40) }, "https://example.test/x");
  const l = layoutExport(text, "landscape", measure);
  expect(l.lines.filter((b) => b.role === "headline").map((b) => b.text).join(" ")).toBe(story.headline);
  const caveat = l.lines.filter((b) => b.role === "caveat");
  expect(caveat.at(-1)!.text.endsWith("…")).toBe(true);
  expect(l.truncated).toEqual(["caveat"]);
});
