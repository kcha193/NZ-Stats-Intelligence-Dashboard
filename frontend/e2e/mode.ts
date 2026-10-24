// The same browser specs run against the live app (FastAPI) and the published static site. These helpers cover the
// few places a spec talks to the data layer directly.
export const STATIC = process.env.E2E_MODE === "static";

/** Where links and exports should point: the canonical site on the published build, the page's own origin otherwise. */
export const exportedOrigin = (pageUrl: string) => (STATIC ? "https://nzstats.test" : new URL(pageUrl).origin);

type Envelope = { payload: unknown };

/** The data behind a live API path, from whichever layer is under test. */
export const dataUrl = (live: { path: string; file: string }) => (STATIC ? `/data/v1/${live.file}` : `/api/${live.path}`);
export const unwrap = <T>(body: unknown): T => (STATIC ? (body as Envelope).payload : body) as T;
export const rewrap = (body: unknown, payload: unknown) => (STATIC ? { ...(body as object), payload } : payload);
