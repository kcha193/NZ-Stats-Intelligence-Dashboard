import { screen, within } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import cpi from "@/test/fixtures/cpi.json";
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
