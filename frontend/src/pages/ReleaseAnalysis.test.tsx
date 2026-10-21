import { screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
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
      "Historical context", "Revision analysis", "Corrections within this publication", "Interpretation", "Source and methodology",
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

  it.each(["abc", "1.5", "-3", "1e3", "9007199254740993", "9".repeat(400), "0"])("says the release was not found for the malformed id %s (review #4268065818)", async (id) => {
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

it("labels standard errors explicitly rather than displaying confidence interval notation", async () => {
  renderWithProviders(ui, { route: `/releases/${detail.release.id}` });
  const table = await screen.findByRole("table", { name: "Headline metrics" });
  expect(within(table).getByText("SE 545")).toBeInTheDocument();
  expect(within(table).queryByText(/±545/)).not.toBeInTheDocument();
});

it("reports corrections within a publication separately from earlier publications", async () => {
  const corrected = structuredClone(detail);
  Object.assign(corrected.analysis!, { corrections: {
    available: true, note: "A correction within this publication.", against_captured_at: "2026-10-11T16:00:00+13:00", captured_at: "2026-10-12T16:00:00+13:00",
    series: [{ series_key: "mig.m.net", label: "Net migration (monthly estimate)", unit: "people", n_changed: 1, changes: [{ period: "2026-07", original: 5170, revised: 5171, original_status: "provisional", revised_status: "provisional", original_std_error: 545, revised_std_error: 546, original_released_in: "2026-07", revised_released_in: "2026-07" }] }],
  } });
  mockApi({ [`/api/releases/${detail.release.id}`]: corrected });
  renderWithProviders(ui, { route: `/releases/${detail.release.id}` });
  const section = (await screen.findByRole("heading", { name: "Corrections within this publication" })).closest("section")!;
  expect(within(section).getByText("5,170")).toBeInTheDocument();
  expect(within(section).getByText("5,171")).toBeInTheDocument();
  expect(within(section).getByText("SE 545 → SE 546")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Since the previous release" })).toBeInTheDocument();
});

it("keeps CPI's published decimal precision in correction rows", async () => {
  const corrected = structuredClone(detail);
  const change = (period: string, original: number, revised: number) => ({
    period, original, revised, original_status: "final", revised_status: "final",
    original_std_error: null, revised_std_error: null, original_released_in: null, revised_released_in: null,
  });
  Object.assign(corrected.analysis!, { corrections: {
    available: true, note: "A correction within this publication.", against_captured_at: "2026-10-11T16:00:00+13:00", captured_at: "2026-10-12T16:00:00+13:00",
    series: [
      { series_key: "cpi.index.sa.all_groups", label: "CPI all groups, seasonally adjusted", unit: "index", n_changed: 1, changes: [change("2026-06", 1359.64, 1359.92)] },
      { series_key: "cpi.contrib.q.transport", label: "Transport contribution", unit: "percentage points", n_changed: 1, changes: [change("2026-06", 0.824, 0.831)] },
      { series_key: "cpi.underlying.median", label: "Weighted median", unit: "percent", n_changed: 1, changes: [change("2026-06", 0.4, 0.5)] },
    ],
  } });
  mockApi({ [`/api/releases/${detail.release.id}`]: corrected });
  renderWithProviders(ui, { route: `/releases/${detail.release.id}` });
  const section = (await screen.findByRole("heading", { name: "Corrections within this publication" })).closest("section")!;
  // 1,359.64 -> 1,359.92 must not collapse to 1,360 -> 1,360
  for (const text of ["1,359.64", "1,359.92", "0.824", "0.831", "0.4", "0.5"]) {
    expect(within(section).getByText(text)).toBeInTheDocument();
  }
  expect(within(section).queryByText("1,360")).not.toBeInTheDocument();
});

it("gives CPI's annual and quarterly all-groups metrics distinct React identities", async () => {
  const cpi = structuredClone(detail);
  const [first] = cpi.analysis!.headline_metrics;
  // CPI's annual and quarterly all-groups headline metrics share one series key.
  cpi.analysis!.headline_metrics = [
    { ...first, label: "CPI annual inflation, all groups" },
    { ...first, label: "CPI quarterly inflation, all groups" },
    ...cpi.analysis!.headline_metrics.slice(1),
  ];
  mockApi({ [`/api/releases/${detail.release.id}`]: cpi });
  const errors = vi.spyOn(console, "error").mockImplementation(() => {});
  renderWithProviders(ui, { route: `/releases/${detail.release.id}` });
  await screen.findByRole("heading", { name: "Headline metrics" });
  const duplicateKeys = errors.mock.calls.filter((c) => String(c[0]).includes("same key"));
  errors.mockRestore();
  expect(duplicateKeys).toEqual([]);
  expect(screen.getAllByText("CPI quarterly inflation, all groups").length).toBeGreaterThan(0);
});
