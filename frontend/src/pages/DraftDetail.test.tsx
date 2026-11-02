import { screen, within } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { DraftItem } from "@/api/drafts";
import { InternalDrafts } from "@/components/outlook/InternalDrafts";
import { mockApi, renderWithProviders } from "@/test/mockApi";
import DraftDetail from "./DraftDetail";

// SYNTHETIC: a fictional institution and hand-written claims. Real drafts never enter the repository.
afterEach(() => vi.unstubAllGlobals());

const evidence = [{ section_ordinal: 0, page: 1, quote: "Growth of 2.9% is expected in 2027 (synthetic)" }];
const base = { badge: "b", evidence, role: null, issuer: null, indicator: null, horizon: null, value: null, unit: null, scenario: null,
  qualification: null, rate: null, action: null, decided_on: null, vote_for: null, vote_against: null, source: null, period: null,
  adjustment: null, measure: null };

const draft: DraftItem = {
  id: 7,
  label: "Internal draft. Not an official statistic.",
  official_statistic: false,
  approved_for_publication: false,
  human_reviewed: false,
  checks_passed: false,
  errors: 1,
  warnings: 1,
  counts: { clean: 1, warning: 1, failed: 1 },
  institution: "example",
  institution_name: "Example Research (synthetic)",
  document: { title: "Example Update (synthetic)", url: "https://research.example.org/update", published_on: "2026-10-15",
    fetched_at: "2026-10-16T10:00:00+13:00", version_no: 1, format: "pdf", page_count: 7 },
  licence: "Synthetic licence",
  licence_url: null,
  provenance: { provider: "openrouter", model: "example/model", hosted: true, prompt_version: "outlook-v4", processing_version: "3b-1",
    verifier_version: "verify-3", written_at: "2026-10-16T10:00:00+13:00", checks_scope: "Checks test where a quote sits." },
  claims: [
    { ...base, kind: "institutional_view", role: "outlook", text: "Growth is expected to recover <img src=x>.", path: "outlook", status: "clean", problems: [] },
    { ...base, kind: "third_party_forecast", text: "GDP growth", issuer: "IMF", horizon: "2027", value: 2.9, unit: "percent", path: "forecasts[0]",
      status: "failed", problems: [{ code: "issuer_not_in_evidence", severity: "error", message: "forecasts[0]: issuer is not named near the evidence" }] },
    { ...base, kind: "reported_figure", text: "Prices rose 3.7%.", source: "Stats NZ", value: 3.7, unit: "percent", period: "September 2026",
      path: "facts[0]", status: "warning", problems: [{ code: "source_not_named", severity: "warning", message: "facts[0]: source is not named" }] },
  ],
};
const open = (id = 7) =>
  renderWithProviders(<Routes><Route path="/economic-outlook/draft/:id" element={<DraftDetail />} /></Routes>, { route: `/economic-outlook/draft/${id}` });
const on = { research_public: false, internal_drafts: true };
const off = { research_public: false, internal_drafts: false };
const draftCalls = (fn: ReturnType<typeof vi.fn>) => fn.mock.calls.filter(([u]) => String(u).includes("/api/internal/drafts"));

describe("draft detail", () => {
  it("states that the summary failed checks and is not approved", async () => {
    mockApi({ "/api/capabilities": on, "/api/internal/drafts/7": draft });
    open();
    const banner = await screen.findByRole("alert");
    expect(banner).toHaveTextContent("Draft: failed checks, not approved.");
    expect(banner).toHaveTextContent("1 with no problem found, 1 with a warning only, 1 failed");
    expect(screen.getByRole("heading", { level: 1, name: "Example Update (synthetic)" })).toBeInTheDocument();
    expect(screen.getByText("Example Research (synthetic)")).toBeInTheDocument();
  });

  it("marks every claim with its status in words", async () => {
    mockApi({ "/api/capabilities": on, "/api/internal/drafts/7": draft });
    open();
    const outlook = await screen.findByRole("region", { name: "Outlook" });
    expect(within(outlook).getByText("No problem found")).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Forecast claims in this draft" });
    expect(within(table).getByText("Failed checks")).toBeInTheDocument();
    expect(within(table).getByText("Issuer not named in or near the evidence")).toBeInTheDocument();
    const figures = screen.getByRole("region", { name: "Figures as the document reports them" });
    expect(within(figures).getByText("Warning")).toBeInTheDocument();
    expect(within(figures).getByText(/September 2026/)).toBeInTheDocument();
  });

  it("shows who issued a forecast and says when it is a third party's", async () => {
    mockApi({ "/api/capabilities": on, "/api/internal/drafts/7": draft });
    open();
    const row = (await screen.findByRole("table", { name: "Forecast claims in this draft" })).querySelector("tbody tr")!;
    expect(row).toHaveTextContent("IMF");
    expect(row).toHaveTextContent("Third party");
    expect(row).toHaveTextContent("2.9%");
  });

  it("never carries the labels of a checked or reviewed summary", async () => {
    mockApi({ "/api/capabilities": on, "/api/internal/drafts/7": draft });
    const { container } = open();
    await screen.findByRole("alert");
    for (const label of ["Evidence checked", "Human reviewed", "Published here"]) expect(container).not.toHaveTextContent(label);
    expect(screen.getByText(/failed with 1 error and 1 warning/)).toBeInTheDocument();
    expect(screen.getByText("Failed evidence checks")).toBeInTheDocument();
    expect(screen.getByText("Not reviewed")).toBeInTheDocument();
    expect(screen.getByText("Not published")).toBeInTheDocument();
  });

  it("says a draft that passed is still unapproved", async () => {
    mockApi({ "/api/capabilities": on, "/api/internal/drafts/7": { ...draft, checks_passed: true, errors: 0, counts: { clean: 3, warning: 0, failed: 0 } } });
    open();
    expect(await screen.findByRole("alert")).toHaveTextContent("Draft: passed the automated checks, not approved.");
  });

  it("renders model text as text", async () => {
    mockApi({ "/api/capabilities": on, "/api/internal/drafts/7": draft });
    const { container } = open();
    expect(await screen.findByText(/Growth is expected to recover <img src=x>\./)).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
  });

  it("asks for nothing and shows nothing while the switch is off", async () => {
    const fn = mockApi({ "/api/capabilities": off, "/api/internal/drafts/7": draft });
    open();
    expect(await screen.findByText("This draft is not available")).toBeInTheDocument();
    expect(draftCalls(fn)).toEqual([]);
    expect(screen.queryByText("Example Update (synthetic)")).not.toBeInTheDocument();
  });

  it("treats a draft the server withholds as not available", async () => {
    mockApi({ "/api/capabilities": on });
    open();
    expect(await screen.findByText("This draft is not available")).toBeInTheDocument();
  });
});

describe("internal drafts on the outlook", () => {
  it("sends no draft request and renders nothing while the switch is off", async () => {
    const fn = mockApi({ "/api/capabilities": off, "/api/internal/drafts": { items: [draft] } });
    renderWithProviders(<InternalDrafts />);
    await vi.waitFor(() => expect(fn.mock.calls.some(([u]) => String(u).includes("/api/capabilities"))).toBe(true));
    expect(screen.queryByRole("region", { name: "Internal drafts" })).not.toBeInTheDocument();
    expect(draftCalls(fn)).toEqual([]);
  });

  it("renders nothing when the server cannot say whether the switch is on", async () => {
    const fn = mockApi({});
    renderWithProviders(<InternalDrafts />);
    await vi.waitFor(() => expect(fn).toHaveBeenCalled());
    expect(screen.queryByRole("region", { name: "Internal drafts" })).not.toBeInTheDocument();
    expect(draftCalls(fn)).toEqual([]);
  });

  it("renders nothing and asks for nothing on the static site", async () => {
    vi.stubEnv("VITE_DATA_MODE", "static");
    const fn = mockApi({ "/api/capabilities": on, "/api/internal/drafts": { items: [draft] } });
    renderWithProviders(<InternalDrafts />);
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(fn).not.toHaveBeenCalled();
    expect(screen.queryByRole("region", { name: "Internal drafts" })).not.toBeInTheDocument();
    vi.unstubAllEnvs();
  });

  it("renders nothing when no draft is listed", async () => {
    const fn = mockApi({ "/api/capabilities": on, "/api/internal/drafts": { items: [] } });
    renderWithProviders(<InternalDrafts />);
    await vi.waitFor(() => expect(draftCalls(fn).length).toBe(1));
    expect(screen.queryByRole("region", { name: "Internal drafts" })).not.toBeInTheDocument();
  });

  it("identifies itself to the server as the local dashboard", async () => {
    const fn = mockApi({ "/api/capabilities": on, "/api/internal/drafts": { items: [draft] } });
    renderWithProviders(<InternalDrafts />);
    await screen.findByRole("region", { name: "Internal drafts" });
    const [, init] = draftCalls(fn)[0];
    expect(init.headers["X-NZStats-Client"]).toBe("dashboard");
  });

  it("reports a failed request rather than hiding it", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) =>
      String(input).includes("/api/capabilities")
        ? new Response(JSON.stringify(on), { status: 200 })
        : new Response(JSON.stringify({ detail: "refused" }), { status: 403 })));
    renderWithProviders(<InternalDrafts />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("lists a draft with its warning, counts and a link to its page", async () => {
    mockApi({ "/api/capabilities": on, "/api/internal/drafts": { items: [draft] } });
    renderWithProviders(<InternalDrafts />);
    const section = await screen.findByRole("region", { name: "Internal drafts" });
    expect(within(section).getByText(/Only on this machine/)).toBeInTheDocument();
    expect(within(section).getByText("Draft: failed checks, not approved")).toBeInTheDocument();
    expect(within(section).getByText(/1 with no problem found, 1 with a warning only, 1 failed/)).toBeInTheDocument();
    expect(within(section).getByRole("link", { name: "Example Update (synthetic)" })).toHaveAttribute("href", "/economic-outlook/draft/7");
  });
});
