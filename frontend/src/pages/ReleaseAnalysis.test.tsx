import { screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { Route, Routes } from "react-router-dom";
import detail from "@/test/fixtures/release_detail.json";
import scheduled from "@/test/fixtures/release_scheduled.json";
import { mockApi, renderWithProviders } from "@/test/mockApi";
import ReleaseAnalysis from "./ReleaseAnalysis";

const ui = (
  <Routes>
    <Route path="/releases/:id" element={<ReleaseAnalysis />} />
  </Routes>
);

describe("ReleaseAnalysis", () => {
  beforeEach(() => {
    mockApi({
      [`/api/releases/${detail.release.id}`]: detail,
      [`/api/releases/${scheduled.release.id}`]: scheduled,
    });
  });

  it("answers the questions in order with source and methodology", async () => {
    renderWithProviders(ui, { route: `/releases/${detail.release.id}` });
    expect(await screen.findByRole("heading", { level: 1, name: new RegExp(detail.release.title) })).toBeInTheDocument();
    const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(headings).toEqual([
      "Executive summary", "Headline metrics", "Since the previous release",
      "Historical context", "Revision analysis", "Interpretation", "Source and methodology",
    ]);
    expect(screen.getByRole("link", { name: /view the original stats nz publication/i })).toHaveAttribute("href", expect.stringContaining("stats.govt.nz"));
  });

  it("separates revisions from the new reference period", async () => {
    renderWithProviders(ui, { route: `/releases/${detail.release.id}` });
    const section = (await screen.findByRole("heading", { name: "Since the previous release" })).closest("section")!;
    expect(within(section).getAllByText(/revision of/i).length).toBeGreaterThan(0);
    expect(within(section).getAllByText(/new reference period/i).length).toBeGreaterThan(0);
  });

  it("labels inference apart from observation", async () => {
    renderWithProviders(ui, { route: `/releases/${detail.release.id}` });
    const section = (await screen.findByRole("heading", { name: "Interpretation" })).closest("section")!;
    const inferences = detail.analysis!.interpretation.filter((i) => i.kind === "inference");
    expect(within(section).queryAllByText("Inference")).toHaveLength(inferences.length);
  });

  it("explains why there is no analysis for a scheduled release", async () => {
    renderWithProviders(ui, { route: `/releases/${scheduled.release.id}` });
    expect(await screen.findByText(new RegExp(scheduled.unavailable_reason!.slice(0, 20)))).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Executive summary" })).not.toBeInTheDocument();
  });

  it("handles an unknown release", async () => {
    renderWithProviders(ui, { route: "/releases/987654" });
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it.each(["abc", "1.5", "-3", "1e3"])("says the release was not found for the malformed id %s (review #4268065818)", async (id) => {
    const fetchSpy = mockApi({});
    renderWithProviders(ui, { route: `/releases/${id}` });
    expect(await screen.findByText(/release was not found/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /release calendar/i })).toHaveAttribute("href", "/calendar");
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("offers printing", async () => {
    renderWithProviders(ui, { route: `/releases/${detail.release.id}` });
    expect(await screen.findByRole("button", { name: /print/i })).toBeInTheDocument();
  });
});
