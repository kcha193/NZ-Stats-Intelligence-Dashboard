import type { CpiDashboard, EctDashboard, Overview, SeriesData } from "@/api/types";
import { buildCpiStories } from "./cpi";
import { buildEctStories } from "./ect";
import { orderStories } from "./engine";
import { buildMigrationStories } from "./migration";
import type { Story } from "./types";

export type StorySources = {
  cpi?: CpiDashboard;
  ect?: EctDashboard;
  overview?: Overview;
  net?: SeriesData;
  arrivals?: SeriesData;
  departures?: SeriesData;
  nz?: SeriesData;
  nonNz?: SeriesData;
};

/** Every story the loaded data supports, newest first. Used by the running app and by the build-time page metadata. */
export function composeStories(s: StorySources): Story[] {
  const o = s.overview;
  const releases = o ? [...o.latest_releases, ...(o.featured ? [o.featured.release] : [])] : [];
  return orderStories([
    ...(s.cpi ? buildCpiStories(s.cpi) : []),
    ...(s.ect ? buildEctStories(s.ect) : []),
    ...buildMigrationStories({
      net: s.net, arrivals: s.arrivals, departures: s.departures, nz: s.nz, nonNz: s.nonNz, releases,
    }),
  ]);
}
