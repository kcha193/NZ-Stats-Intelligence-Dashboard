import { useMemo } from "react";
import { ApiError } from "@/api/client";
import { useCpi, useEct, useOverview, useSeries } from "@/api/hooks";
import { buildCpiStories } from "./cpi";
import { buildEctStories } from "./ect";
import { orderStories } from "./engine";
import { buildMigrationStories } from "./migration";
import type { Story, StoryCategory } from "./types";

export type SourceState = "ready" | "loading" | "not_ingested" | "error";

type Q<T> = { data: T | undefined; error: Error | null; isLoading: boolean };

/** Any data means the category is usable; otherwise a 404 means "not ingested yet". */
const stateOf = (qs: Q<unknown>[]): SourceState => {
  if (qs.some((q) => q.isLoading)) return "loading";
  if (qs.some((q) => q.data !== undefined)) return "ready";
  if (qs.some((q) => q.error instanceof ApiError && q.error.status === 404)) return "not_ingested";
  return qs.some((q) => q.error) ? "error" : "ready";
};

/** Every story the ingested data supports, plus why a category has none. Categories load independently; `isLoading` is true while any is still loading. */
export function useStories(): { stories: Story[]; sources: Record<StoryCategory, SourceState>; isLoading: boolean; refetch: () => void } {
  const cpi = useCpi();
  const ect = useEct();
  const net = useSeries("mig.ry.net");
  const arrivals = useSeries("mig.ry.arrivals");
  const departures = useSeries("mig.ry.departures");
  const nz = useSeries("mig.ry.net.nz");
  const nonNz = useSeries("mig.ry.net.nonnz");
  // Only used to attach a release id and page to migration vintages; its failure never hides a story.
  const overview = useOverview();
  /** Retries only the requests that failed. */
  const refetch = () => {
    for (const q of [cpi, ect, net, arrivals, departures, nz, nonNz, overview]) if (q.error) void q.refetch();
  };
  const result = useMemo(() => {
    const migration = [net, arrivals, departures, nz, nonNz];
    const sources: Record<StoryCategory, SourceState> = {
      inflation: stateOf([cpi]),
      spending: stateOf([ect]),
      migration: overview.isLoading ? "loading" : stateOf(migration),
    };
    const releases = overview.data ? [...overview.data.latest_releases, ...(overview.data.featured ? [overview.data.featured.release] : [])] : [];
    // A category's stories appear once its sources have settled: built from half of them (migration before the release
    // summaries that carry its status, say) they would be shown and then change.
    const stories = orderStories([
      ...(cpi.data ? buildCpiStories(cpi.data) : []),
      ...(ect.data ? buildEctStories(ect.data) : []),
      ...buildMigrationStories({
        net: net.data, arrivals: arrivals.data, departures: departures.data, nz: nz.data, nonNz: nonNz.data, releases,
      }),
    ]).filter((s) => sources[s.category] !== "loading");
    return { stories, sources, isLoading: Object.values(sources).includes("loading") };
  }, [cpi, ect, overview, net, arrivals, departures, nz, nonNz]);
  return { ...result, refetch };
}
