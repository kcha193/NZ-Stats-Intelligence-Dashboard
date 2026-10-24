import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { resetSnapshotCache } from "@/api/static";
import health from "@/test/fixtures/health.json";
import { mockApi, renderWithProviders } from "@/test/mockApi";
import Health from "./Health";

describe("Health", () => {
  it("shows each source's state, recent ingestion runs and counts", async () => {
    mockApi({ "/api/health": health });
    renderWithProviders(<Health />);
    expect(await screen.findByRole("heading", { level: 1, name: /data health/i })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: /sources/i })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: /recent ingestion runs/i })).toBeInTheDocument();
    expect(screen.getByText(/series/i)).toBeInTheDocument();
  });

  it("makes failures understandable", async () => {
    mockApi({
      "/api/health": {
        ...health,
        sources: [{ source: "release:international-migration", state: "degraded", last_checked_at: "2026-10-14T10:50:00+13:00", last_success_at: null, detail: "validation_failed: [continuity] missing months" }],
        recent_runs: [{ release_key: "x", started_at: "2026-10-14T10:50:00+13:00", outcome: "failed", error_class: "validation_failed", detail: "[continuity] missing months" }],
      },
    });
    renderWithProviders(<Health />);
    expect(await screen.findAllByText(/validation_failed/)).not.toHaveLength(0);
    expect(screen.getByText(/last known good data is still being shown/i)).toBeInTheDocument();
  });

  describe("on the published site", () => {
    afterEach(() => vi.unstubAllEnvs());

    it("reports the snapshot's source freshness without a database flag or an ingestion log", async () => {
      vi.stubEnv("VITE_DATA_MODE", "static");
      resetSnapshotCache();
      const snapshot_id = "a".repeat(64);
      mockApi({
        "/data/v1/manifest.json": { schema_version: 1, origin: "production", snapshot_id, generated_at: "2026-10-24T08:00:00Z", data_updated_at: null },
        "/data/v1/health.json": { schema_version: 1, kind: "health", snapshot_id, payload: { ...health, recent_runs: [] } },
      });
      renderWithProviders(<Health />);
      expect(await screen.findByRole("table", { name: /sources/i })).toBeInTheDocument();
      expect(screen.queryByRole("table", { name: /recent ingestion runs/i })).not.toBeInTheDocument();
      expect(screen.queryByText(/Database (OK|unavailable)/)).not.toBeInTheDocument();
      expect(screen.getByText(/as of the last published snapshot/i)).toBeInTheDocument();
    });
  });
});
