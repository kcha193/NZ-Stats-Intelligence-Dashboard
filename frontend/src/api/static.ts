import { ApiError } from "./errors";
import { snapshotBase } from "./mode";

/**
 * Reads the published snapshot and answers the same URLs the live API does, so no hook or page changes.
 *
 * Every file is an envelope `{schema_version, kind, snapshot_id, payload}` and must belong to the same snapshot as the
 * manifest. A CDN that serves half of a new deploy therefore produces a clear "unavailable" state (after one forced
 * reload) instead of numbers from two different releases on one page.
 */

const SCHEMA_VERSION = 1;
const UNAVAILABLE = "The latest published data could not be loaded. Please try again shortly.";
const DEFAULT_LIMIT = 50;
const CALENDAR_BACK_DAYS = 45;
const CALENDAR_AHEAD_DAYS = 90;
const TZ = "Pacific/Auckland";

/** The snapshot cannot be read or fails its consistency checks. Message is safe to show; details are logged. */
export class SnapshotUnavailableError extends ApiError {
  constructor(detail?: string) {
    super(503, UNAVAILABLE);
    this.name = "SnapshotUnavailableError";
    if (detail) console.warn(`snapshot unavailable: ${detail}`);
  }
}

export type Manifest = {
  schema_version: number;
  origin: "production" | "fixture";
  snapshot_id: string;
  generated_at: string;
  data_updated_at: string | null;
  attribution?: { source: string; url: string; licence: string; licence_url: string; note: string };
};

let manifestPromise: Promise<Manifest> | null = null;
let reloading: Promise<Manifest> | null = null;
const listeners = new Set<() => void>();

export const resetSnapshotCache = () => {
  manifestPromise = null;
  reloading = null;
  listeners.clear();
};

/** Called when the manifest changes under a running page (a new deploy), so cached data can be refetched. */
export const onSnapshotChange = (fn: () => void) => {
  listeners.add(fn);
  return () => listeners.delete(fn);
};

const url = (name: string) => `${snapshotBase()}/${name}`;
const isJson = (res: Response) => (res.headers.get("content-type") ?? "").includes("json");
const aborted = () => new DOMException("The operation was aborted.", "AbortError");

async function fetchEnvelope(name: string, signal: AbortSignal | undefined, reload: boolean): Promise<Response> {
  try {
    return await fetch(url(name), { signal, cache: reload ? "reload" : "no-cache", headers: { Accept: "application/json" } });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new SnapshotUnavailableError(`${name}: ${(e as Error).message}`);
  }
}

/** The manifest is tiny and shared by every request, so it is fetched without any one caller's AbortSignal. */
async function loadManifest(reload: boolean): Promise<Manifest> {
  const res = await fetchEnvelope("manifest.json", undefined, reload);
  if (!res.ok || !isJson(res)) throw new SnapshotUnavailableError(`manifest HTTP ${res.status}`);
  const m = (await res.json()) as Partial<Manifest>;
  if (m.schema_version !== SCHEMA_VERSION || typeof m.snapshot_id !== "string") {
    throw new SnapshotUnavailableError(`unsupported manifest ${String(m.schema_version)}`);
  }
  return m as Manifest;
}

/** A caller still stops waiting when its own signal aborts, without cancelling the shared request. */
function untilAborted<T>(p: Promise<T>, signal: AbortSignal | undefined): Promise<T> {
  if (!signal) return p;
  if (signal.aborted) return Promise.reject(aborted());
  return new Promise<T>((resolve, reject) => {
    const onAbort = () => reject(aborted());
    signal.addEventListener("abort", onAbort, { once: true });
    p.then(resolve, reject).finally(() => signal.removeEventListener("abort", onAbort));
  });
}

export function getManifest(signal?: AbortSignal, reload = false): Promise<Manifest> {
  if (reload) {
    if (!reloading) {
      const previous = manifestPromise;
      const next = loadManifest(true);
      reloading = next;
      manifestPromise = next;
      const done = () => {
        if (reloading === next) reloading = null;
      };
      next.then(
        async (m) => {
          done();
          if (previous && (await previous.catch(() => null))?.snapshot_id !== m.snapshot_id) for (const fn of listeners) fn();
        },
        () => {
          done();
          if (manifestPromise === next) manifestPromise = null; // a failure is not cached
        },
      );
    }
    return untilAborted(reloading ?? manifestPromise!, signal);
  }
  if (!manifestPromise) {
    const next = loadManifest(false);
    manifestPromise = next;
    next.catch(() => {
      if (manifestPromise === next) manifestPromise = null;
    });
  }
  return untilAborted(manifestPromise, signal);
}

type Resolved = { file: string; kind: string; shape: "list" | "object" };

const notFound = (what = "not found") => new ApiError(404, what);

/** Which snapshot file answers an API path. `null` = the API has an answer the snapshot deliberately does not publish. */
function route(path: string, q: URLSearchParams): Resolved | null {
  const seg = path.split("/").filter(Boolean); // ["api", ...]
  const [, a, b, c] = seg;
  if (seg[0] !== "api" || seg.some((s) => s === ".." || s === ".")) return null;
  const only = (n: number) => seg.length === n;
  if (a === "overview" && only(2)) return { file: "overview.json", kind: "overview", shape: "object" };
  if (a === "cpi" && only(2)) return { file: "cpi.json", kind: "cpi", shape: "object" };
  if (a === "ect" && only(2)) return { file: "ect.json", kind: "ect", shape: "object" };
  if (a === "health" && only(2)) return { file: "health.json", kind: "health", shape: "object" };
  if (a === "releases" && only(2)) return { file: "releases.json", kind: "releases", shape: "list" };
  if (a === "releases" && only(3) && /^\d+$/.test(b)) return { file: `releases/${b}.json`, kind: "release", shape: "object" };
  if (a === "series" && only(3) && /^[\w.-]+$/.test(b)) {
    const v = q.get("vintage");
    if (v && v !== "latest") return null;
    return { file: `series/${b}.json`, kind: "series", shape: "object" };
  }
  if (a === "revisions" && only(3) && /^[\w.-]+$/.test(b)) {
    if (q.get("base") || q.get("compare")) return null;
    return { file: `revisions/${b}.json`, kind: "revisions", shape: "object" };
  }
  if (a === "migration" && b === "countries" && only(3) && c === undefined) {
    if (Number(q.get("months") ?? 12) !== 12 || Number(q.get("top") ?? 15) !== 15) return null;
    return { file: "migration/countries.json", kind: "countries", shape: "object" };
  }
  return null;
}

async function readFile<T>(r: Resolved, signal: AbortSignal | undefined): Promise<T> {
  for (const reload of [false, true]) {
    const manifest = await getManifest(signal, reload);
    const res = await fetchEnvelope(r.file, signal, reload);
    if (res.status === 404) throw notFound("not published");
    if (!res.ok || !isJson(res)) throw new SnapshotUnavailableError(`${r.file} HTTP ${res.status}`);
    const env = (await res.json()) as { schema_version?: number; kind?: string; snapshot_id?: string; payload?: unknown };
    if (env.schema_version !== SCHEMA_VERSION || env.kind !== r.kind) throw new SnapshotUnavailableError(`${r.file}: wrong envelope`);
    const shapeOk = r.shape === "list" ? Array.isArray(env.payload) : typeof env.payload === "object" && env.payload !== null && !Array.isArray(env.payload);
    if (!shapeOk) throw new SnapshotUnavailableError(`${r.file}: wrong payload shape`);
    if (env.snapshot_id === manifest.snapshot_id) return env.payload as T;
    // Mixed snapshots (a deploy landed between the two requests, or a stale cache): retry once bypassing caches.
  }
  throw new SnapshotUnavailableError(`${r.file}: belongs to a different snapshot than the manifest`);
}

const aklToday = (now: Date): string => new Intl.DateTimeFormat("en-CA", { timeZone: TZ }).format(now);
const addDays = (day: string, n: number): string => {
  const d = new Date(`${day}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
};

type Summary = { id: number; published_at: string; status: string; category: string };

function listReleases(all: Summary[], q: URLSearchParams): Summary[] {
  const statuses = (q.get("status") ?? "").split(",").filter(Boolean);
  const limit = Math.min(Math.max(Number(q.get("limit") ?? DEFAULT_LIMIT) || DEFAULT_LIMIT, 1), 200);
  const offset = Math.max(Number(q.get("offset") ?? 0) || 0, 0);
  const category = q.get("category");
  return all
    .filter((r) => (statuses.length === 0 || statuses.includes(r.status)) && (!category || r.category === category))
    .slice(offset, offset + limit);
}

/** `published_at` is an Auckland ISO string, so its first ten characters are the Auckland calendar day. */
function calendarWindow(all: Summary[], q: URLSearchParams, now: Date): Summary[] {
  const today = aklToday(now);
  const from = q.get("from") ?? addDays(today, -CALENDAR_BACK_DAYS);
  const to = q.get("to") ?? addDays(today, CALENDAR_AHEAD_DAYS);
  return all
    .filter((r) => r.published_at.slice(0, 10) >= from && r.published_at.slice(0, 10) <= to)
    .sort((a, b) => (a.published_at === b.published_at ? a.id - b.id : a.published_at < b.published_at ? -1 : 1));
}

/** The snapshot lists what was upcoming when it was exported; a release whose time has passed is not "next" any more. */
function stillUpcoming<O extends { upcoming?: Summary[] }>(overview: O, now: Date): O {
  if (!Array.isArray(overview.upcoming)) return overview;
  return { ...overview, upcoming: overview.upcoming.filter((r) => Date.parse(r.published_at) >= now.getTime()) };
}

export async function staticGetJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const { pathname, searchParams } = new URL(path, "https://snapshot.invalid");
  if (pathname === "/api/calendar") {
    const [all, meta] = await Promise.all([
      readFile<Summary[]>({ file: "releases.json", kind: "releases", shape: "list" }, signal),
      readFile<{ last_checked_at: string | null; last_success_at: string | null }>(
        { file: "calendar.json", kind: "calendar", shape: "object" }, signal),
    ]);
    return { items: calendarWindow(all, searchParams, new Date()), ...meta } as T;
  }
  const resolved = route(pathname, searchParams);
  if (!resolved) throw notFound("not published in the static site");
  const payload = await readFile<T>(resolved, signal);
  if (resolved.file === "releases.json") return listReleases(payload as Summary[], searchParams) as T;
  if (resolved.file === "overview.json") return stillUpcoming(payload as { upcoming?: Summary[] }, new Date()) as T;
  return payload;
}
