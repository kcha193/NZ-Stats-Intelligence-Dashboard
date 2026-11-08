import type { DraftAssessment, DraftClaim, DraftFeed, DraftItem } from "../../src/api/drafts";

// SYNTHETIC ONLY. Browser routes serve these invented claims; no stored research is read.
const base: DraftClaim = {
  path: "outlook", status: "clean", problems: [], kind: "institutional_view", badge: "AI interpretation", text: "Synthetic recovery outlook.",
  evidence: [{ section_ordinal: 0, page: 1, quote: "Synthetic source quotation only." }],
  role: "outlook", issuer: null, indicator: null, horizon: null, value: null, unit: null, scenario: null,
  qualification: null, rate: null, action: null, decided_on: null, vote_for: null, vote_against: null,
  source: null, period: null, adjustment: null, measure: null,
};
const failed = (code: string) => [{ code, severity: "error" as const, message: "Synthetic evidence does not support this claim." }];
const claims: DraftClaim[] = [
  { ...base, status: "failed", problems: failed("quote_not_found") },
  { ...base, path: "drivers[0]", role: "driver", text: "Synthetic supported demand driver." },
  { ...base, path: "risks[0]", role: "risk", text: "Synthetic warning about demand.", status: "warning", problems: [{ code: "definition_not_stated", severity: "warning", message: "Synthetic definition remains uncertain." }] },
  { ...base, path: "facts[0]", role: null, kind: "reported_figure", text: "Synthetic foreign spending.", source: "Example Survey", period: "September 2026", value: 20, unit: "USD billion", measure: "Quarterly change", adjustment: "Seasonally adjusted", qualification: "Provisional" },
  { ...base, path: "facts[1]", role: null, kind: "reported_figure", text: "Synthetic excluded figure.", status: "failed", problems: failed("period_not_supported") },
  { ...base, path: "forecasts[0]", role: null, kind: "third_party_forecast", text: "Synthetic institutional forecast.", issuer: "Example Institute", horizon: "2027 calendar year", value: 1.2, unit: "percent", measure: "Annual growth", qualification: "Conditional", adjustment: "Not stated" },
  { ...base, path: "decisions[0]", role: null, kind: "policy_decision", text: "Synthetic unsupported policy decision.", status: "failed", problems: failed("decision_not_in_evidence") },
];
const assessment: DraftAssessment = {
  schema_version: "presentation-1", id: "synthetic-assessment-" + "a".repeat(64), assessed_at: "2026-11-08T00:00:00Z", verifier_version: "verify-5",
  original_verifier_version: "verify-4", original_output_hash: "b".repeat(64), evidence_hash: "c".repeat(64), original_status: "failed_verification",
  errors: 3, warnings: 1, counts: { clean: 3, warning: 1, failed: 3 }, claims,
  executive_paths: ["drivers[0]", "risks[0]", "facts[0]", "forecasts[0]"], warning_paths: ["risks[0]"], excluded_paths: ["outlook", "facts[1]", "decisions[0]"],
};
export const syntheticDraft: DraftItem = {
  id: 77, label: "Internal draft. Not an official statistic.", official_statistic: false, approved_for_publication: false,
  human_reviewed: false, checks_passed: false, validation: "failed_automated_checks", errors: 2, warnings: 1,
  counts: { clean: 4, warning: 1, failed: 2 }, institution: "treasury", institution_name: "The Treasury (synthetic)",
  document: { title: "Synthetic research update", url: "https://research.example.org/synthetic", published_on: "2026-10-29", fetched_at: "2026-10-30T00:00:00Z", version_no: 1, format: "pdf", page_count: 2 },
  document_date: null, licence: "Synthetic test licence", licence_url: null,
  provenance: { provider: "synthetic", model: "synthetic/model", hosted: false, prompt_version: "outlook-test", processing_version: "synthetic", verifier_version: "verify-4", written_at: "2026-10-30T00:00:00Z", checks_scope: "Synthetic checks only" },
  // Original outlook was clean; the derived assessment rejects it without relabelling history.
  claims: claims.map((c) => c.path === "outlook" ? { ...c, status: "clean", problems: [] } : c),
  newer_report: null, assessment,
};
const other = { ...syntheticDraft, id: 78, institution: "rbnz", institution_name: "Reserve Bank (synthetic)", document: { ...syntheticDraft.document, title: "Synthetic bank update" } };
const historical = { ...syntheticDraft, id: 79, document: { ...syntheticDraft.document, title: "Synthetic historical update", published_on: "2026-10-15" }, newer_report: { title: syntheticDraft.document.title, published_on: "2026-10-29" } };
export const syntheticFeed: DraftFeed = {
  mode: "automatic", items: [syntheticDraft, other, historical], notice: "Synthetic test notice",
  reports: [syntheticDraft, other].map((d) => ({ institution: d.institution, institution_name: d.institution_name, title: d.document.title, url: d.document.url, series: null, published_on: d.document.published_on, newest: true, draft_id: d.id, validation: d.validation, withheld: false })),
};
