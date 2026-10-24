import { screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { resetSnapshotCache } from "@/api/static";
import { renderWithProviders } from "@/test/mockApi";
import { SnapshotStamp } from "./SnapshotStamp";

const manifest = (over: Record<string, unknown> = {}) => ({
  schema_version: 1, origin: "production", snapshot_id: "a".repeat(64),
  generated_at: "2026-10-24T08:00:00Z", data_updated_at: "2026-10-22T20:04:11+13:00", ...over,
});
const serve = (m: unknown) =>
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(m), { status: 200, headers: { "content-type": "application/json" } })));

beforeEach(() => {
  resetSnapshotCache();
  vi.stubEnv("VITE_DATA_MODE", "static");
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("SnapshotStamp", () => {
  it("states when the data was last updated and that it is a snapshot, not a live feed", async () => {
    serve(manifest());
    renderWithProviders(<SnapshotStamp />);
    expect(await screen.findByText(/Data last updated 22 Oct 2026, 20:04 NZDT/)).toBeInTheDocument();
    expect(screen.getByText(/not a live feed/)).toBeInTheDocument();
    expect(screen.getByText(/Site refreshed 24 Oct 2026, 21:00 NZDT/)).toBeInTheDocument();
  });

  it("flags fixture data prominently", async () => {
    serve(manifest({ origin: "fixture" }));
    renderWithProviders(<SnapshotStamp />);
    expect(await screen.findByRole("note")).toHaveTextContent(/Test data built from fixture files/);
  });

  it("says so when nothing has been published", async () => {
    serve(manifest({ data_updated_at: null }));
    renderWithProviders(<SnapshotStamp />);
    expect(await screen.findByText("No data published yet")).toBeInTheDocument();
  });

  it("renders nothing while the manifest is unavailable", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("offline"); }));
    const { container } = renderWithProviders(<SnapshotStamp />);
    await new Promise((r) => setTimeout(r, 20));
    expect(container).toBeEmptyDOMElement();
  });
});
