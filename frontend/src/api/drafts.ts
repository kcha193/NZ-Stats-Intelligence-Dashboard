/**
 * Internal draft responses, hand-written because these routes are mounted only by `nzstats serve` on loopback (with
 * `--internal-drafts`, or the owner's auto_display opt-in) and are not in the published API that `schema.d.ts` is generated from. They mirror `research/drafts_api.py`.
 */

export type DraftProblem = { code: string; severity: "error" | "warning"; message: string };

export type DraftClaimStatus = "clean" | "warning" | "failed";

/** What the automated checks found (Phase 4T). Validation categories, not certainty: none of them means "verified". */
export type ValidationCategory = "no_automated_issue" | "automated_warning" | "failed_automated_checks" | "unusable_response";

export type DraftClaim = {
  path: string;
  status: DraftClaimStatus;
  problems: DraftProblem[];
  kind: "institutional_view" | "forecast" | "third_party_forecast" | "policy_decision" | "forward_guidance" | "assumption" | "reported_figure";
  badge: string;
  text: string;
  evidence: { section_ordinal: number; page: number | null; quote: string }[];
  role: string | null;
  issuer: string | null;
  indicator: string | null;
  horizon: string | null;
  value: number | null;
  unit: string | null;
  scenario: string | null;
  qualification: string | null;
  rate: number | null;
  action: string | null;
  decided_on: string | null;
  vote_for: number | null;
  vote_against: number | null;
  source: string | null;
  period: string | null;
  adjustment: string | null;
  measure: string | null;
};

/** Read-only replay; the original claims and provenance below retain their stored verifier. */
export type DraftAssessment = {
  schema_version: "presentation-1";
  id: string;
  assessed_at: string;
  verifier_version: string;
  original_verifier_version: string;
  original_output_hash: string;
  evidence_hash: string;
  original_status: string;
  errors: number;
  warnings: number;
  counts: Record<DraftClaimStatus, number>;
  claims: DraftClaim[];
  executive_paths: string[];
  warning_paths: string[];
  excluded_paths: string[];
};

export type DraftItem = {
  id: number;
  label: string;
  official_statistic: false;
  approved_for_publication: false;
  human_reviewed: boolean;
  checks_passed: boolean;
  validation: Exclude<ValidationCategory, "unusable_response">;
  errors: number;
  warnings: number;
  counts: Record<DraftClaimStatus, number>;
  institution: string;
  institution_name: string;
  document: { title: string; url: string; published_on: string | null; fetched_at: string; version_no: number; format: string; page_count: number | null };
  document_date: string | null;
  licence: string;
  licence_url: string | null;
  provenance: { provider: string; model: string; hosted: boolean; prompt_version: string; processing_version: string; verifier_version: string; written_at: string; checks_scope: string };
  claims: DraftClaim[];
  assessment?: DraftAssessment | null;
  newer_report: { title: string; published_on: string } | null;
};

export type DraftReport = {
  institution: string;
  institution_name: string;
  title: string;
  url: string;
  series: string | null;
  published_on: string | null;
  newest: boolean;
  draft_id: number | null;
  validation: ValidationCategory | null;
  /** A parsed AI summary exists for this report, but the draft gate shows none of it (Phase 4AA). */
  withheld: boolean;
};

export type DraftFeed = { mode: "named" | "automatic"; items: DraftItem[]; reports: DraftReport[]; notice: string };
