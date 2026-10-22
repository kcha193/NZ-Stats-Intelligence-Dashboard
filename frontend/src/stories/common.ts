import type { ReleaseAnalysis, SeriesData } from "@/api/types";
import type { Provenance } from "./types";

export function provenanceOf(a: ReleaseAnalysis): Provenance {
  const r = a.release;
  return {
    releaseId: r.id, releaseKey: r.release_key, title: r.title, publishedAt: r.published_at,
    capturedAt: a.vintage_captured_at, pageUrl: r.page_url ?? null, status: r.status, seriesSlug: r.series_slug,
  };
}

/** Provenance for a story read from per-series endpoints, which carry the vintage but neither the release id nor its status. */
export function provenanceOfSeries(d: SeriesData, seriesSlug: string, releaseId: number | null, status: string): Provenance {
  return {
    releaseId, releaseKey: d.vintage.release_key, title: d.vintage.title, publishedAt: d.vintage.published_at,
    capturedAt: d.vintage.captured_at, pageUrl: null, status, seriesSlug,
  };
}

/** A correction is the first thing a reader must see, ahead of the story's own caveats. */
export function releaseCaveats(a: ReleaseAnalysis): string[] {
  return a.release.status === "corrected" ? [`Corrected release: ${a.corrections.note}`] : [];
}

/** For a release known only by its summary, which carries the status but not the correction note. */
export const statusCaveats = (status: string): string[] =>
  status === "corrected" ? ["Corrected release: Stats NZ corrected this release after first publishing it."] : [];

/** Two series from per-series endpoints may be combined only when one ingested bundle produced both. */
export const sameBundle = (a: SeriesData, b: SeriesData) =>
  a.vintage.release_key === b.vintage.release_key && a.vintage.captured_at === b.vintage.captured_at;
