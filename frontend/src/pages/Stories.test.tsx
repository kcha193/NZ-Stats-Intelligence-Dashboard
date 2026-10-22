import { screen, within } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import cpi from "@/test/fixtures/cpi.json";
import ect from "@/test/fixtures/ect.json";
import overview from "@/test/fixtures/overview.json";
import arrivals from "@/test/fixtures/series_arrivals_ry.json";
import departures from "@/test/fixtures/series_departures_ry.json";
import net from "@/test/fixtures/series_net_ry.json";
import nonNz from "@/test/fixtures/series_net_nonnz_ry.json";
import nz from "@/test/fixtures/series_net_nz_ry.json";
import { mockApi, renderWithProviders } from "@/test/mockApi";
import Stories from "./Stories";
import StoryPage from "./Story";

vi.mock("@/charts/EChart", () => ({
  EChart: ({ ariaLabel }: { ariaLabel: string }) => <div role="img" aria-label={ariaLabel} />,
}));

const routes = (
  <Routes>
    <Route path="/stories" element={<Stories />} />
    <Route path="/stories/:id" element={<StoryPage />} />
  </Routes>
);

describe("Stories feed", () => {
  beforeEach(() => mockApi({ "/api/cpi": cpi, "/api/releases": [] }));

  it("lists every story the data supports, each with its finding, period and publication date", async () => {
    renderWithProviders(routes, { route: "/stories" });
    expect(await screen.findByRole("heading", { level: 1, name: "Stories" })).toBeInTheDocument();
    const list = await screen.findByRole("list", { name: "All stories" });
    const cards = within(list).getAllByRole("article");
    expect(cards).toHaveLength(3);
    const first = cards[0];
    expect(within(first).getByRole("link", { name: "Annual inflation rises to 4.1%" })).toHaveAttribute("href", "/stories/inflation-annual-2026-06");
    expect(first).toHaveTextContent("June 2026 quarter");
    expect(first).toHaveTextContent("Published 21 Jul 2026");
    expect(first).toHaveTextContent("Inflation and prices");
  });

  it("says which categories have no stories yet instead of inventing any", async () => {
    renderWithProviders(routes, { route: "/stories" });
    expect(await screen.findByText(/Consumer spending: no data has been ingested yet/)).toBeInTheDocument();
    expect(screen.getByText(/International migration: no data has been ingested yet/)).toBeInTheDocument();
  });

  it("filters by category from the URL", async () => {
    renderWithProviders(routes, { route: "/stories?category=spending" });
    expect(await screen.findByText(/No consumer spending stories are available/)).toBeInTheDocument();
    expect(screen.queryByRole("article")).not.toBeInTheDocument();
  });
});

describe("Story page", () => {
  beforeEach(() => mockApi({ "/api/cpi": cpi, "/api/releases": [] }));

  it("tells the whole story: headline, number, chart, explanation, context, evidence, source, dashboard", async () => {
    renderWithProviders(routes, { route: "/stories/inflation-annual-2026-06" });
    expect(await screen.findByRole("heading", { level: 1, name: "Annual inflation rises to 4.1%" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Key statistic" })).toHaveTextContent("4.1%annual change in the CPI");
    expect(screen.getByRole("img", { name: /Annual CPI inflation, last ten years/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "What the data shows" })).toBeInTheDocument();
    expect(screen.getByText("Annual inflation was last this high in the December 2023 quarter (4.7%).")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Values used in this story" })).toHaveTextContent("cpi.index.nsa.all_groups");
    const source = screen.getByRole("region", { name: "Source" });
    expect(within(source).getByRole("link", { name: /Consumers price index: June 2026 quarter/ })).toHaveAttribute(
      "href", "https://www.stats.govt.nz/information-releases/consumers-price-index-june-2026-quarter/");
    expect(source).toHaveTextContent("21 Jul 2026");
    expect(screen.getByRole("link", { name: "Explore the inflation dashboard" })).toHaveAttribute("href", "/inflation");
  });

  it("offers both presentation formats and copies the story link when the share sheet is unavailable", async () => {
    const writeText = vi.fn(async () => undefined);
    vi.stubGlobal("navigator", { ...navigator, share: undefined, clipboard: { writeText } });
    renderWithProviders(routes, { route: "/stories/inflation-annual-2026-06" });
    const group = await screen.findByRole("group", { name: "Export and share" });
    expect(within(group).getByRole("button", { name: /Landscape PNG \(1200 × 675\)/ })).toBeEnabled();
    expect(within(group).getByRole("button", { name: /Portrait PNG \(1200 × 1500\)/ })).toBeEnabled();
    within(group).getByRole("button", { name: /Share link/ }).click();
    expect(await screen.findByText("Link copied.")).toBeInTheDocument();
    expect(writeText).toHaveBeenCalledWith(`${window.location.origin}/stories/inflation-annual-2026-06`);
    vi.unstubAllGlobals();
  });

  it("switches the drivers chart between quarterly and annual contributions", async () => {
    renderWithProviders(routes, { route: "/stories/inflation-drivers-2026-06" });
    expect(await screen.findByRole("img", { name: /quarterly CPI change/ })).toBeInTheDocument();
    screen.getByRole("radio", { name: "Annual" }).click();
    expect(await screen.findByRole("img", { name: /annual CPI change/ })).toBeInTheDocument();
  });

  it("marks an older story address as superseded and links to the current one", async () => {
    renderWithProviders(routes, { route: "/stories/inflation-annual-2026-03" });
    expect(await screen.findByRole("heading", { name: /This story has been superseded/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Annual inflation rises to 4.1%" })).toHaveAttribute("href", "/stories/inflation-annual-2026-06");
    expect(screen.queryByRole("group", { name: "Key statistic" })).not.toBeInTheDocument();
  });

  it("explains an unknown story address", async () => {
    renderWithProviders(routes, { route: "/stories/inflation-annual-2031-06" });
    expect(await screen.findByRole("heading", { name: "Story not found" })).toBeInTheDocument();
  });

  it("names a year-ended period in lower case mid-sentence", async () => {
    mockApi({ ...ALL, "/api/releases": [{
      id: 41, release_key: "international-migration:august 2026", title: "International migration: August 2026",
      series_slug: "international-migration", category: "Migration", importance: "high", period_label: "August 2026",
      published_at: "2026-10-14T10:45:00+13:00", status: "published", headline: null, page_url: null, has_analysis: false,
    }] });
    renderWithProviders(routes, { route: "/stories/migration-net-2026-07" });
    expect(await screen.findByRole("note")).toHaveTextContent("so this story still shows the year ended July 2026.");
  });

  it("warns when Stats NZ has published a newer release that is not verified here yet", async () => {
    mockApi({
      "/api/cpi": cpi,
      "/api/releases": [{
        id: 40, release_key: "consumers-price-index:september 2026 quarter", title: "Consumers price index: September 2026 quarter",
        series_slug: "consumers-price-index", category: "Prices and inflation", importance: "high", period_label: "September 2026 quarter",
        published_at: "2026-10-22T10:45:00+13:00", status: "published", headline: null, page_url: null, has_analysis: false,
      }],
    });
    renderWithProviders(routes, { route: "/stories/inflation-annual-2026-06" });
    expect(await screen.findByRole("note")).toHaveTextContent(
      "Stats NZ published Consumers price index: September 2026 quarter on 22 Oct 2026. It has not been verified here yet, so this story still shows the June 2026 quarter.");
  });
});

const ALL = {
  "/api/cpi": cpi, "/api/ect": ect, "/api/overview": overview, "/api/releases": [],
  "/api/series/mig.ry.net": net, "/api/series/mig.ry.arrivals": arrivals, "/api/series/mig.ry.departures": departures,
  "/api/series/mig.ry.net.nz": nz, "/api/series/mig.ry.net.nonnz": nonNz,
};

describe("stories across categories", () => {
  it("orders all eight stories newest release first", async () => {
    mockApi(ALL);
    renderWithProviders(routes, { route: "/stories" });
    const list = await screen.findByRole("list", { name: "All stories" });
    const heads = within(list).getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(heads).toEqual([
      "Retail card spending fell 0.4% in September 2026",
      "Spending on fuel rose 2.9% in September 2026; hospitality fell 2.3%",
      "Annual net migration gain rises to 20,350",
      "Migrant arrivals rise 5.2% while departures fall 3.5%",
      "Net loss of New Zealand citizens is offset by a larger gain of other citizens",
      "Annual inflation rises to 4.1%",
      "Transport made the largest contribution to quarterly inflation of 1.5%",
      "Tradables inflation (4.9%) runs ahead of non-tradables (3.4%)",
    ]);
    expect(screen.queryByText(/no data has been ingested yet/)).not.toBeInTheDocument();
  });

  it("renders a card spending story with its release analysis link and a switch to the spending level", async () => {
    mockApi(ALL);
    renderWithProviders(routes, { route: "/stories/spending-retail-2026-09" });
    expect(await screen.findByRole("heading", { level: 1, name: "Retail card spending fell 0.4% in September 2026" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Key statistic" })).toHaveTextContent("\u22120.4%monthly change, seasonally adjusted");
    expect(screen.getByRole("img", { name: /monthly percentage change, last 24 months/ })).toBeInTheDocument();
    screen.getByRole("radio", { name: "Spending level" }).click();
    expect(await screen.findByText(/does not start at zero/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Full release analysis" })).toHaveAttribute("href", "/releases/2");
  });

  it("renders a provisional migration story and attaches the release from the overview", async () => {
    mockApi(ALL);
    renderWithProviders(routes, { route: "/stories/migration-citizenship-2026-07" });
    expect(await screen.findByRole("heading", { level: 1, name: /offset by a larger gain of other citizens/ })).toBeInTheDocument();
    expect(screen.getAllByText("Provisional").length).toBeGreaterThan(0);
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
    const source = screen.getByRole("region", { name: "Source" });
    expect(within(source).getByRole("link", { name: /International migration: July 2026/ })).toHaveAttribute(
      "href", "https://www.stats.govt.nz/information-releases/international-migration-july-2026/");
    expect(screen.getByRole("link", { name: "Explore the migration dashboard" })).toHaveAttribute("href", "/migration");
  });
});

describe("a corrected migration release", () => {
  const correctedOverview = {
    ...overview,
    latest_releases: overview.latest_releases.map((r) => (r.id === 2 ? { ...r, status: "corrected" } : r)),
    featured: overview.featured && { ...overview.featured, release: { ...overview.featured.release, status: "corrected" } },
  };

  it("is flagged on the feed card and on the story page's source", async () => {
    mockApi({ ...ALL, "/api/overview": correctedOverview });
    renderWithProviders(routes, { route: "/stories?category=migration" });
    const cards = within(await screen.findByRole("list", { name: "International migration stories" })).getAllByRole("article");
    expect(cards).toHaveLength(3);
    for (const card of cards) expect(card).toHaveTextContent(/corrected/i);
  });

  it("states the correction in the story's source and caveats", async () => {
    mockApi({ ...ALL, "/api/overview": correctedOverview });
    renderWithProviders(routes, { route: "/stories/migration-net-2026-07" });
    const source = await screen.findByRole("region", { name: "Source" });
    expect(source).toHaveTextContent("Corrected by Stats NZ");
    expect(screen.getByText(/Corrected release: Stats NZ corrected this release/)).toBeInTheDocument();
  });
});

describe("newer-release notice", () => {
  const release = (status: string) => ({
    id: 40, release_key: "consumers-price-index:september 2026 quarter", title: "Consumers price index: September 2026 quarter",
    series_slug: "consumers-price-index", category: "Prices and inflation", importance: "high", period_label: "September 2026 quarter",
    published_at: "2026-10-22T10:45:00+13:00", status, headline: null, page_url: null, has_analysis: false,
  });

  it.each(["published", "corrected"])("is shown for a %s release", async (status) => {
    mockApi({ "/api/cpi": cpi, "/api/releases": [release(status)] });
    renderWithProviders(routes, { route: "/stories/inflation-annual-2026-06" });
    expect(await screen.findByRole("note")).toHaveTextContent("Stats NZ published Consumers price index: September 2026 quarter");
  });

  it.each(["scheduled", "delayed", "unavailable"])("ignores a newer %s release whose date has passed and reports the published one", async (status) => {
    const notYetPublished = { ...release(status), id: 41, title: "Consumers price index: December 2026 quarter", published_at: "2026-10-23T08:00:00+13:00" };
    mockApi({ "/api/cpi": cpi, "/api/releases": [notYetPublished, release("published")] });
    renderWithProviders(routes, { route: "/stories/inflation-annual-2026-06" });
    const note = await screen.findByRole("note");
    expect(note).toHaveTextContent("Stats NZ published Consumers price index: September 2026 quarter on 22 Oct 2026");
    expect(note).not.toHaveTextContent("December 2026 quarter");
  });
});

/** Answers every request except those for `held`, which never settle: a source that is still loading. */
function holdBack(...held: string[]) {
  const fn = mockApi(ALL);
  const real = fn.getMockImplementation() as (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
  fn.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) =>
    held.includes(new URL(String(input), "http://localhost").pathname) ? new Promise<Response>(() => undefined) : real(input, init));
}

describe("categories that are ready do not wait for the others", () => {
  it("lists ready stories while another category is still loading, and says which", async () => {
    holdBack("/api/ect");
    renderWithProviders(routes, { route: "/stories" });
    const list = await screen.findByRole("list", { name: "All stories" });
    const headlines = within(list).getAllByRole("article").map((a) => a.textContent ?? "");
    expect(headlines).toHaveLength(6);
    expect(headlines.some((h) => h.includes("Annual inflation rises to 4.1%"))).toBe(true);
    expect(screen.getByRole("status")).toHaveTextContent("Still loading: Consumer spending.");
  });

  it("opens a deep-linked story as soon as its own category is ready", async () => {
    holdBack("/api/ect");
    renderWithProviders(routes, { route: "/stories/inflation-annual-2026-06" });
    expect(await screen.findByRole("heading", { level: 1, name: "Annual inflation rises to 4.1%" })).toBeInTheDocument();
  });

  it("keeps waiting, rather than reporting 'not found', for a story whose category is still loading", async () => {
    holdBack("/api/ect");
    renderWithProviders(routes, { route: "/stories/spending-retail-2026-09" });
    expect(await screen.findByRole("status", { name: "Loading" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Story not found" })).not.toBeInTheDocument();
  });

  it("does not show migration stories before the release summaries that carry their status have loaded", async () => {
    holdBack("/api/overview");
    renderWithProviders(routes, { route: "/stories" });
    const list = await screen.findByRole("list", { name: "All stories" });
    expect(within(list).getAllByRole("article")).toHaveLength(5);
    expect(list).not.toHaveTextContent("Annual net migration");
    expect(screen.getByRole("status")).toHaveTextContent("Still loading: International migration.");
  });

  it("filters the feed by a category that is still loading without calling it empty", async () => {
    holdBack("/api/ect");
    renderWithProviders(routes, { route: "/stories?category=spending" });
    expect(await screen.findByRole("status", { name: "Loading" })).toBeInTheDocument();
    expect(screen.queryByText(/No consumer spending stories are available/)).not.toBeInTheDocument();
  });
});
