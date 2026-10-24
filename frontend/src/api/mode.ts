/**
 * "live": the page talks to the FastAPI app that serves it (Docker, local development).
 * "static": the page reads validated JSON snapshots published next to it (Netlify). Set by `vite build --mode static`.
 */
export const isStaticMode = (): boolean => import.meta.env.VITE_DATA_MODE === "static";

/** Where the snapshot lives, relative to the site root. */
export const snapshotBase = (): string => (import.meta.env.VITE_SNAPSHOT_BASE as string | undefined) ?? "/data/v1";

/** A live dashboard refetches on a timer; a snapshot only changes when the site is redeployed. */
export const pollEvery = (ms: number): number | false => (isStaticMode() ? false : ms);
