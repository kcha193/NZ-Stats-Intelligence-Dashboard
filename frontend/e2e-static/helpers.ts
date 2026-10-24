import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

const DIST = path.resolve(import.meta.dirname, "../dist-static");

/** Dashboards and listings that exist on the published site. */
export const PAGES = ["/", "/stories", "/inflation", "/electronic-card-transactions", "/migration", "/calendar", "/health"];

/** Story addresses the build prerendered, read from the build output so the list cannot go stale. */
export const STORIES = readdirSync(path.join(DIST, "_pages/stories"))
  .filter((f) => f.endsWith(".html"))
  .map((f) => `/stories/${f.replace(/\.html$/, "")}`);

/** A release that has an analysis, as the snapshot lists them. */
export function analysedReleasePath(): string {
  const list = JSON.parse(readFileSync(path.join(DIST, "data/v1/releases.json"), "utf8")).payload as { id: number; has_analysis: boolean }[];
  const first = list.find((r) => r.has_analysis);
  if (!first) throw new Error("the snapshot has no release with an analysis");
  return `/releases/${first.id}`;
}

export const ALL_ROUTES = () => [...PAGES, ...STORIES, analysedReleasePath()];

export const SITE_URL = "https://nzstats.test";
