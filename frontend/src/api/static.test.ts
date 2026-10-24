import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "./client";
import { SnapshotUnavailableError, resetSnapshotCache, staticGetJson } from "./static";

const SID = "a".repeat(64);
const summary = (id: number, over: Record<string, unknown> = {}) => ({
  id, release_key: `k${id}`, title: `Release ${id}`, series_slug: "s", category: "Migration", importance: "high",
  period_label: null, published_at: "2026-10-15T10:45:00+13:00", status: "published", headline: null, page_url: null,
  has_analysis: true, ...over,
});

function env(kind: string, payload: unknown, snapshot_id = SID) {
  return { schema_version: 1, kind, snapshot_id, payload };
}

type Files = Record<string, unknown>;
function serve(files: Files, opts: { manifestId?: string } = {}) {
  const manifest = { schema_version: 1, origin: "production", snapshot_id: opts.manifestId ?? SID, generated_at: "2026-10-24T08:00:00Z", data_updated_at: "2026-10-22T20:04:11+13:00" };
  const all: Files = { "manifest.json": manifest, ...files };
  const fn = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), "https://example.test");
    const name = url.pathname.replace(/^\/data\/v1\//, "");
    if (!(name in all)) return new Response("<html>app</html>", { status: 404, headers: { "content-type": "text/html" } });
    return new Response(JSON.stringify(all[name]), { status: 200, headers: { "content-type": "application/json" } });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

beforeEach(() => {
  resetSnapshotCache();
  vi.stubEnv("VITE_DATA_MODE", "static");
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("static snapshot adapter", () => {
  it("serves an API path from the matching snapshot file and unwraps the envelope", async () => {
    const f = serve({ "overview.json": env("overview", { kpis: [] }) });
    expect(await staticGetJson("/api/overview")).toEqual({ kpis: [] });
    expect(f.mock.calls.map((c) => String(c[0]))).toEqual(["/data/v1/manifest.json", "/data/v1/overview.json"]);
  });

  it("fetches the manifest once per session", async () => {
    const f = serve({ "cpi.json": env("cpi", {}), "ect.json": env("ect", {}) });
    await staticGetJson("/api/cpi");
    await staticGetJson("/api/ect");
    expect(f.mock.calls.filter((c) => String(c[0]).endsWith("manifest.json"))).toHaveLength(1);
  });

  it("filters the release list by status, category, offset and limit, newest first", async () => {
    serve({
      "releases.json": env("releases", [
        summary(3, { category: "Migration" }), summary(2, { category: "Prices", status: "scheduled", has_analysis: false }),
        summary(1, { category: "Migration" }),
      ]),
    });
    expect((await staticGetJson<{ id: number }[]>("/api/releases?limit=200")).map((r) => r.id)).toEqual([3, 2, 1]);
    expect((await staticGetJson<{ id: number }[]>("/api/releases?category=Migration")).map((r) => r.id)).toEqual([3, 1]);
    expect((await staticGetJson<{ id: number }[]>("/api/releases?status=scheduled,delayed")).map((r) => r.id)).toEqual([2]);
    expect((await staticGetJson<{ id: number }[]>("/api/releases?limit=1&offset=1")).map((r) => r.id)).toEqual([2]);
  });

  it("serves release details by id and treats a bad or unknown id as not found", async () => {
    serve({ "releases/7.json": env("release", { release: summary(7) }) });
    expect(await staticGetJson("/api/releases/7")).toEqual({ release: summary(7) });
    await expect(staticGetJson("/api/releases/8")).rejects.toMatchObject({ status: 404 });
    await expect(staticGetJson("/api/releases/abc")).rejects.toMatchObject({ status: 404 });
  });

  it("windows the calendar by whole Auckland days, inclusive, oldest first", async () => {
    serve({
      "releases.json": env("releases", [
        summary(4, { published_at: "2026-11-01T10:45:00+13:00" }),
        summary(3, { published_at: "2026-10-31T23:30:00+13:00" }),
        summary(2, { published_at: "2026-10-01T00:00:00+13:00" }),
        summary(1, { published_at: "2026-09-30T23:59:00+13:00" }),
      ]),
      "calendar.json": env("calendar", { last_checked_at: "c", last_success_at: "s" }),
    });
    const out = await staticGetJson<{ items: { id: number }[]; last_success_at: string }>(
      "/api/calendar?from=2026-10-01&to=2026-10-31",
    );
    expect(out.items.map((i) => i.id)).toEqual([2, 3]);
    expect(out.last_success_at).toBe("s");
  });

  it("defaults the calendar to 45 days back and 90 days ahead of today in Auckland", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-24T08:00:00Z")); // 21:00 NZDT, 24 Oct
    try {
      serve({
        "releases.json": env("releases", [
          summary(3, { published_at: "2027-01-22T10:00:00+13:00" }), // 90 days ahead: included
          summary(2, { published_at: "2027-01-23T10:00:00+13:00" }), // 91 days ahead: excluded
          summary(1, { published_at: "2026-09-09T10:00:00+12:00" }), // 45 days back: included
          summary(0, { published_at: "2026-09-08T10:00:00+12:00" }), // 46 days back: excluded
        ]),
        "calendar.json": env("calendar", { last_checked_at: null, last_success_at: null }),
      });
      const out = await staticGetJson<{ items: { id: number }[] }>("/api/calendar");
      expect(out.items.map((i) => i.id)).toEqual([1, 3]);
    } finally {
      vi.useRealTimers();
    }
  });

  it("serves series and revisions for the latest vintage only", async () => {
    serve({ "series/mig.m.net.json": env("series", { points: [] }), "revisions/mig.m.net.json": env("revisions", { rows: [] }) });
    expect(await staticGetJson("/api/series/mig.m.net")).toEqual({ points: [] });
    expect(await staticGetJson("/api/series/mig.m.net?vintage=latest")).toEqual({ points: [] });
    await expect(staticGetJson("/api/series/mig.m.net?vintage=other-release")).rejects.toMatchObject({ status: 404 });
    expect(await staticGetJson("/api/revisions/mig.m.net")).toEqual({ rows: [] });
    await expect(staticGetJson("/api/revisions/mig.m.net?base=x")).rejects.toMatchObject({ status: 404 });
  });

  it("serves only the published country window", async () => {
    serve({ "migration/countries.json": env("countries", { months: 12 }) });
    expect(await staticGetJson("/api/migration/countries?months=12&top=15")).toEqual({ months: 12 });
    await expect(staticGetJson("/api/migration/countries?months=6&top=15")).rejects.toMatchObject({ status: 404 });
  });

  it("rejects a path the snapshot does not contain with a 404 ApiError", async () => {
    serve({});
    await expect(staticGetJson("/api/nope")).rejects.toBeInstanceOf(ApiError);
    await expect(staticGetJson("/api/series/../../etc")).rejects.toMatchObject({ status: 404 });
  });

  it("turns a missing data file into a 404, as the live API does for data not ingested yet", async () => {
    serve({});
    await expect(staticGetJson("/api/cpi")).rejects.toMatchObject({ status: 404 });
  });

  it("treats an HTML page served in place of JSON as unavailable, never as data", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<!doctype html>", { status: 200, headers: { "content-type": "text/html" } })));
    await expect(staticGetJson("/api/cpi")).rejects.toBeInstanceOf(SnapshotUnavailableError);
  });

  it("is unavailable, with a message safe to show, when the manifest cannot be fetched", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    const err = await staticGetJson("/api/cpi").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(SnapshotUnavailableError);
    expect((err as ApiError).status).toBe(503);
    expect((err as Error).message).not.toMatch(/fetch/i);
  });

  it("rejects an unsupported schema version", async () => {
    const f = serve({ "cpi.json": env("cpi", {}) });
    f.mockImplementationOnce(async () => new Response(JSON.stringify({ schema_version: 99 }), { status: 200, headers: { "content-type": "application/json" } }));
    await expect(staticGetJson("/api/cpi")).rejects.toBeInstanceOf(SnapshotUnavailableError);
  });

  it("rejects a file from a different snapshot than the manifest after one forced reload", async () => {
    const f = serve({ "cpi.json": env("cpi", {}, "b".repeat(64)) });
    await expect(staticGetJson("/api/cpi")).rejects.toBeInstanceOf(SnapshotUnavailableError);
    // manifest + file, then a cache-bypassing retry of both
    expect(f.mock.calls.length).toBeGreaterThanOrEqual(4);
  });

  it("recovers when a new deploy replaced the data between the manifest and the file", async () => {
    const stale = "b".repeat(64);
    let manifestCalls = 0;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const name = String(input).replace("/data/v1/", "");
      const json = (b: unknown) => new Response(JSON.stringify(b), { status: 200, headers: { "content-type": "application/json" } });
      if (name === "manifest.json") return json({ schema_version: 1, origin: "production", snapshot_id: manifestCalls++ === 0 ? stale : SID });
      return json(env("cpi", { ok: true }));
    }));
    const changed = vi.fn();
    const { onSnapshotChange } = await import("./static");
    onSnapshotChange(changed);
    expect(await staticGetJson("/api/cpi")).toEqual({ ok: true });
    expect(changed).toHaveBeenCalled();
  });

  it("rejects an envelope of the wrong kind", async () => {
    serve({ "cpi.json": env("ect", {}) });
    await expect(staticGetJson("/api/cpi")).rejects.toBeInstanceOf(SnapshotUnavailableError);
  });

  it("keeps the shared manifest alive when the request that started it is cancelled", async () => {
    serve({ "cpi.json": env("cpi", { ok: 1 }), "ect.json": env("ect", { ok: 2 }) });
    const first = new AbortController();
    const cancelled = staticGetJson("/api/cpi", first.signal).catch((e: unknown) => e);
    first.abort();
    expect(((await cancelled) as Error).name).toBe("AbortError");
    expect(await staticGetJson("/api/ect")).toEqual({ ok: 2 }); // a later caller is unaffected
  });

  it("reloads the manifest once when several files arrive from a newer deploy at the same time", async () => {
    const stale = "b".repeat(64);
    let manifestCalls = 0;
    const f = vi.fn(async (input: RequestInfo | URL) => {
      const name = String(input).replace("/data/v1/", "");
      const json = (b: unknown) => new Response(JSON.stringify(b), { status: 200, headers: { "content-type": "application/json" } });
      if (name === "manifest.json") {
        manifestCalls += 1;
        return json({ schema_version: 1, origin: "production", snapshot_id: manifestCalls === 1 ? stale : SID });
      }
      return json(env(name.replace(".json", ""), { ok: name }));
    });
    vi.stubGlobal("fetch", f);
    await Promise.all([staticGetJson("/api/cpi"), staticGetJson("/api/ect"), staticGetJson("/api/overview")]);
    expect(manifestCalls).toBe(2); // the first (stale) and one shared reload, not one per file
  });

  it("drops releases from the overview's upcoming list once their time has passed", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-24T08:00:00Z"));
    try {
      serve({
        "overview.json": env("overview", {
          upcoming: [
            summary(1, { published_at: "2026-10-20T10:45:00+13:00", status: "scheduled" }),
            summary(2, { published_at: "2026-10-28T10:45:00+13:00", status: "scheduled" }),
          ],
          latest_releases: [summary(9)],
        }),
      });
      const o = await staticGetJson<{ upcoming: { id: number }[]; latest_releases: unknown[] }>("/api/overview");
      expect(o.upcoming.map((r) => r.id)).toEqual([2]);
      expect(o.latest_releases).toHaveLength(1);
    } finally {
      vi.useRealTimers();
    }
  });
});
