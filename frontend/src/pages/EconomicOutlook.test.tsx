import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Kpi, Overview, ResearchFeed } from "@/api/types";
import { mockApi, renderWithProviders } from "@/test/mockApi";
import overview from "@/test/fixtures/overview.json";
import feed from "@/test/fixtures/research_synthetic_feed.json";
import forecasts from "@/test/fixtures/research_synthetic_forecasts.json";
import forecastsGdp from "@/test/fixtures/research_synthetic_forecasts_gdp.json";
import EconomicOutlook from "./EconomicOutlook";

// jsdom has no canvas: the chart is replaced by its accessible image, which carries the same description.
vi.mock("@/charts/EChart", () => ({ EChart: ({ ariaLabel }: { ariaLabel: string }) => <div role="img" aria-label={ariaLabel} /> }));

// Research fixtures are SYNTHETIC: fictional institutions served by the real API over seeded test data.
const CPI: Kpi = {
  release_id: 9, published_at: "2026-07-21T10:45:00+12:00", source_url: "https://www.stats.govt.nz/cpi",
  metric: {
    series_key: "cpi.index.nsa.all_groups", label: "CPI annual inflation, all groups", value: 4.058, unit: "percent",
    frequency: "quarterly", period: "2026-06", period_label: "Quarter ended June 2026", status: "final", std_error: null,
    change_prior: null, change_year_ago: { label: "vs June 2025 quarter (a year earlier)", comparison_period: "2025-06", previous: 2.658, absolute: 1.4, percent: null },
  },
};
const withCpi = { ...(overview as unknown as Overview), kpis: [...(overview as unknown as Overview).kpis, CPI] };

afterEach(() => vi.unstubAllGlobals());

const urls = (fn: ReturnType<typeof vi.fn>) => fn.mock.calls.map((c) => String(c[0]));

describe("Economic outlook, nothing published (the real default)", () => {
  it("shows the official pulse and a clear explanation instead of research", async () => {
    mockApi({ "/api/overview": withCpi }); // every /api/research/* answers 404, as the disabled API does
    renderWithProviders(<EconomicOutlook />);
    expect(await screen.findByRole("heading", { level: 1, name: "Economic outlook" })).toBeInTheDocument();
    const pulse = await screen.findByRole("list", { name: "Latest indicators" });
    expect(within(pulse).getByText("4.1%")).toBeInTheDocument();
    expect(within(pulse).getByText(/Consumer prices were 4\.1% higher than a year earlier/)).toBeInTheDocument();
    expect(within(pulse).getByRole("link", { name: "Explore migration" })).toHaveAttribute("href", "/migration");
    expect(await screen.findByText("No institutional research is published here yet")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem").some((li) => /A person approves it/.test(li.textContent ?? ""))).toBe(true);
    expect(await screen.findByText(/No forecasts are published here yet/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("never prints an em or en dash in its own copy", async () => {
    mockApi({ "/api/overview": withCpi });
    const { container } = renderWithProviders(<EconomicOutlook />);
    await screen.findByText("No institutional research is published here yet");
    expect(container.textContent).not.toMatch(/[–—]/);
  });
});

describe("Economic outlook with published research (SYNTHETIC)", () => {
  const routes = { "/api/overview": withCpi, "/api/research/feed": feed, "/api/research/forecasts": forecasts };

  it("lists each summary with its institution, date, AI label, review steps and links", async () => {
    mockApi(routes);
    renderWithProviders(<EconomicOutlook />);
    const entry = await screen.findByRole("article", { name: "Quarterly Economic Outlook, October 2026 (synthetic)" });
    expect(within(entry).getByText("Harbourside Bank (synthetic)")).toBeInTheDocument();
    expect(within(entry).getByText("Published 8 Oct 2026")).toBeInTheDocument();
    expect(within(entry).getByText(/AI interpretation of the document\. Not an official statistic\./)).toBeInTheDocument();
    expect(within(entry).getByText("Human reviewed 26 Oct 2026")).toBeInTheDocument();
    const original = within(entry).getByRole("link", { name: /Original document/ });
    expect(original).toHaveAttribute("href", "https://research.example.org/harbourside/quarterly-outlook");
    expect(original).toHaveAttribute("rel", "noopener noreferrer");
    expect(within(entry).getByRole("link", { name: "Evidence and 4 forecasts" })).toHaveAttribute("href", expect.stringMatching(/^\/economic-outlook\/research\/\d+$/));
  });

  it("shows a link-only source without any AI text", async () => {
    mockApi(routes);
    renderWithProviders(<EconomicOutlook />);
    const tasman = (await screen.findAllByRole("article")).find((a) => a.textContent?.includes("Tasman Markets"))!;
    expect(within(tasman).getByText(/permits a link and its publication details only/)).toBeInTheDocument();
    expect(within(tasman).queryByText(/AI interpretation/)).not.toBeInTheDocument();
    expect(within(tasman).queryByText(/keep easing/)).not.toBeInTheDocument();
    expect(within(tasman).queryByText("AI summary")).not.toBeInTheDocument();
    expect(within(tasman).getByRole("link", { name: "Publication details" })).toBeInTheDocument();
  });

  it("expands drivers, risks and uncertainty from the keyboard", async () => {
    mockApi(routes);
    const user = userEvent.setup();
    renderWithProviders(<EconomicOutlook />);
    const entry = (await screen.findAllByRole("article")).find((a) => a.textContent?.includes("Harbourside Bank"))!;
    const toggle = within(entry).getByRole("button", { name: /Show drivers, risks and uncertainty/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(within(entry).getByText(/China would weigh on dairy prices/)).not.toBeVisible();
    toggle.focus();
    await user.keyboard("{Enter}");
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(within(entry).getByText(/China would weigh on dairy prices/)).toBeVisible();
  });

  it("sends search, filter and sort to the API and resets to the first page", async () => {
    const fetch = mockApi(routes);
    const user = userEvent.setup();
    renderWithProviders(<EconomicOutlook />);
    await screen.findAllByRole("article");
    await user.selectOptions(screen.getByRole("combobox", { name: "Institution" }), "kauri");
    await waitFor(() => expect(urls(fetch).some((u) => u.includes("institution=kauri") && u.includes("offset=0"))).toBe(true));
    await user.type(screen.getByLabelText("Search titles and summaries"), "dairy");
    await waitFor(() => expect(urls(fetch).some((u) => u.includes("q=dairy"))).toBe(true));
    await user.click(screen.getByRole("radio", { name: "Oldest" }));
    await waitFor(() => expect(urls(fetch).some((u) => u.includes("sort=oldest"))).toBe(true));
  });

  it("groups by institution without changing what is shown", async () => {
    mockApi(routes);
    const user = userEvent.setup();
    renderWithProviders(<EconomicOutlook />);
    await screen.findAllByRole("article");
    expect(screen.getByRole("region", { name: "October 2026" })).toBeInTheDocument();
    await user.click(within(screen.getByRole("group", { name: "Group by" })).getByRole("radio", { name: "Institution" }));
    expect(screen.getByRole("region", { name: "Kauri Economics (synthetic)" })).toBeInTheDocument();
    expect(screen.getAllByRole("article")).toHaveLength(4);
  });

  it("explains an empty filter result and clears it", async () => {
    const empty: ResearchFeed = { ...(feed as unknown as ResearchFeed), items: [], total: 0 };
    mockApi({ ...routes, "/api/research/feed": empty });
    renderWithProviders(<EconomicOutlook />);
    expect(await screen.findByText("No research matches these filters.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Clear search and filters" })).toBeInTheDocument();
  });

  it("renders upstream text as text, never as markup", async () => {
    const hostile = structuredClone(feed) as unknown as ResearchFeed;
    hostile.items[0].outlook!.text = '<img src=x onerror="window.__pwned=1">Prices';
    hostile.items[0].document.title = "<script>window.__pwned=1</script>Title";
    hostile.items[0].document.url = "javascript:alert(1)";
    mockApi({ ...routes, "/api/research/feed": hostile });
    const { container } = renderWithProviders(<EconomicOutlook />);
    expect(await screen.findByText(/<img src=x onerror/)).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector('a[href^="javascript"]')).toBeNull();
  });

  it("shows an error, not an empty state, when the API fails", async () => {
    mockApi({ "/api/overview": withCpi, "/api/research/forecasts": forecasts, "/api/research/feed": () => { throw new Error("boom"); } });
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://localhost");
      if (url.pathname === "/api/research/feed") return new Response(JSON.stringify({ detail: "server error" }), { status: 500 });
      const body = url.pathname === "/api/overview" ? withCpi : forecasts;
      return new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
    }));
    renderWithProviders(<EconomicOutlook />);
    expect(await screen.findByRole("alert")).toHaveTextContent("server error");
    expect(screen.queryByText("No institutional research is published here yet")).not.toBeInTheDocument();
  });
});

describe("forecast comparison (SYNTHETIC)", () => {
  // Query-specific mocks first: a key without "?" matches its path with any query.
  const routes = {
    "/api/research/forecasts?indicator=gdp": forecastsGdp,
    "/api/research/forecasts?indicator=ocr": { ...forecasts, groups: [], excluded: [] },
    "/api/overview": withCpi, "/api/research/feed": feed, "/api/research/forecasts": forecasts,
  };

  it("compares CPI forecasts beside the latest official observation, with a table view", async () => {
    mockApi(routes);
    renderWithProviders(<EconomicOutlook />);
    const fig = await screen.findByRole("figure", { name: /CPI inflation, Year to June 2027/ });
    expect(within(fig).getByText(/Annual change \(through the year\), in percent\. Central forecasts\. 3 institutions/)).toBeInTheDocument();
    expect(within(fig).getByText(/Latest official observation: Stats NZ annual CPI inflation 4\.1%/)).toBeInTheDocument();
    expect(within(fig).getByText(/does not test any institution/)).toBeInTheDocument();
    const rows = within(within(fig).getByRole("table")).getAllByRole("row").slice(1);
    expect(rows.map((r) => within(r).getByRole("rowheader").textContent)).toEqual([
      "Harbourside Bank (synthetic)", "Kauri Economics (synthetic)", "Southern Treasury Office (synthetic)"]);
    expect(within(fig).getByRole("img")).toHaveAccessibleName(/Harbourside Bank \(synthetic\) 2\.3%/);
  });

  it("keeps scenarios apart from central forecasts", async () => {
    mockApi(routes);
    const user = userEvent.setup();
    renderWithProviders(<EconomicOutlook />);
    await screen.findByRole("figure", { name: /CPI inflation, Year to June 2027/ });
    expect(screen.queryByText(/Scenario: Downside/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "Scenarios" }));
    const fig = await screen.findByRole("figure", { name: /CPI inflation, Year to June 2027/ });
    expect(within(fig).getByText(/Scenario: Downside/)).toBeInTheDocument();
    expect(within(within(fig).getByRole("table")).getAllByRole("row")).toHaveLength(2);
  });

  it("puts GDP on two bases in two charts and explains what cannot be compared", async () => {
    mockApi(routes);
    const user = userEvent.setup();
    renderWithProviders(<EconomicOutlook />);
    await screen.findByRole("figure", { name: /CPI inflation/ });
    await user.click(screen.getByRole("radio", { name: "GDP" }));
    const figs = await screen.findAllByRole("figure", { name: /GDP, Year to March 2027/ });
    expect(figs).toHaveLength(2);
    expect(figs.map((f) => f.textContent)).toEqual([expect.stringContaining("Annual average change"), expect.stringContaining("Annual change (through the year)")]);
    expect(within(figs[1]).getByText(/Only one institution/)).toBeInTheDocument();
    expect(screen.queryByText(/Latest official observation/)).not.toBeInTheDocument(); // no official GDP series here
    const not = screen.getByText(/Not compared \(2\)/).closest("details")!;
    expect(within(not).getByText(/annual average or a change through the year/)).toBeInTheDocument();
    expect(within(not).getByText(/direction only/)).toBeInTheDocument();
  });

  it("says plainly when an indicator has no comparable forecast", async () => {
    mockApi(routes);
    const user = userEvent.setup();
    renderWithProviders(<EconomicOutlook />);
    await screen.findByRole("figure", { name: /CPI inflation/ });
    await user.click(screen.getByRole("radio", { name: "OCR" }));
    expect(await screen.findByText(/No central OCR forecasts can be compared/)).toBeInTheDocument();
  });
});
