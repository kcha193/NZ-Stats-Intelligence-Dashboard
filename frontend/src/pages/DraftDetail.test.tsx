import { screen, within } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { DraftItem, DraftReport } from "@/api/drafts";
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
  validation: "failed_automated_checks",
  errors: 1,
  warnings: 1,
  counts: { clean: 1, warning: 1, failed: 1 },
  institution: "example",
  institution_name: "Example Research (synthetic)",
  document: { title: "Example Update (synthetic)", url: "https://research.example.org/update", published_on: "2026-10-15",
    fetched_at: "2026-10-16T10:00:00+13:00", version_no: 1, format: "pdf", page_count: 7 },
  document_date: null,
  licence: "Synthetic licence",
  licence_url: null,
  newer_report: null,
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
const reports: DraftReport[] = [
  { institution: "example", institution_name: "Example Research (synthetic)", title: "Example Update, later (synthetic)", url: "https://research.example.org/later",
    series: "Update", published_on: "2026-11-02", newest: true, draft_id: null, validation: null },
  { institution: "example", institution_name: "Example Research (synthetic)", title: "Example Update (synthetic)", url: "https://research.example.org/update",
    series: "Update", published_on: "2026-10-19", newest: false, draft_id: 7, validation: "failed_automated_checks" },
];
const newer = { title: "Example Update, later (synthetic)", published_on: "2026-11-02" };
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
    expect(banner).toHaveTextContent("AI draft: failed automated checks, not independently reviewed.");
    expect(banner).toHaveTextContent("1 with no automated issue detected, 1 with an automated warning, 1 failed");
    expect(screen.getByRole("heading", { level: 1, name: "Example Update (synthetic)" })).toBeInTheDocument();
    expect(screen.getByText("Example Research (synthetic)")).toBeInTheDocument();
  });

  it("marks every claim with its status in words", async () => {
    mockApi({ "/api/capabilities": on, "/api/internal/drafts/7": draft });
    open();
    const outlook = await screen.findByRole("region", { name: "Outlook" });
    expect(within(outlook).getByText("No automated issue detected")).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Forecast claims in this draft" });
    expect(within(table).getByText("Failed automated checks")).toBeInTheDocument();
    expect(within(table).getByText("Issuer not named in or near the evidence")).toBeInTheDocument();
    const figures = screen.getByRole("region", { name: "Figures as the document reports them" });
    expect(within(figures).getByText("Automated warning")).toBeInTheDocument();
    expect(within(figures).getByText(/September 2026/)).toBeInTheDocument();
  });

  it("shows who issued a forecast and says when it is a third party's", async () => {
    mockApi({ "/api/capabilities": on, "/api/internal/drafts/7": draft });
    open();
    const row = (await screen.findByRole("table", { name: "Forecast claims in this draft" })).querySelector("tbody tr")!;
    expect(row).toHaveTextContent("IMF");
    expect(row).toHaveTextContent("Third party, not the report's author");
    expect(row).toHaveTextContent("2.9%");
  });

  it("never carries the labels of a checked or reviewed summary", async () => {
    mockApi({ "/api/capabilities": on, "/api/internal/drafts/7": draft });
    const { container } = open();
    await screen.findByRole("alert");
    for (const label of ["Evidence checked", "Human reviewed", "Published here", "Approved", "Official statistic", "Verified"]) {
      expect(container).not.toHaveTextContent(new RegExp(`\\b${label}\\b`));
    }
    expect(screen.getByText(/failed with 1 error and 1 warning/)).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Processing and review" })).getByText("Failed automated checks")).toBeInTheDocument();
    expect(screen.getByText("Not independently reviewed")).toBeInTheDocument();
    expect(screen.getByText("Not published")).toBeInTheDocument();
  });

  it("says when the institution has published a newer report than the one this draft covers", async () => {
    mockApi({ "/api/capabilities": on, "/api/internal/drafts/7": { ...draft, newer_report: newer } });
    open();
    expect(await screen.findByRole("alert")).toHaveTextContent("This draft covers an earlier report. Newest held: Example Update, later (synthetic), published 2 Nov 2026.");
  });

  it("does not mention a newer report when none is held", async () => {
    mockApi({ "/api/capabilities": on, "/api/internal/drafts/7": draft });
    open();
    expect(await screen.findByRole("alert")).not.toHaveTextContent("earlier report");
  });

  it("says a draft that passed is still unapproved", async () => {
    mockApi({ "/api/capabilities": on, "/api/internal/drafts/7": { ...draft, checks_passed: true, validation: "no_automated_issue", errors: 0, counts: { clean: 3, warning: 0, failed: 0 } } });
    open();
    expect(await screen.findByRole("alert")).toHaveTextContent("AI draft: no automated issue detected, not independently reviewed.");
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
  it("names the newest report by publication date and keeps earlier reports reachable", async () => {
    mockApi({ "/api/capabilities": on, "/api/internal/drafts": { items: [{ ...draft, newer_report: newer }], reports } });
    renderWithProviders(<InternalDrafts />);
    const held = await screen.findByRole("region", { name: "Reports held" });
    const [latest, earlier] = within(held).getAllByRole("listitem");
    expect(latest).toHaveTextContent("Newest");
    expect(latest).toHaveTextContent("published 2 Nov 2026");
    expect(latest).toHaveTextContent("No AI commentary");
    expect(latest).not.toHaveTextContent(/No AI summary/i);
    expect(within(latest).getByRole("link", { name: /Example Update, later/ })).toHaveAttribute("href", "https://research.example.org/later");
    expect(earlier).not.toHaveTextContent("Newest");
    expect(earlier).toHaveTextContent("published 19 Oct 2026");
    expect(within(earlier).getByRole("link", { name: /Example Update \(synthetic\)/ })).toHaveAttribute("href", "https://research.example.org/update");
    expect(within(earlier).getByRole("link", { name: "Read the AI draft" })).toHaveAttribute("href", "/economic-outlook/draft/7");
  });

  it("does not claim a report was never summarised just because no draft can be shown", async () => {
    mockApi({ "/api/capabilities": on, "/api/internal/drafts": { items: [], reports: reports.slice(0, 1) } });
    renderWithProviders(<InternalDrafts />);
    const held = await screen.findByRole("region", { name: "Reports held" });
    expect(held).toHaveTextContent("No AI commentary");
    expect(held).not.toHaveTextContent(/No AI summary/i);
    expect(within(held).queryByRole("link", { name: "Read the AI draft" })).not.toBeInTheDocument();
  });

  it("says a listed draft covers an earlier report when a newer one is held", async () => {
    mockApi({ "/api/capabilities": on, "/api/internal/drafts": { items: [{ ...draft, newer_report: newer }], reports } });
    renderWithProviders(<InternalDrafts />);
    const drafts = await screen.findByRole("region", { name: "Internal drafts" });
    expect(within(drafts).getByText(/This draft covers an earlier report\./)).toBeInTheDocument();
  });

  it("shows held reports when no draft has been named", async () => {
    mockApi({ "/api/capabilities": on, "/api/internal/drafts": { items: [], reports: reports.slice(0, 1) } });
    renderWithProviders(<InternalDrafts />);
    expect(await screen.findByRole("region", { name: "Reports held" })).toHaveTextContent("Example Update, later (synthetic)");
    expect(screen.queryByText(/These AI summaries may have failed/)).not.toBeInTheDocument();
  });

  it("does not call a report undated by its import date", async () => {
    mockApi({ "/api/capabilities": on, "/api/internal/drafts": { items: [], reports: [{ ...reports[0], published_on: null, newest: false }] } });
    renderWithProviders(<InternalDrafts />);
    const held = await screen.findByRole("region", { name: "Reports held" });
    expect(held).toHaveTextContent("publication date not stated");
    expect(held).not.toHaveTextContent("Newest");
  });

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
    expect(within(section).getByText("Failed automated checks")).toBeInTheDocument();
    expect(within(section).getByText(/1 with no automated issue detected, 1 with an automated warning, 1 failed/)).toBeInTheDocument();
    expect(within(section).getByRole("link", { name: "Example Update (synthetic)" })).toHaveAttribute("href", "/economic-outlook/draft/7");
  });
});

describe("Phase 4T internal AI experience", () => {
  const NOTICE = "AI-generated research draft. Automated checks may miss errors. Not independently reviewed.";
  const treasury = { ...draft, id: 9, institution: "treasury", institution_name: "The Treasury (synthetic)",
    document: { ...draft.document, title: "Treasury Update (synthetic)", url: "https://research.example.org/t" }, document_date: "29 October 2026" };
  const feed = {
    mode: "automatic",
    items: [treasury],
    reports: [
      { institution: "treasury", institution_name: "The Treasury (synthetic)", title: "Treasury Update (synthetic)", url: "https://research.example.org/t",
        series: null, published_on: "2026-11-02", newest: true, draft_id: 9, validation: "failed_automated_checks" },
      { institution: "rbnz", institution_name: "Reserve Bank (synthetic)", title: "Bank Statement (synthetic)", url: "https://research.example.org/r",
        series: null, published_on: "2026-10-08", newest: true, draft_id: null, validation: "unusable_response" },
    ],
    notice: NOTICE,
  };

  it("shows the persistent notice on the outlook and on each draft", async () => {
    mockApi({ "/api/capabilities": on, "/api/internal/drafts": feed, "/api/internal/drafts/7": draft });
    renderWithProviders(<InternalDrafts />);
    expect(await screen.findByText(NOTICE)).toBeInTheDocument();
    open();
    expect(await screen.findByRole("alert")).toHaveTextContent(NOTICE);
  });

  it("leads with the latest Treasury and Reserve Bank commentary", async () => {
    mockApi({ "/api/capabilities": on, "/api/internal/drafts": feed });
    renderWithProviders(<InternalDrafts />);
    const t = await screen.findByRole("article", { name: "Latest Treasury commentary" });
    expect(t).toHaveTextContent("Treasury Update (synthetic)");
    expect(t).toHaveTextContent("Published 2 Nov 2026. Document date: 29 October 2026");
    expect(t).toHaveTextContent("Failed automated checks");
    expect(t).toHaveTextContent("AI interpretation");
    expect(within(t).getByRole("link", { name: "Read the full draft and its checks" })).toHaveAttribute("href", "/economic-outlook/draft/9");
    const r = screen.getByRole("article", { name: "Latest Reserve Bank commentary" });
    expect(r).toHaveTextContent("The AI response for this report was unusable, so nothing is shown.");
    expect(within(r).queryByText("AI interpretation")).not.toBeInTheDocument();
  });

  it("separates current reports from earlier ones", async () => {
    mockApi({ "/api/capabilities": on, "/api/internal/drafts": { ...feed, items: [treasury, { ...draft, newer_report: newer }] } });
    renderWithProviders(<InternalDrafts />);
    expect(await screen.findByRole("region", { name: "Current reports" })).toHaveTextContent("Treasury Update (synthetic)");
    expect(screen.getByRole("region", { name: "Earlier reports" })).toHaveTextContent("Example Update (synthetic)");
  });

  it("puts every failed claim and its reason in view without a click", async () => {
    mockApi({ "/api/capabilities": on, "/api/internal/drafts/7": draft });
    open();
    const failed = await screen.findByRole("region", { name: "1 claim failed the automated checks" });
    expect(within(failed).getByRole("link", { name: "GDP growth" })).toHaveAttribute("href", "#claim-forecasts-0-");
    expect(within(failed).getByText("Issuer not named in or near the evidence")).toBeVisible();
    expect(within(failed).getByText("forecasts[0]: issuer is not named near the evidence")).toBeVisible();
  });

  it("marks AI interpretation apart from what the report states", async () => {
    mockApi({ "/api/capabilities": on, "/api/internal/drafts/7": draft });
    open();
    const outlook = await screen.findByRole("region", { name: "Outlook" });
    expect(within(outlook).getByText("AI interpretation")).toBeInTheDocument();
    expect(within(outlook).getByText("Statement in the official report")).toBeInTheDocument();
    expect(screen.getByText("Not the official series. Official Stats NZ figures are on the dashboard pages.")).toBeInTheDocument();
  });

  it("never calls a failed or warned claim's quote the report's own statement", async () => {
    mockApi({ "/api/capabilities": on, "/api/internal/drafts/7": draft });
    open();
    const table = await screen.findByRole("table", { name: "Forecast claims in this draft" });
    expect(within(table).getByText("Quote cited by the AI, not confirmed by the automated checks")).toBeInTheDocument();
    expect(within(table).queryByText("Statement in the official report")).not.toBeInTheDocument();
    const figures = screen.getByRole("region", { name: "Figures as the document reports them" });
    expect(within(figures).queryByText("Statement in the official report")).not.toBeInTheDocument();
  });

  it("can show only the claims with issues", async () => {
    mockApi({ "/api/capabilities": on, "/api/internal/drafts/7": draft });
    open();
    expect(await screen.findByRole("region", { name: "Outlook" })).toBeInTheDocument();
    screen.getByRole("checkbox", { name: /Show only claims with an automated warning or failure/ }).click();
    await vi.waitFor(() => expect(screen.queryByRole("region", { name: "Outlook" })).not.toBeInTheDocument());
    expect(screen.getByRole("table", { name: "Forecast claims in this draft" })).toBeInTheDocument();
  });

  it("states the document date or says it is not stated", async () => {
    mockApi({ "/api/capabilities": on, "/api/internal/drafts/7": draft });
    open();
    expect(await screen.findByText("Not stated in the document")).toBeInTheDocument();
  });

  it("says a draft with a warning is not verified", async () => {
    mockApi({ "/api/capabilities": on, "/api/internal/drafts/7": { ...draft, checks_passed: true, validation: "automated_warning" } });
    const { container } = open();
    expect(await screen.findByRole("alert")).toHaveTextContent("AI draft: automated warning, not independently reviewed.");
    expect(container).not.toHaveTextContent(/\bverified\b/i);
  });
});
