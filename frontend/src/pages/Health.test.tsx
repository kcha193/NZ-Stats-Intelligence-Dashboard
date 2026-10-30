import { screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { resetSnapshotCache } from "@/api/static";
import health from "@/test/fixtures/health.json";
import { mockApi, renderWithProviders } from "@/test/mockApi";
import { opsStatus } from "@/test/opsStatus";
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

  describe("operations", () => {
    it("answers: is collection on, is the app working, what is next, is the data current", async () => {
      mockApi({ "/api/health": health, "/api/ops/status": opsStatus() });
      renderWithProviders(<Health />);
      expect(await screen.findByRole("heading", { level: 2, name: "Operations" })).toBeInTheDocument();
      expect(screen.getByText("OK.").closest("[data-level]")).toHaveAttribute("data-level", "ok");
      expect(screen.getByText(/Everything checked is within its limits/)).toBeInTheDocument();
      expect(screen.getByText("On")).toBeInTheDocument();
      expect(screen.getByText("Running")).toBeInTheDocument();
      expect(screen.getByText("Labour market statistics: September 2026 quarter")).toBeInTheDocument();
      const table = screen.getByRole("table", { name: /is each release current/i });
      expect(within(table).getByText("Current")).toBeInTheDocument();
      expect(screen.getByText("Nothing. Every check is within its limit.")).toBeInTheDocument();
    });

    it("says collection is off by choice, and does not call that a fault", async () => {
      mockApi({
        "/api/health": health,
        "/api/ops/status": opsStatus({
          collection: { mode: "disabled", summary: "Scheduled collection is deliberately off (started with --no-scheduler). Nothing is fetched until you run it." },
          calendar: { ...opsStatus().calendar, next_refresh_at: null },
        }),
      });
      renderWithProviders(<Health />);
      expect(await screen.findByText("Off (by choice)")).toBeInTheDocument();
      expect(screen.getByText(/deliberately off/)).toBeInTheDocument();
      expect(screen.getByText("Nothing. Every check is within its limit.")).toBeInTheDocument();
    });

    it("names the problem, how bad it is and what to do about it", async () => {
      mockApi({
        "/api/health": health,
        "/api/ops/status": opsStatus({
          overall: "critical",
          summary: "1 critical item(s) need action now.",
          process: { ...opsStatus().process, state: "stalled", heartbeat_age_seconds: 1200 },
          issues: [{
            key: "process:stalled", severity: "critical", category: "process",
            title: "The dashboard process is alive but has stopped reporting",
            detail: "Process 4242 has not updated its heartbeat for 20 min.",
            action: "Check the terminal running it, then stop and start it again.",
          }],
        }),
      });
      renderWithProviders(<Health />);
      expect(await screen.findByText(/Critical: The dashboard process is alive but has stopped reporting/)).toBeInTheDocument();
      expect(screen.getByText(/Check the terminal running it/)).toBeInTheDocument();
      expect(screen.getByText("Not responding")).toBeInTheDocument();
      expect(screen.getByText(/Critical\./).closest("[data-level]")).toHaveAttribute("data-level", "critical");
    });

    it("shows which release is overdue, and not merely which data is old", async () => {
      const base = opsStatus();
      mockApi({
        "/api/health": health,
        "/api/ops/status": opsStatus({
          overall: "attention",
          freshness: [{ ...base.freshness[0], state: "overdue", overdue: [{ release_key: "gdp-2026-09", published_at: "2026-12-17T10:45:00+13:00", hours_late: 9, status: "scheduled", last_outcome: null, last_error_class: null }] }],
        }),
      });
      renderWithProviders(<Health />);
      expect(await screen.findByText("Overdue: gdp-2026-09")).toBeInTheDocument();
      expect(screen.getByText(/An old reference period is normal until Stats NZ publishes again/)).toBeInTheDocument();
    });

    it("keeps the rest of the page when the operational status cannot be loaded", async () => {
      mockApi({ "/api/health": health }); // /api/ops/status answers 404
      renderWithProviders(<Health />);
      expect(await screen.findByText(/Operational status could not be loaded/)).toBeInTheDocument();
      expect(screen.getByRole("table", { name: /sources/i })).toBeInTheDocument();
    });

    it("never prints an em or en dash in its own copy", async () => {
      mockApi({ "/api/health": health, "/api/ops/status": opsStatus() });
      const { container } = renderWithProviders(<Health />);
      await screen.findByRole("heading", { level: 2, name: "Operations" });
      expect(container.textContent).not.toMatch(/[–—]/);
    });
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
      expect(screen.queryByRole("heading", { name: "Operations" })).not.toBeInTheDocument();
    });
  });
});
