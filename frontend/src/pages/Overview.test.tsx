import { screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import overview from "@/test/fixtures/overview.json";
import { mockApi, renderWithProviders } from "@/test/mockApi";
import series from "@/test/fixtures/series_net_ry.json";
import Overview from "./Overview";

vi.mock("@/charts/EChart", () => ({
  EChart: ({ ariaLabel }: { ariaLabel: string }) => <div role="img" aria-label={ariaLabel} />,
}));

describe("Overview", () => {
  beforeEach(() => {
    mockApi({ "/api/overview": overview, "/api/series/mig.ry.net": series });
  });

  it("answers the key question in the first screen: KPIs, featured release, panels, freshness", async () => {
    renderWithProviders(<Overview />);
    expect(await screen.findByRole("heading", { name: /economic overview/i })).toBeInTheDocument();
    const kpis = screen.getByRole("region", { name: /key indicators/i });
    expect(within(kpis).getAllByRole("article").length).toBeGreaterThanOrEqual(4);
    expect(screen.getByRole("region", { name: /featured release/i })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /latest releases/i })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /upcoming releases/i })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /data freshness/i })).toBeInTheDocument();
  });

  it("names the period and provisional status of the trend's latest value", async () => {
    renderWithProviders(<Overview />);
    const heading = await screen.findByRole("heading", { level: 3, name: /^Year-ended net migration:/ });
    expect(heading).toHaveTextContent("year ended Jul 2026, provisional");
  });

  it("names the inactive categories rather than faking indicators", async () => {
    renderWithProviders(<Overview />);
    expect(await screen.findByText(/not yet active/i)).toHaveTextContent(/Prices and inflation/);
  });

  it("shows a note instead of an error when no series has been ingested yet (review #4254034477)", async () => {
    // First run: `discover` has listed releases, but no backfill has stored any series.
    mockApi({ "/api/overview": { ...overview, kpis: [], featured: null } });
    renderWithProviders(<Overview />);
    expect(await screen.findByRole("region", { name: /upcoming releases/i })).toBeInTheDocument();
    expect(await screen.findByText(/trend appears once the first release has been ingested/i)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("still reports a genuine failure to load the trend", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const path = new URL(String(input), "http://localhost").pathname;
      return path === "/api/overview"
        ? new Response(JSON.stringify(overview), { status: 200, headers: { "content-type": "application/json" } })
        : new Response(JSON.stringify({ detail: "boom" }), { status: 500 });
    }));
    renderWithProviders(<Overview />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/could not be loaded/i);
  });

  it("explains an empty database", async () => {
    mockApi({
      "/api/overview": { generated_at: "2026-10-11T16:00:00+13:00", kpis: [], latest_releases: [], upcoming: [], freshness: [], featured: null, inactive_categories: [] },
    });
    renderWithProviders(<Overview />);
    expect(await screen.findByText(/no data has been ingested yet/i)).toBeInTheDocument();
  });

  it("shows an error with a retry when the API fails", async () => {
    mockApi({});
    renderWithProviders(<Overview />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });
});

it("uses the ingested data time when the response is generated days later", async () => {
  mockApi({ "/api/overview": { ...overview, generated_at: "2026-10-16T10:00:00+13:00", data_updated_at: "2026-10-11T16:00:00+13:00" }, "/api/series/mig.ry.net": series });
  renderWithProviders(<Overview />);
  expect(await screen.findByText(/Migration data ingested 11 Oct 2026, 16:00 NZDT/)).toBeInTheDocument();
  expect(screen.queryByText(/Updated 16 Oct/)).not.toBeInTheDocument();
});
