import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import overview from "@/test/fixtures/overview.json";
import { mockApi, renderWithProviders } from "@/test/mockApi";
import series from "@/test/fixtures/series_net_ry.json";
import cpi from "@/test/fixtures/cpi.json";
import ect from "@/test/fixtures/ect.json";
import Overview from "./Overview";

vi.mock("@/charts/EChart", () => ({
  EChart: ({ ariaLabel }: { ariaLabel: string }) => <div role="img" aria-label={ariaLabel} />,
}));

describe("Overview", () => {
  beforeEach(() => {
    mockApi({ "/api/overview": overview, "/api/series/mig.ry.net": series });
  });

  it("answers the key question in the first screen: masthead, indicators, featured release, panels, freshness", async () => {
    renderWithProviders(<Overview />);
    expect(await screen.findByRole("heading", { level: 1, name: "New Zealand’s economy, explained." })).toBeInTheDocument();
    const kpis = screen.getByRole("region", { name: /key indicators/i });
    // One headline indicator per topic at first (this fixture has migration only); every indicator one click away.
    expect(within(kpis).getAllByRole("article")).toHaveLength(1);
    await userEvent.click(within(kpis).getByRole("button", { name: `Explore all ${overview.kpis.length} indicators` }));
    expect(within(kpis).getAllByRole("article")).toHaveLength(overview.kpis.length);
    expect(within(kpis).getByRole("button", { name: "Show headline indicators only" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("region", { name: /featured release/i })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /latest releases/i })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /upcoming releases/i })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /data freshness/i })).toBeInTheDocument();
  });

  it("puts each headline measure at a glance with its period, comparator, plain meaning and provisional status", async () => {
    renderWithProviders(<Overview />);
    const glance = await screen.findByRole("region", { name: "The economy at a glance" });
    const net = within(glance).getByRole("article", { name: "Net migration" });
    expect(net).toHaveTextContent("+20,350");
    expect(net).toHaveTextContent(/people, year-ended total.*, year ended July 2026/);
    expect(net).toHaveTextContent("Up from a net gain of 9,592 a year earlier");
    expect(net).toHaveTextContent("Over the year, 20,350 more migrants arrived than left.");
    expect(within(net).getByText("Provisional")).toBeInTheDocument();
    expect(within(net).getByRole("link", { name: "Net migration" })).toHaveAttribute("href", "/stories/migration-net-2026-07");
  });

  it("explains a term in place when it is selected", async () => {
    renderWithProviders(<Overview />);
    const glance = await screen.findByRole("region", { name: "The economy at a glance" });
    await userEvent.click(within(glance).getByRole("button", { name: /people, year-ended total: what does this mean/ }));
    expect(await screen.findByRole("dialog")).toHaveTextContent(/Long-term arrivals minus long-term departures|12 of the following 16 months/);
  });

  it("leads with the newest verified story, its number and a link to read it", async () => {
    // Migration (published 14 Sep) is newer than CPI (21 Jul), so it leads; CPI follows in the collection.
    mockApi({ "/api/overview": overview, "/api/series/mig.ry.net": series, "/api/cpi": cpi });
    renderWithProviders(<Overview />);
    const hero = await screen.findByRole("region", { name: "Annual net migration gain rises to 20,350" });
    expect(within(hero).getByRole("group", { name: "Key statistic" })).toHaveTextContent("+20,350");
    expect(within(hero).getByRole("link", { name: "Read the story" })).toHaveAttribute("href", "/stories/migration-net-2026-07");
    expect(within(hero).getByText(/Published 14 Sep 2026/)).toBeInTheDocument();
    expect(within(hero).getByText("Provisional")).toBeInTheDocument();
    const latest = screen.getByRole("list", { name: "Latest stories" });
    expect(within(latest).getAllByRole("article")[0]).toHaveTextContent("Annual inflation rises to 4.1%");
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
    await waitFor(() => expect(screen.queryByRole("status", { name: "Loading stories" })).not.toBeInTheDocument());
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

it("lays out all three topics: glance in reading order, the newest release as the lead, a varied collection and topic entrances", async () => {
  mockApi({ "/api/overview": overview, "/api/series/mig.ry.net": series, "/api/cpi": cpi, "/api/ect": ect });
  renderWithProviders(<Overview />);
  const glance = await screen.findByRole("region", { name: "The economy at a glance" });
  expect(within(glance).getAllByRole("article").map((a) => a.getAttribute("aria-labelledby"))).toEqual([
    "glance-inflation-annual-2026-06", "glance-spending-retail-2026-09", "glance-migration-net-2026-07",
  ]);
  expect(within(glance).getByRole("article", { name: "Inflation" })).toHaveTextContent("Consumer prices were 4.1% higher than a year earlier.");
  // Card spending (16 Oct) is the newest release, so it leads.
  expect(screen.getByRole("region", { name: "Retail card spending fell 0.4% in September 2026" })).toBeInTheDocument();
  const latest = screen.getByRole("list", { name: "Latest stories" });
  const first = within(latest).getAllByRole("article")[0];
  expect(first).not.toHaveTextContent("Consumer spending"); // the prominent slot avoids repeating the lead's topic
  const topics = screen.getByRole("region", { name: "Explore by topic" });
  expect(within(topics).getByRole("link", { name: "Explore inflation" })).toHaveAttribute("href", "/inflation");
  expect(within(topics).getByRole("link", { name: "2 stories" })).toHaveAttribute("href", "/stories?category=spending");
});
