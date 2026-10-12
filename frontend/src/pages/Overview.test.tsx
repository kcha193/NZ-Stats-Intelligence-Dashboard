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

  it("names the inactive categories rather than faking indicators", async () => {
    renderWithProviders(<Overview />);
    expect(await screen.findByText(/not yet active/i)).toHaveTextContent(/Prices and inflation/);
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
