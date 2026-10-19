import { screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { Route, Routes } from "react-router-dom";
import { Freshness } from "@/components/Freshness";
import calendar from "@/test/fixtures/calendar.json";
import cpi from "@/test/fixtures/cpi.json";
import health from "@/test/fixtures/health.json";
import overview from "@/test/fixtures/overview.json";
import { mockApi, renderWithProviders } from "@/test/mockApi";
import Calendar from "./Calendar";
import Overview from "./Overview";
import ReleaseAnalysis from "./ReleaseAnalysis";

vi.mock("@/charts/EChart", () => ({ EChart: () => null }));
const rel = cpi.analysis.release;

it("shows the verified annual CPI rate beside the other indicators and links the dashboard", async () => {
  const metric = cpi.analysis.headline_metrics[0];
  mockApi({
    "/api/overview": {
      ...overview,
      inactive_categories: overview.inactive_categories.filter((c) => c.name !== "Prices and inflation"),
      kpis: [...overview.kpis, { metric, release_id: rel.id, published_at: rel.published_at, source_url: rel.page_url }],
    },
  });
  renderWithProviders(<Overview />);
  const indicators = await screen.findByRole("region", { name: "Key indicators" });
  const tile = within(indicators).getByRole("article", { name: metric.label });
  expect(tile).toHaveTextContent("4.1%");
  expect(tile).toHaveTextContent("+1.0 percentage points");
  expect(tile).not.toHaveTextContent("n/a");
  expect(tile).toHaveTextContent("June 2026");
  expect(screen.getByRole("link", { name: "Explore inflation" })).toHaveAttribute("href", "/inflation");
  expect(screen.getByText(/Not yet active/)).not.toHaveTextContent("Prices and inflation");
});

it("renders CPI rates, percentage-point changes and index revisions with the right precision", async () => {
  mockApi({ [`/api/releases/${rel.id}`]: { release: rel, analysis: cpi.analysis, unavailable_reason: null } });
  renderWithProviders(<Routes><Route path="/releases/:id" element={<ReleaseAnalysis />} /></Routes>, { route: `/releases/${rel.id}` });
  const metrics = await screen.findByRole("table", { name: "Headline metrics" });
  expect(metrics).toHaveTextContent("4.1%");
  expect(metrics).toHaveTextContent("+1.0 percentage points");
  expect(metrics).not.toHaveTextContent("n/a)");
  const since = screen.getByRole("heading", { name: "Since the previous release" }).closest("section")!;
  expect(since).toHaveTextContent("3.1%");
  expect(since).toHaveTextContent("4.1%");
  const revisions = screen.getByRole("heading", { name: "Revision analysis" }).closest("section")!;
  expect(revisions).toHaveTextContent("1,338.50");
  expect(revisions).toHaveTextContent("1,339.64");
});

it("keeps a scheduled CPI release and links a published one to its analysis", async () => {
  const scheduled = { ...rel, id: rel.id + 1000, release_key: "consumers-price-index:september 2026 quarter", title: "Consumers price index: September 2026 quarter", period_label: "September 2026 quarter", status: "scheduled", published_at: "2099-10-22T10:45:00+13:00", has_analysis: false, headline: null, page_url: null };
  mockApi({ "/api/calendar": { ...calendar, items: [rel, scheduled] } });
  renderWithProviders(<Calendar />);
  const list = await screen.findByRole("list", { name: /releases/i });
  expect(within(list).getByRole("link", { name: rel.title })).toHaveAttribute("href", `/releases/${rel.id}`);
  const row = within(list).getByText(scheduled.title).closest("li")!;
  expect(row).toHaveTextContent("Scheduled");
  expect(within(row).queryByRole("link")).not.toBeInTheDocument();
});

it("names the CPI source in data freshness", () => {
  const source = { ...health.sources[3], source: "release:consumers-price-index" };
  renderWithProviders(<Freshness sources={[source]} />);
  expect(screen.getByText("Consumers price index releases")).toBeInTheDocument();
});
