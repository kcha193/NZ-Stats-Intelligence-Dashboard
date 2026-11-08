import { screen, within } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { DraftItem, DraftReport } from "@/api/drafts";
import { EconomicIntelligence } from "@/components/outlook/InternalDrafts";
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
    series: "Update", published_on: "2026-11-02", newest: true, draft_id: null, validation: null, withheld: false },
  { institution: "example", institution_name: "Example Research (synthetic)", title: "Example Update (synthetic)", url: "https://research.example.org/update",
    series: "Update", published_on: "2026-10-19", newest: false, draft_id: 7, validation: "failed_automated_checks", withheld: false },
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
    expect(screen.getByText("Internal use only")).toBeInTheDocument();
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

describe("AI Economic Intelligence on the outlook (Phase 4AA)", () => {
  const NOTICE = "AI-generated analysis for internal use. Claims are checked automatically against source documents but may contain errors. Not independently reviewed.";
  const treasury: DraftItem = { ...draft, id: 9, institution: "treasury", institution_name: "The Treasury (synthetic)",
    document: { ...draft.document, title: "Treasury Update (synthetic)", url: "https://research.example.org/t", published_on: "2026-11-02" },
    document_date: "29 October 2026",
    claims: [
      ...draft.claims,
      { ...base, kind: "institutional_view", role: "driver", text: "Household spending is recovering (synthetic).", path: "drivers[0]", status: "clean", problems: [] },
      { ...base, kind: "institutional_view", role: "risk", text: "Export prices could fall (synthetic).", path: "risks[0]", status: "failed",
        problems: [{ code: "quote_not_found", severity: "error", message: "risks[0]: quote not found in the document" }] },
    ] };
  treasury.assessment = {
    schema_version: "presentation-1", id: "synthetic-phase-aa", assessed_at: "2026-11-08T00:00:00Z", verifier_version: "verify-5",
    original_verifier_version: "verify-3", original_output_hash: "synthetic-aa-output", evidence_hash: "synthetic-aa-evidence", original_status: "failed_verification",
    errors: 2, warnings: 1, counts: { clean: 2, warning: 1, failed: 2 }, claims: treasury.claims,
    executive_paths: ["outlook", "facts[0]", "drivers[0]"], warning_paths: ["facts[0]"], excluded_paths: ["forecasts[0]", "risks[0]"],
  };
  const feed = {
    mode: "automatic",
    items: [treasury],
    reports: [
      { institution: "treasury", institution_name: "The Treasury (synthetic)", title: "Treasury Update (synthetic)", url: "https://research.example.org/t",
        series: null, published_on: "2026-11-02", newest: true, draft_id: 9, validation: "failed_automated_checks", withheld: false },
      { institution: "rbnz", institution_name: "Reserve Bank (synthetic)", title: "Bank Statement (synthetic)", url: "https://research.example.org/r",
        series: null, published_on: "2026-10-08", newest: true, draft_id: null, validation: "unusable_response", withheld: false },
    ],
    notice: NOTICE,
  };
  const show = (body: unknown, caps = on) => mockApi({ "/api/capabilities": caps, "/api/internal/drafts": body });
  const section = () => screen.findByRole("region", { name: "AI Economic Intelligence" });

  it("shows unreviewed commentary that failed its checks, with the internal-use notice", async () => {
    show(feed);
    renderWithProviders(<EconomicIntelligence />);
    const s = await section();
    expect(within(s).getByRole("note")).toHaveTextContent(NOTICE);
    const summary = within(s).getByRole("article", { name: "Executive summary" });
    expect(summary).toHaveTextContent("The Treasury (synthetic), published 2 Nov 2026. Document date: 29 October 2026");
    expect(summary).toHaveTextContent("Failed automated checks");
    expect(summary).toHaveTextContent("AI interpretation of the report");
    expect(within(summary).getByRole("link", { name: /Treasury Update \(synthetic\)/ })).toHaveAttribute("href", "https://research.example.org/t");
    expect(within(summary).getByRole("link", { name: /Read the full analysis/ })).toHaveAttribute("href", "/economic-outlook/draft/9");
  });

  it("never asks for a person's approval or shows the publication checklist", async () => {
    show(feed);
    const { container } = renderWithProviders(<EconomicIntelligence />);
    await section();
    for (const text of ["A person approves it", "No institutional research is published here yet", "Human reviewed", "Approved", "Verified"]) {
      expect(container).not.toHaveTextContent(new RegExp(`\\b${text}\\b`));
    }
    expect(container.textContent).not.toMatch(/[–—]/);
  });

  it("separates drivers and risks, reported figures and institutional forecasts, each with its check result", async () => {
    show(feed);
    renderWithProviders(<EconomicIntelligence />);
    await section();
    const drivers = screen.getByRole("region", { name: "Key economic drivers and risks" });
    expect(within(within(drivers).getByRole("region", { name: "Key drivers" })).getByText("No automated issue detected")).toBeInTheDocument();
    const risks = within(drivers).getByRole("region", { name: "Risks" });
    expect(risks).not.toHaveTextContent("Export prices could fall (synthetic).");
    expect(risks).toHaveTextContent("No statements without automated errors.");
    const facts = screen.getByRole("region", { name: "Reported economic facts and institutional forecasts" });
    expect(facts).toHaveTextContent("not the official Stats NZ series");
    expect(within(facts).getByRole("region", { name: "Reported figures" })).toHaveTextContent("Source: Stats NZ. Period: September 2026. Value: 3.7%.");
    expect(within(facts).queryByRole("table", { name: "Institutional forecasts" })).not.toBeInTheDocument();
    expect(within(facts).getByText("Automated warning")).toBeInTheDocument();
  });

  it("leads with the latest Treasury and Reserve Bank commentary", async () => {
    show(feed);
    renderWithProviders(<EconomicIntelligence />);
    const t = await screen.findByRole("article", { name: "Latest Treasury commentary" });
    expect(t).toHaveTextContent("Published 2 Nov 2026. Document date: 29 October 2026");
    expect(t).toHaveTextContent("Failed automated checks");
    expect(t).toHaveTextContent("Original automated checks: verify-3, prompt outlook-v4");
    expect(within(t).getByRole("link", { name: "Read the full analysis and its checks" })).toHaveAttribute("href", "/economic-outlook/draft/9");
    const r = screen.getByRole("article", { name: "Latest Reserve Bank commentary" });
    expect(r).toHaveTextContent("The AI response for this report was unusable, so nothing is shown.");
    expect(within(r).queryByText("AI interpretation")).not.toBeInTheDocument();
  });

  it("does not repeat the executive summary's outlook in its institution card", async () => {
    show(feed);
    renderWithProviders(<EconomicIntelligence />);
    const t = await screen.findByRole("article", { name: "Latest Treasury commentary" });
    expect(within(t).queryByText("AI interpretation")).not.toBeInTheDocument();
    expect(screen.getAllByText(/Growth is expected to recover/)).toHaveLength(1); // once, in the executive summary
  });

  it("keeps every failed claim and its reason reachable in the verification details", async () => {
    show(feed);
    renderWithProviders(<EconomicIntelligence />);
    await section();
    const checks = screen.getByRole("list", { name: "Automated checks by analysis" });
    expect(checks).toHaveTextContent("1 error and 1 warning across 5 claims. Checks verify-3, prompt outlook-v4, model example/model (hosted).");
    expect(within(checks).getByText("3 claims with a failed check or warning")).toBeInTheDocument();
    expect(within(checks).getAllByText("risks[0]: quote not found in the document")[0]).toBeInTheDocument();
    expect(within(checks).getByRole("link", { name: "Evidence quotes and every claim" })).toHaveAttribute("href", "/economic-outlook/draft/9");
  });

  it("puts earlier reports under historical commentary", async () => {
    show({ ...feed, items: [treasury, { ...draft, newer_report: newer }] });
    renderWithProviders(<EconomicIntelligence />);
    const history = await screen.findByRole("region", { name: "Historical commentary" });
    expect(history).toHaveTextContent("Example Update (synthetic)");
    expect(within(history).getByText("Historical")).toBeInTheDocument();
    expect(within(history).getByText(/This draft covers an earlier report\./)).toBeInTheDocument();
    expect(screen.getByRole("article", { name: "Executive summary" })).toHaveTextContent("Treasury Update (synthetic)");
  });

  it("names the newest report by publication date and keeps earlier reports reachable", async () => {
    show({ ...feed, items: [{ ...draft, newer_report: newer }], reports });
    renderWithProviders(<EconomicIntelligence />);
    const held = await screen.findByRole("region", { name: "Reports held" });
    const [latest, earlier] = within(held).getAllByRole("listitem");
    expect(latest).toHaveTextContent("Newest");
    expect(latest).toHaveTextContent("published 2 Nov 2026");
    expect(latest).toHaveTextContent("No AI analysis for this report yet");
    expect(earlier).toHaveTextContent("published 19 Oct 2026");
    expect(within(earlier).getByRole("link", { name: "Read the AI analysis" })).toHaveAttribute("href", "/economic-outlook/draft/7");
  });

  it("does not call a report undated by its import date", async () => {
    show({ ...feed, items: [], reports: [{ ...reports[0], published_on: null, newest: false }] });
    renderWithProviders(<EconomicIntelligence />);
    const held = await screen.findByRole("region", { name: "Reports held" });
    expect(held).toHaveTextContent("publication date not stated");
    expect(held).not.toHaveTextContent("Newest");
  });

  it.each([
    ["no document imported", { ...feed, items: [], reports: [] }, "No document has been imported"],
    ["no commentary generated", { ...feed, items: [], reports: [{ ...feed.reports[0], draft_id: null, validation: null }] }, "No AI analysis has been generated"],
    ["an unusable response", { ...feed, items: [], reports: [feed.reports[1]] }, "An AI response was unusable"],
    ["commentary withheld by the gate", { ...feed, items: [], reports: [{ ...feed.reports[0], draft_id: null, validation: null, withheld: true }] }, "AI analysis is withheld"],
    ["automatic display off", { ...feed, mode: "named", items: [], reports: [] }, "Automatic display is off"],
  ])("explains an empty view: %s", async (_name, body, reason) => {
    show(body);
    const { container } = renderWithProviders(<EconomicIntelligence />);
    expect(await screen.findByText("No AI analysis to show yet")).toBeInTheDocument();
    expect(screen.getByText(reason)).toBeInTheDocument();
    expect(container).not.toHaveTextContent(/approves|published here yet/);
  });

  it("says opening the page never starts an AI request", async () => {
    show({ ...feed, items: [], reports: [{ ...feed.reports[0], draft_id: null, validation: null }] });
    renderWithProviders(<EconomicIntelligence />);
    const t = await screen.findByRole("article", { name: "Latest Treasury commentary" });
    expect(t).toHaveTextContent("An AI request runs only when an operator starts one; opening this page never starts one.");
  });

  it("shows the published-research view, and asks for no draft, while the switch is off", async () => {
    const fn = show({ items: [draft] }, off);
    renderWithProviders(<EconomicIntelligence />);
    expect(await screen.findByText("No AI economic analysis is shown here")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "AI Economic Intelligence" })).not.toBeInTheDocument();
    expect(screen.queryByText(/A person approves it/)).not.toBeInTheDocument();
    expect(draftCalls(fn)).toEqual([]);
  });

  it("asks for no draft when the server cannot say whether the switch is on", async () => {
    const fn = mockApi({});
    renderWithProviders(<EconomicIntelligence />);
    expect(await screen.findByText("No AI economic analysis is shown here")).toBeInTheDocument();
    expect(draftCalls(fn)).toEqual([]);
  });

  it("asks for no draft on the static site", async () => {
    vi.stubEnv("VITE_DATA_MODE", "static");
    const fn = show({ items: [draft] });
    renderWithProviders(<EconomicIntelligence />);
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(draftCalls(fn)).toEqual([]);
    expect(screen.queryByRole("region", { name: "AI Economic Intelligence" })).not.toBeInTheDocument();
    vi.unstubAllEnvs();
  });

  it("identifies itself to the server as the local dashboard", async () => {
    const fn = show(feed);
    renderWithProviders(<EconomicIntelligence />);
    await section();
    const [, init] = draftCalls(fn)[0];
    expect(init.headers["X-NZStats-Client"]).toBe("dashboard");
  });

  it("reports a failed request rather than hiding it", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) =>
      String(input).includes("/api/capabilities")
        ? new Response(JSON.stringify(on), { status: 200 })
        : new Response(JSON.stringify({ detail: "refused" }), { status: 403 })));
    renderWithProviders(<EconomicIntelligence />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("shows the same notice on each analysis page", async () => {
    mockApi({ "/api/capabilities": on, "/api/internal/drafts/7": draft });
    open();
    expect(await screen.findByRole("alert")).toHaveTextContent(NOTICE);
  });
});

describe("Phase 4T draft page", () => {
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
    expect(within(outlook).getByText("Quote cited by the AI; automated checks found no issue, not independently confirmed")).toBeInTheDocument();
    expect(within(outlook).queryByText("Statement in the official report")).not.toBeInTheDocument();
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

// SYNTHETIC replay intentionally disagrees with the original stored assessment.
const replayClaims = [
  { ...draft.claims[0], status: "failed" as const, problems: [{ code: "quote_not_found", severity: "error" as const, message: "outlook: evidence is unsupported" }] },
  { ...draft.claims[0], path: "drivers[0]", role: "driver", text: "Supported driver (synthetic)." },
  { ...draft.claims[0], path: "risks[0]", role: "risk", text: "Warning risk (synthetic).", status: "warning" as const,
    problems: [{ code: "definition_not_stated", severity: "warning" as const, message: "Definition remains uncertain (synthetic)." }] },
  { ...draft.claims[1] },
  { ...draft.claims[2], status: "clean" as const, problems: [], text: "Foreign spending (synthetic).", value: 20, unit: "USD billion", source: "Example Survey", measure: "Quarterly change", adjustment: "Seasonally adjusted", qualification: "Provisional" },
  { ...draft.claims[0], path: "decisions[0]", kind: "policy_decision" as const, role: null, text: "Unsupported policy decision (synthetic).", status: "failed" as const,
    problems: [{ code: "decision_not_in_evidence", severity: "error" as const, message: "Decision is unsupported (synthetic)." }] },
];
const replay = {
  schema_version: "presentation-1" as const, id: "synthetic-assessment-id", assessed_at: "2026-11-08T00:00:00Z", verifier_version: "verify-5",
  original_verifier_version: "verify-3", original_output_hash: "synthetic-output-hash", evidence_hash: "synthetic-evidence-hash", original_status: "failed_verification",
  errors: 3, warnings: 1, counts: { clean: 2, warning: 1, failed: 3 }, claims: replayClaims,
  executive_paths: ["drivers[0]", "risks[0]", "facts[0]"], warning_paths: ["risks[0]"], excluded_paths: ["outlook", "forecasts[0]", "decisions[0]"],
};
const assessedDraft = { ...draft, assessment: replay };
const showReplay = () => mockApi({ "/api/capabilities": on, "/api/internal/drafts": { mode: "automatic", items: [assessedDraft], reports: [], notice: "Synthetic" } });

describe("Phase 4AB derived assessment", () => {
  it("excludes failed outlook, forecasts and policy decisions from prominent commentary", async () => {
    showReplay();
    renderWithProviders(<EconomicIntelligence />);
    const summary = await screen.findByRole("article", { name: "Executive summary" });
    expect(summary).toHaveTextContent("No evidence-supported AI outlook is available for this report.");
    expect(summary).not.toHaveTextContent(draft.claims[0].text);
    const facts = screen.getByRole("region", { name: "Reported economic facts and institutional forecasts" });
    expect(facts).not.toHaveTextContent("GDP growth");
    expect(facts).not.toHaveTextContent("Unsupported policy decision");
  });
  it("separates clean drivers and warning risks and retains warning details", async () => {
    showReplay();
    renderWithProviders(<EconomicIntelligence />);
    const drivers = await screen.findByRole("region", { name: "Key economic drivers and risks" });
    expect(within(drivers).getByRole("region", { name: "Key drivers" })).toHaveTextContent("Supported driver (synthetic).");
    const risks = within(drivers).getByRole("region", { name: "Risks" });
    for (const text of ["Statements with automated warnings", "Warning risk (synthetic).", "Definition remains uncertain (synthetic)."]) expect(risks).toHaveTextContent(text);
  });
  it("shows measurement, adjustment, source, period, unit, qualification and original publication", async () => {
    showReplay();
    renderWithProviders(<EconomicIntelligence />);
    const facts = await screen.findByRole("region", { name: "Reported economic facts and institutional forecasts" });
    for (const text of ["USD billion", "Quarterly change", "Seasonally adjusted", "Example Survey", "September 2026", "Provisional", "15 Oct 2026"]) expect(facts).toHaveTextContent(text);
    expect(facts).not.toHaveTextContent("NZD");
  });
  it("retains excluded original claims and unconfirmed source citations in expandable attention details", async () => {
    showReplay();
    renderWithProviders(<EconomicIntelligence />);
    const attention = await screen.findByRole("group", { name: /Claims requiring attention/ });
    expect(attention.tagName).toBe("DETAILS");
    for (const text of [draft.claims[0].text, evidence[0].quote, "Quote cited by the AI, not confirmed", "quote_not_found", "Excluded from executive insights", "verify-5", "8 Nov 2026"]) expect(attention).toHaveTextContent(text);
  });
  it.each([null, undefined])("fails closed when the derived assessment is %s", async (assessment) => {
    mockApi({ "/api/capabilities": on, "/api/internal/drafts": { mode: "automatic", items: [{ ...draft, assessment }], reports: [], notice: "Synthetic" } });
    renderWithProviders(<EconomicIntelligence />);
    const summary = await screen.findByRole("article", { name: "Executive summary" });
    expect(summary).toHaveTextContent("No evidence-supported AI outlook is available for this report.");
    expect(summary).not.toHaveTextContent(draft.claims[0].text);
  });
  it("identifies original and derived assessments without relabelling original claim statuses", async () => {
    mockApi({ "/api/capabilities": on, "/api/internal/drafts/7": assessedDraft });
    open();
    const derived = await screen.findByRole("region", { name: "Derived presentation assessment" });
    for (const text of ["verify-5", "8 Nov 2026", "synthetic-assessment-id", "synthetic-output-hash", "synthetic-evidence-hash", "verify-3"]) expect(derived).toHaveTextContent(text);
    expect(screen.getByRole("region", { name: "Outlook" })).toHaveTextContent("No automated issue detected");
    expect(screen.getByRole("heading", { name: "Original stored summary" })).toBeInTheDocument();
  });
});

describe("Phase 4AB promotion boundaries", () => {
  it("does not promote failed claims even if executive paths include them", async () => {
    const a = { ...replay, executive_paths: replay.claims.map((c) => c.path), excluded_paths: [] };
    mockApi({ "/api/capabilities": on, "/api/internal/drafts": { mode: "automatic", items: [{ ...draft, assessment: a }], reports: [], notice: "Synthetic" } });
    renderWithProviders(<EconomicIntelligence />);
    expect(await screen.findByRole("article", { name: "Executive summary" })).not.toHaveTextContent(draft.claims[0].text);
    expect(screen.getByRole("region", { name: "Reported economic facts and institutional forecasts" })).not.toHaveTextContent("GDP growth");
  });
  it("excludes failed outlooks from other institutions, other current and historical previews", async () => {
    const items = [assessedDraft,
      { ...assessedDraft, id: 8, institution: "rbnz", document: { ...draft.document, title: "Bank update (synthetic)" } },
      { ...assessedDraft, id: 9, newer_report: newer, document: { ...draft.document, title: "Older update (synthetic)" } }];
    mockApi({ "/api/capabilities": on, "/api/internal/drafts": { mode: "automatic", items, reports: [{ ...reports[0], institution: "rbnz", draft_id: 8 }], notice: "Synthetic" } });
    renderWithProviders(<EconomicIntelligence />);
    for (const region of [await screen.findByRole("article", { name: "Latest Reserve Bank commentary" }), screen.getByRole("region", { name: "Other current commentary" }), screen.getByRole("region", { name: "Historical commentary" })]) {
      expect(region).toHaveTextContent("No evidence-supported AI outlook is available for this report.");
      expect(region).not.toHaveTextContent(draft.claims[0].text);
    }
  });
  it("states a missing unit explicitly without inferring NZD", async () => {
    const claims = replay.claims.map((c) => c.path === "facts[0]" ? { ...c, unit: null } : c);
    mockApi({ "/api/capabilities": on, "/api/internal/drafts": { mode: "automatic", items: [{ ...draft, assessment: { ...replay, claims } }], reports: [], notice: "Synthetic" } });
    renderWithProviders(<EconomicIntelligence />);
    const facts = await screen.findByRole("region", { name: "Reported economic facts and institutional forecasts" });
    expect(facts).toHaveTextContent("Unit: Not stated");
    expect(facts).not.toHaveTextContent(/NZD|NZ\$/);
  });
  it("preserves the original policy claim's words in the complete original summary", async () => {
    const d = { ...assessedDraft, claims: [...draft.claims, replayClaims[5]] };
    mockApi({ "/api/capabilities": on, "/api/internal/drafts/7": d });
    open();
    const original = await screen.findByRole("region", { name: "Policy decisions" });
    expect(original).toHaveTextContent("Unsupported policy decision (synthetic).");
  });
});
