import { screen, within } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockApi, renderWithProviders } from "@/test/mockApi";
import excerpt from "@/test/fixtures/research_synthetic_detail_excerpt.json";
import summary from "@/test/fixtures/research_synthetic_detail_summary.json";
import linkOnly from "@/test/fixtures/research_synthetic_detail_link_only.json";
import ResearchDetail from "./ResearchDetail";

// SYNTHETIC fixtures: fictional institutions served by the real API over seeded test data.
afterEach(() => vi.unstubAllGlobals());

const open = (id: number) =>
  renderWithProviders(<Routes><Route path="/economic-outlook/research/:id" element={<ResearchDetail />} /></Routes>, { route: `/economic-outlook/research/${id}` });

describe("research detail", () => {
  it("shows the document, the labelled AI interpretation, quotes, forecasts and provenance", async () => {
    mockApi({ [`/api/research/summaries/${excerpt.item.id}`]: excerpt });
    open(excerpt.item.id);
    expect(await screen.findByRole("heading", { level: 1, name: excerpt.item.document.title })).toBeInTheDocument();
    expect(screen.getByText("Harbourside Bank (synthetic)")).toBeInTheDocument();
    expect(screen.getByText("8 Oct 2026")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Read the original document/ })).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.getByText(/AI interpretation of the document\. Not an official statistic\./)).toBeInTheDocument();
    const outlook = screen.getByRole("region", { name: "Outlook" });
    expect(within(outlook).getByText(/Section 1, page 1/)).toBeInTheDocument();
    expect(within(outlook).getByText(/Annual CPI inflation is forecast to ease to 2\.3%/).tagName).toBe("BLOCKQUOTE");
    const table = screen.getByRole("table", { name: "Forecast claims in this document" });
    const scenario = within(table).getAllByRole("row").find((r) => r.textContent?.includes("Scenario: Downside"))!;
    expect(scenario).toHaveTextContent("1.6%");
    expect(scenario).toHaveTextContent("Weaker export prices");
    expect(screen.getByText(/fake-1 \(fake, run locally\)/)).toBeInTheDocument();
    expect(screen.getByText(/Version 1, stored .* \(current, summarised here\)/)).toBeInTheDocument();
    expect(document.title).toContain(excerpt.item.document.title);
  });

  it("shows evidence locations but no quotes when the source does not permit excerpts", async () => {
    mockApi({ [`/api/research/summaries/${summary.item.id}`]: summary });
    const { container } = open(summary.item.id);
    expect(await screen.findByText(/does not permit quoting/)).toBeInTheDocument();
    expect(screen.getAllByText(/Section \d+, page \d+/).length).toBeGreaterThan(0);
    expect(container.querySelector("blockquote")).toBeNull();
    expect(screen.getByText("43.5 % of GDP")).toBeInTheDocument();
  });

  it("shows only publication details for a link-only source", async () => {
    mockApi({ [`/api/research/summaries/${linkOnly.item.id}`]: linkOnly });
    open(linkOnly.item.id);
    expect(await screen.findByText("Link only")).toBeInTheDocument();
    expect(screen.queryByText(/AI interpretation/)).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Forecast claims" })).not.toBeInTheDocument();
  });

  it("says a summary is not published rather than showing an error", async () => {
    mockApi({});
    open(424242);
    expect(await screen.findByText("This research summary is not published here")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to the economic outlook" })).toHaveAttribute("href", "/economic-outlook");
  });

  it("does not request an address that is not a summary id", async () => {
    const fetch = mockApi({});
    renderWithProviders(<Routes><Route path="/economic-outlook/research/:id" element={<ResearchDetail />} /></Routes>, { route: "/economic-outlook/research/..%2Fadmin" });
    expect(await screen.findByText("This research summary is not published here")).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });
});
