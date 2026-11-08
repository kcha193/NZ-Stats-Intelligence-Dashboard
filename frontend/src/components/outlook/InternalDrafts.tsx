import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useInternalDrafts } from "@/api/hooks";
import type { DraftClaim, DraftClaimStatus, DraftFeed, DraftItem, DraftReport, ValidationCategory } from "@/api/drafts";
import { formatForecastValue } from "@/charts/forecasts";
import { ExternalLink } from "@/components/outlook/ExternalLink";
import { ResearchFeed } from "@/components/outlook/ResearchFeed";
import { ErrorState } from "@/components/QueryBoundary";
import { Skeleton } from "@/components/ui/skeleton";
import { formatAklDate, formatCivilDate } from "@/lib/format";
import { UNIT_LABELS } from "@/pages/ResearchDetail";

/** The persistent notice on every internal AI view. Its wording is fixed by the owner (Phase 4AA). */
export const DRAFT_NOTICE =
  "AI-generated analysis for internal use. Claims are checked automatically against source documents but may contain errors. Not independently reviewed.";

const STATUS_LABELS: Record<DraftClaimStatus, string> = {
  failed: "Failed automated checks",
  warning: "Automated warning",
  clean: "No automated issue detected",
};
const STATUS_STYLES: Record<DraftClaimStatus, string> = {
  failed: "border-destructive bg-destructive/10 text-destructive",
  warning: "border-amber-600/50 bg-amber-50 text-amber-800 dark:bg-amber-950 dark:text-amber-200",
  clean: "border-rule-strong/30 text-muted-foreground",
};

/** Validation categories, never certainty: "no automated issue" is not "verified". */
const VALIDATION_LABELS: Record<ValidationCategory, string> = {
  no_automated_issue: "No automated issue detected",
  automated_warning: "Automated warning",
  failed_automated_checks: "Failed automated checks",
  unusable_response: "Unusable AI response, not shown",
};
const VALIDATION_STATUS: Record<ValidationCategory, DraftClaimStatus> = {
  no_automated_issue: "clean",
  automated_warning: "warning",
  failed_automated_checks: "failed",
  unusable_response: "failed",
};
// The two institutions whose commentary leads the page. Others still appear in the lists below.
const LEADING = [
  ["treasury", "Treasury"],
  ["rbnz", "Reserve Bank"],
] as const;

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

/** A claim's result, always in words as well as colour. */
export function ClaimStatus({ status }: { status: DraftClaimStatus }) {
  return <span className={`inline-block rounded-full border px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[status]}`}>{STATUS_LABELS[status]}</span>;
}

export function ValidationBadge({ category }: { category: ValidationCategory }) {
  return (
    <span className={`inline-block rounded-full border px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[VALIDATION_STATUS[category]]}`}>
      {VALIDATION_LABELS[category]}
    </span>
  );
}

/** The notice, in the same words wherever AI analysis is shown. */
export function DraftNotice({ className = "" }: { className?: string }) {
  return (
    <p role="note" className={`rounded-md border border-destructive/60 bg-destructive/5 px-3 py-2 text-sm font-medium ${className}`}>
      {DRAFT_NOTICE}
    </p>
  );
}

export const draftHeadline = (d: DraftItem) => `AI draft: ${VALIDATION_LABELS[d.validation].toLowerCase()}, not independently reviewed`;

export const draftCounts = (d: DraftItem) =>
  `${d.counts.clean} with no automated issue detected, ${d.counts.warning} with an automated warning, ${d.counts.failed} failed`;

/** A number with its unit, as the document states it. */
export function valueText(value: number | null, unit: string | null) {
  if (value === null) return "No number stated";
  const label = unit ? UNIT_LABELS[unit] ?? unit : null;
  return label ? formatForecastValue(value, label) : String(value);
}

const draftLink = (d: DraftItem) => `/economic-outlook/draft/${d.id}`;
export const NO_SUPPORTED_OUTLOOK = "No evidence-supported AI outlook is available for this report.";

/** Never promote an original claim when a replay is absent, excluded or has an error. */
export function executiveClaims(d: DraftItem): DraftClaim[] {
  const a = d.assessment;
  if (!a || a.schema_version !== "presentation-1") return [];
  return a.claims.filter((c) =>
    a.executive_paths.includes(c.path) && !a.excluded_paths.includes(c.path)
    && c.status !== "failed" && !c.problems.some((p) => p.severity === "error"),
  );
}
const ofRole = (d: DraftItem, role: string) => executiveClaims(d).filter((c) => c.kind === "institutional_view" && c.role === role);
const published = (d: DraftItem) =>
  `${d.institution_name}, published ${formatCivilDate(d.document.published_on)}${d.document_date ? `. Document date: ${d.document_date}` : ""}`;

/** Set when the institution has published after the report this analysis covers, so it cannot read as the latest view. */
export function NewerReportNote({ draft }: { draft: DraftItem }) {
  if (!draft.newer_report) return null;
  return (
    <p className="mt-2 text-sm font-medium">
      This draft covers an earlier report. Newest held: {draft.newer_report.title}, published {formatCivilDate(draft.newer_report.published_on)}.
    </p>
  );
}

/** A claim in the model's words, labelled as interpretation, with its check result beside it. */
function ClaimLine({ claim, children }: { claim: DraftClaim; children?: ReactNode }) {
  return (
    <li className="py-2.5">
      <p className="leading-relaxed">{claim.text}</p>
      {children}
      <p className="mt-1"><ClaimStatus status={claim.status} /></p>
      {claim.problems.length > 0 && <ul className="mt-1 text-sm text-muted-foreground">{claim.problems.map((p, i) => <li key={i}>{p.code}: {p.message}</li>)}</ul>}
    </li>
  );
}

function Panel({ id, title, intro, children }: { id: string; title: string; intro?: string; children: ReactNode }) {
  return (
    <section aria-labelledby={id}>
      <h3 id={id} className="font-display text-lg font-semibold tracking-tight">{title}</h3>
      {intro && <p className="mt-1 max-w-[72ch] text-sm text-muted-foreground">{intro}</p>}
      <div className="mt-3">{children}</div>
    </section>
  );
}

/** Both identities remain visible; a replay never replaces historical verification. */
export function AssessmentIdentity({ draft }: { draft: DraftItem }) {
  const a = draft.assessment;
  return (
    <section aria-label="Derived presentation assessment" className="mt-3 text-xs text-muted-foreground">
      <p className="font-medium">Derived presentation assessment</p>
      {a ? <>
        <p>{a.verifier_version}, assessed {formatAklDate(a.assessed_at)}. {a.errors} errors and {a.warnings} warnings. {a.counts.clean} with no automated issue detected, {a.counts.warning} with warnings, {a.counts.failed} excluded.</p>
        <p>Original stored assessment: {a.original_verifier_version}, {a.original_status}, {draft.errors} errors and {draft.warnings} warnings.</p>
        <details className="mt-1">
          <summary className="cursor-pointer">Assessment identity and original output hash</summary>
          <dl className="mt-1 space-y-1 break-all">
            <div><dt>Assessment ID ({a.schema_version})</dt><dd>{a.id}</dd></div>
            <div><dt>Original output hash</dt><dd>{a.original_output_hash}</dd></div>
            <div><dt>Document evidence hash</dt><dd>{a.evidence_hash}</dd></div>
          </dl>
        </details>
      </> : <p>Unavailable. Executive highlights are withheld. Original stored assessment: {draft.provenance.verifier_version}.</p>}
      <p>Automated evidence checks do not establish economic accuracy.</p>
    </section>
  );
}

/** Every excluded claim remains available, with its original words and AI-cited evidence. */
export function ClaimsAttention({ draft }: { draft: DraftItem }) {
  const a = draft.assessment;
  if (!a) return null;
  const excluded = a.claims.filter((c) => a.excluded_paths.includes(c.path) || c.status === "failed" || c.problems.some((p) => p.severity === "error"));
  if (excluded.length === 0) return null;
  return (
    <details aria-label={`Claims requiring attention: ${draft.document.title}`} className="mt-3 rounded-md border border-destructive/60 p-3 text-sm">
      <summary className="cursor-pointer font-medium">Claims requiring attention ({excluded.length})</summary>
      <p className="mt-2 text-xs text-muted-foreground">{a.verifier_version}, assessed {formatAklDate(a.assessed_at)}. These exclusions do not repair the original output or its stored verdict.</p>
      <ul className="mt-3 space-y-4">
        {excluded.map((c) => {
          const original = draft.claims.find((claim) => claim.path === c.path) ?? c;
          return (
            <li key={c.path} className="break-words">
              <p className="text-xs text-muted-foreground">Original AI claim: {c.path}</p>
              <p className="mt-1 font-medium">{original.text}</p>
              <p className="mt-1">Excluded from executive insights: failed automated evidence checks; support remains unresolved.</p>
              <ul className="mt-1 text-destructive">
                {c.problems.map((p, i) => <li key={i}>{p.severity}: {p.code}: {p.message}</li>)}
              </ul>
              <p className="mt-2 text-xs font-medium">Original source citation. Quote cited by the AI, not confirmed by the automated checks.</p>
              <p className="text-xs"><ExternalLink href={draft.document.url}>{draft.document.title}</ExternalLink>, published {formatCivilDate(draft.document.published_on)}.</p>
              {original.evidence.length === 0 ? (
                <p className="mt-1 text-xs">No evidence cited from the report.</p>
              ) : original.evidence.map((ref, i) => (
                <blockquote key={i} className="mt-2 border-l-2 pl-3">
                  <p>{ref.quote}</p>
                  <p className="mt-1 text-xs text-muted-foreground">Section {ref.section_ordinal + 1}{ref.page !== null ? `, page ${ref.page}` : ""}</p>
                </blockquote>
              ))}
            </li>
          );
        })}
      </ul>
      <p className="mt-3"><Link className="underline underline-offset-4" to={draftLink(draft)}>Complete original summary and stored assessment</Link></p>
    </details>
  );
}

/** Shared derived view on the detail page; original claims stay under their stored verifier below. */
export function DraftAssessmentView({ draft }: { draft: DraftItem }) {
  return (
    <div className="space-y-8">
      <ExecutiveSummary lead={draft} />
      <DriversAndRisks lead={draft} />
      <FactsAndForecasts lead={draft} />
      <ClaimsAttention draft={draft} />
    </div>
  );
}

/** 1. The newest current analysis: the institution's overall view, read by the model. */
function ExecutiveSummary({ lead }: { lead: DraftItem }) {
  const [outlook] = ofRole(lead, "outlook");
  const [uncertainty] = ofRole(lead, "uncertainty");
  return (
    <Panel id="ai-summary-title" title="Latest economic outlook">
      <article aria-label="Executive summary" className="rounded-md border p-4 sm:p-5">
        <p className="text-xs font-medium text-muted-foreground">{published(lead)}</p>
        <p className="mt-1 font-display text-base font-semibold tracking-tight"><ExternalLink href={lead.document.url}>{lead.document.title}</ExternalLink></p>
        <p className="mt-2 flex flex-wrap items-center gap-2 text-sm">
          <span>Original stored assessment:</span><ValidationBadge category={lead.validation} />
          <span className="text-muted-foreground">{plural(lead.claims.length, "claim")}: {draftCounts(lead)}</span>
        </p>
        {!outlook && <p className="mt-3 font-medium">{NO_SUPPORTED_OUTLOOK}</p>}
        <AssessmentIdentity draft={lead} />
        {outlook && (
          <div className="mt-3">
            <p className="text-xs font-medium text-muted-foreground">AI interpretation of the report</p>
            <ul><ClaimLine claim={outlook} /></ul>
          </div>
        )}
        {uncertainty && (
          <div className="mt-1">
            <p className="text-xs font-medium text-muted-foreground">Uncertainty, as the AI reads it</p>
            <ul><ClaimLine claim={uncertainty} /></ul>
          </div>
        )}
        <NewerReportNote draft={lead} />
        <p className="mt-3 text-sm font-medium">
          <Link className="text-accent-ink underline underline-offset-4" to={draftLink(lead)}>Read the full analysis, its evidence and its checks</Link>
        </p>
      </article>
    </Panel>
  );
}

/** 2. The newest report from Treasury and from the Reserve Bank, with its AI analysis when there is one. */
/** `leadId`: the analysis already summarised above, whose outlook is not repeated here. */
function LatestCommentary({ items, reports, leadId = null }: { items: DraftItem[]; reports: DraftReport[]; leadId?: number | null }) {
  const cards = LEADING.flatMap(([key, short]) => {
    const latest = reports.find((r) => r.institution === key && r.newest) ?? reports.find((r) => r.institution === key);
    return latest ? [{ key, short, latest, draft: items.find((d) => d.id === latest.draft_id) ?? null }] : [];
  });
  if (cards.length === 0) return null;
  return (
    <Panel id="latest-commentary-title" title="Latest institutional commentary">
      <div className="grid gap-4 md:grid-cols-2">
        {cards.map(({ key, short, latest, draft }) => (
          <article key={key} aria-label={`Latest ${short} commentary`} className="flex flex-col rounded-md border p-4 sm:p-5">
            <p className="text-xs font-medium text-muted-foreground">{latest.institution_name}</p>
            <h4 className="mt-1 font-display text-base font-semibold tracking-tight">
              <ExternalLink href={latest.url}>{latest.title}</ExternalLink>
            </h4>
            <p className="mt-1 text-sm text-muted-foreground">
              {latest.published_on ? `Published ${formatCivilDate(latest.published_on)}` : "Publication date not stated"}
              {draft?.document_date ? `. Document date: ${draft.document_date}` : ""}
            </p>
            {draft ? (
              <>
                <div className="mt-3 text-sm">Original stored assessment: <ValidationBadge category={draft.validation} /></div>
                {draft.id !== leadId && !ofRole(draft, "outlook")[0] && <p className="mt-3 text-sm">{NO_SUPPORTED_OUTLOOK}</p>}
                {draft.id !== leadId && ofRole(draft, "outlook")[0] && (
                  <div className="mt-3">
                    <p className="text-xs font-medium text-muted-foreground">AI interpretation</p>
                    <ul><ClaimLine claim={ofRole(draft, "outlook")[0]} /></ul>
                  </div>
                )}
                <p className="mt-3 text-sm">{plural(draft.claims.length, "claim")}: {draftCounts(draft)}.</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Original automated checks: {draft.provenance.verifier_version}, prompt {draft.provenance.prompt_version}. Checks look for support in the document, not for economic accuracy.
                </p>
                <AssessmentIdentity draft={draft} />
                <p className="mt-auto pt-3 text-sm font-medium">
                  <Link className="text-accent-ink underline underline-offset-4" to={draftLink(draft)}>Read the full analysis and its checks</Link>
                </p>
              </>
            ) : (
              <p className="mt-3 text-sm">{reportStatusText(latest)}</p>
            )}
          </article>
        ))}
      </div>
    </Panel>
  );
}

function reportStatusText(r: DraftReport) {
  if (r.withheld) return "AI analysis exists for this report but is withheld by the eligibility rules, so nothing is shown.";
  if (r.validation === "unusable_response") return "The AI response for this report was unusable, so nothing is shown.";
  return "No AI analysis for this report yet. An AI request runs only when an operator starts one; opening this page never starts one.";
}

/** 3. What the institution says is moving the economy, and what could go wrong, as the model reads it. */
function DriversAndRisks({ lead }: { lead: DraftItem }) {
  const drivers = ofRole(lead, "driver");
  const risks = ofRole(lead, "risk");
  if (drivers.length === 0 && risks.length === 0) return null;
  const list = (title: string, claims: DraftClaim[]) => (
    <section aria-label={title}>
      <h4 className="text-sm font-semibold">{title}</h4>
      {claims.length === 0 ? <p className="mt-1 text-sm text-muted-foreground">No statements without automated errors.</p> : (
        <div className="mt-2 space-y-3">
          {(["clean", "warning"] as const).map((status) => {
            const group = claims.filter((c) => c.status === status);
            return group.length > 0 && (
              <div key={status}>
                <p className="text-xs font-medium text-muted-foreground">{status === "clean" ? "Statements with no automated issue detected" : "Statements with automated warnings"}</p>
                <ul className="divide-y">{group.map((c) => <ClaimLine key={c.path} claim={c} />)}</ul>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
  return (
    <Panel id="drivers-risks-title" title="Key economic drivers and risks" intro={`AI interpretation of ${lead.institution_name}'s ${lead.document.title}.`}>
      <div className="grid gap-6 md:grid-cols-2">
        {list("Key drivers", drivers)}
        {list("Risks", risks)}
      </div>
    </Panel>
  );
}

/** 4. Figures as the document reports them, and institutions' forecasts: neither is an official Stats NZ observation. */
function FactsAndForecasts({ lead }: { lead: DraftItem }) {
  const facts = executiveClaims(lead).filter((c) => c.kind === "reported_figure");
  const forecasts = executiveClaims(lead).filter((c) => c.kind === "forecast" || c.kind === "third_party_forecast");
  if (facts.length === 0 && forecasts.length === 0) return null;
  return (
    <Panel id="facts-forecasts-title" title="Reported economic facts and institutional forecasts"
      intro="As the AI extracted them from the report. Reported figures are the institution's statement, not the official Stats NZ series shown above; forecasts are the institution's expectations, not outcomes.">
      <p className="mb-3 text-xs text-muted-foreground">Original publication: {formatCivilDate(lead.document.published_on)}. Assessment: {lead.assessment?.verifier_version}, {lead.assessment ? formatAklDate(lead.assessment.assessed_at) : "unavailable"}.</p>
      {facts.length > 0 && (
        <section aria-label="Reported figures">
          <h4 className="text-sm font-semibold">Figures as the report states them</h4>
          <ul className="mt-1 divide-y">
            {facts.map((c) => (
              <ClaimLine key={c.path} claim={c}>
                <p className="text-sm text-muted-foreground">Source: {c.source ?? "Not stated"}. Period: {c.period ?? "Not stated"}. Value: {valueText(c.value, c.unit)}. Unit: {c.unit ?? "Not stated"}. Measure: {c.measure ?? "Not stated"}. Adjustment: {c.adjustment ?? "Not stated"}. Qualification: {c.qualification ?? "None stated"}.</p>
              </ClaimLine>
            ))}
          </ul>
        </section>
      )}
      {forecasts.length > 0 && (
        <div className="mt-5 overflow-x-auto">
          <table className="w-full min-w-[40rem] text-left text-sm">
            <caption className="text-left text-sm font-semibold">Institutional forecasts</caption>
            <thead className="text-xs text-muted-foreground">
              <tr>{["Indicator", "Forecast by", "Horizon", "Value", "Kind", "Automated checks"].map((h) => <th key={h} scope="col" className="py-1.5 pr-4 font-medium">{h}</th>)}</tr>
            </thead>
            <tbody className="divide-y">
              {forecasts.map((c) => (
                <tr key={c.path} className="align-top">
                  <th scope="row" className="py-2 pr-4 font-medium">{c.text}</th>
                  <td className="py-2 pr-4">{c.issuer ?? "Not stated"}{c.kind === "third_party_forecast" && <span className="block text-xs text-muted-foreground">Third party, cited by the report</span>}</td>
                  <td className="py-2 pr-4">{c.horizon ?? "Not stated"}</td>
                  <td className="py-2 pr-4 tabular-nums">{valueText(c.value, c.unit)}<span className="block text-xs text-muted-foreground">Unit: {c.unit ?? "Not stated"}</span></td>
                  <td className="py-2 pr-4">{c.scenario ? `Scenario: ${c.scenario}` : "Central"}<span className="block text-xs text-muted-foreground">Measure: {c.measure ?? "Not stated"}. Adjustment: {c.adjustment ?? "Not stated"}. Qualification: {c.qualification ?? "None stated"}.</span></td>
                  <td className="py-2"><ClaimStatus status={c.status} />{c.problems.map((p, i) => <p key={i} className="mt-1 text-xs">{p.code}: {p.message}</p>)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

function DraftRows({ items }: { items: DraftItem[] }) {
  return (
    <ul className="divide-y">
      {items.map((d) => (
        <li key={d.id} className="py-4">
          <p className="flex flex-wrap items-center gap-2 text-sm">
            {d.newer_report && <span className="inline-block rounded-full border border-rule-strong/40 px-2 py-0.5 text-xs font-medium">Historical</span>}
            <span>Original stored assessment:</span><ValidationBadge category={d.validation} />
            <span className="text-muted-foreground">Not independently reviewed</span>
          </p>
          <h4 className="mt-1.5 font-display text-lg font-semibold tracking-tight">
            <Link className="underline-offset-4 hover:underline" to={draftLink(d)}>{d.document.title}</Link>
          </h4>
          <p className="mt-1 text-sm text-muted-foreground">{published(d)}</p>
          {ofRole(d, "outlook")[0] ? <ul><ClaimLine claim={ofRole(d, "outlook")[0]} /></ul> : <p className="mt-2 text-sm">{NO_SUPPORTED_OUTLOOK}</p>}
          <AssessmentIdentity draft={d} />
          <p className="mt-1 text-sm">{plural(d.claims.length, "claim")}: {draftCounts(d)}.</p>
          <NewerReportNote draft={d} />
        </li>
      ))}
    </ul>
  );
}

/** 6a. Each analysis's automated check results; claim-by-claim problems expand in place. */
function Verification({ items }: { items: DraftItem[] }) {
  return (
    <ul aria-label="Automated checks by analysis" className="divide-y">
      {items.map((d) => {
        const flagged = d.claims.filter((c) => c.status !== "clean");
        return (
          <li key={d.id} className="py-3 text-sm">
            <p className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{d.document.title}</span>
              <ValidationBadge category={d.validation} />
            </p>
            <p className="mt-1 text-muted-foreground">
              Original stored assessment: {plural(d.errors, "error")} and {plural(d.warnings, "warning")} across {plural(d.claims.length, "claim")}. Checks {d.provenance.verifier_version},
              prompt {d.provenance.prompt_version}, model {d.provenance.model} ({d.provenance.hosted ? "hosted" : "run locally"}).
            </p>
            <AssessmentIdentity draft={d} />
            <ClaimsAttention draft={d} />
            {flagged.length > 0 && (
              <details className="mt-1">
                <summary className="cursor-pointer">{plural(flagged.length, "claim")} with a failed check or warning</summary>
                <ul className="mt-2 space-y-2">
                  {flagged.map((c) => (
                    <li key={c.path}>
                      <p><ClaimStatus status={c.status} /> <span className="font-medium">{c.text}</span></p>
                      <ul className="mt-0.5 text-muted-foreground">
                        {c.problems.map((p, i) => <li key={i} className="break-words">{p.message}</li>)}
                      </ul>
                    </li>
                  ))}
                </ul>
              </details>
            )}
            <p className="mt-1"><Link className="text-accent-ink underline underline-offset-4" to={draftLink(d)}>Evidence quotes and every claim</Link></p>
          </li>
        );
      })}
    </ul>
  );
}

/** 6b. Every report held, newest publication first. A listed report has not necessarily been analysed or checked. */
function ReportsHeld({ reports }: { reports: DraftReport[] }) {
  return (
    <section aria-labelledby="reports-held-title">
      <h4 id="reports-held-title" className="text-sm font-semibold">Reports held</h4>
      <p className="mt-1 max-w-[72ch] text-sm leading-relaxed text-muted-foreground">
        Only on this machine, newest first by the date each institution published it. A report listed here is the institution's own document, and
        being listed does not mean it has been analysed or checked.
      </p>
      <ul className="mt-2 divide-y">
        {reports.map((r) => (
          <li key={r.url} className="py-3">
            <p className="text-sm font-semibold">
              <ExternalLink href={r.url}>{r.title}</ExternalLink>
              {r.newest && <span className="ml-2 inline-block rounded-full border border-rule-strong/40 px-2 py-0.5 text-xs font-medium">Newest</span>}
            </p>
            <p className="mt-1 text-sm text-muted-foreground">{r.institution_name}, {r.published_on ? `published ${formatCivilDate(r.published_on)}` : "publication date not stated"}</p>
            <p className="mt-1 flex flex-wrap items-center gap-2 text-sm">
              {r.validation && <ValidationBadge category={r.validation} />}
              <span>
                {r.draft_id !== null
                  ? <Link className="underline underline-offset-4" to={`/economic-outlook/draft/${r.draft_id}`}>Read the AI analysis</Link>
                  : reportStatusText(r)}
              </span>
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Why nothing can be shown, in the owner's terms. Never a publication checklist. */
function NoCommentary({ feed }: { feed: DraftFeed }) {
  const reasons: [string, string][] = [];
  if (feed.mode === "named") {
    reasons.push(["Automatic display is off", "data/internal-drafts.json does not set auto_display, so only analyses named in that file appear, and none is named."]);
  }
  const { reports } = feed;
  if (reports.length === 0) {
    reasons.push(["No document has been imported", "No Treasury or Reserve Bank report is held on this machine yet."]);
  }
  const count = (pred: (r: DraftReport) => boolean) => reports.filter(pred).length;
  const unusable = count((r) => r.validation === "unusable_response" && !r.withheld);
  const withheld = count((r) => r.withheld);
  const none = count((r) => r.validation === null && !r.withheld);
  if (unusable) reasons.push(["An AI response was unusable", `${plural(unusable, "report")}: the AI response was malformed, cut off or refused, so nothing is shown.`]);
  if (withheld) reasons.push(["AI analysis is withheld", `${plural(withheld, "report")}: an analysis exists but fails the eligibility rules (for example withdrawn or rejected), so it is not shown.`]);
  if (none) reasons.push(["No AI analysis has been generated", `${plural(none, "report")} held with no AI analysis. An AI request runs only when an operator starts one; opening this page never starts one.`]);
  return (
    <div className="rounded-md border border-dashed bg-surface-sunken p-5 sm:p-6">
      <p className="font-display text-lg font-semibold tracking-tight">No AI analysis to show yet</p>
      <ul className="mt-3 space-y-3">
        {reasons.map(([title, body]) => (
          <li key={title} className="border-t border-rule-strong/30 pt-3">
            <p className="text-sm font-medium">{title}</p>
            <p className="mt-0.5 max-w-[72ch] text-sm text-muted-foreground">{body}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** The consolidated internal view: one section for every eligible AI analysis on this machine. */
function Intelligence({ feed }: { feed: DraftFeed }) {
  const { items, reports } = feed;
  const current = items.filter((d) => !d.newer_report);
  const historical = items.filter((d) => d.newer_report);
  const lead = current[0] ?? items[0];
  return (
    <section aria-labelledby="ai-intelligence-title" className="space-y-10">
      <div>
        <h2 id="ai-intelligence-title" className="type-section">AI Economic Intelligence</h2>
        <p className="mt-1.5 max-w-[72ch] text-sm leading-relaxed text-muted-foreground">
          Treasury and Reserve Bank reports held on this machine, read by an AI model. Official Stats NZ observations are the indicators above;
          everything here is an institution's statement or forecast, or the AI's interpretation of it, and is labelled as such.
        </p>
        <DraftNotice className="mt-4" />
      </div>
      {lead ? (
        <>
          <ExecutiveSummary lead={lead} />
          <LatestCommentary items={items} reports={reports} leadId={lead.id} />
          <DriversAndRisks lead={lead} />
          <FactsAndForecasts lead={lead} />
          {current.length > 1 && (
            <Panel id="current-commentary-title" title="Other current commentary"><DraftRows items={current.slice(1)} /></Panel>
          )}
          {historical.length > 0 && (
            <Panel id="historical-commentary-title" title="Historical commentary" intro="The institution has published a newer report since each of these.">
              <DraftRows items={historical} />
            </Panel>
          )}
        </>
      ) : (
        <>
          <NoCommentary feed={feed} />
          <LatestCommentary items={items} reports={reports} />
        </>
      )}
      <section aria-labelledby="evidence-title" className="rounded-md border p-5 sm:p-6">
        <h3 id="evidence-title" className="font-display text-lg font-semibold tracking-tight">Source evidence and automated verification</h3>
        <p className="mt-1 max-w-[72ch] text-sm text-muted-foreground">
          Automated checks test whether each quote, number, unit and horizon is found in the stored document. They do not test economic accuracy,
          and &ldquo;no automated issue detected&rdquo; is not verification.
        </p>
        <div className="mt-4 space-y-6">
          {items.length > 0 && <Verification items={items} />}
          {reports.length > 0 && <ReportsHeld reports={reports} />}
        </div>
      </section>
    </section>
  );
}

/**
 * The economic outlook's research area. With internal AI analysis switched on for this server, the consolidated
 * internal view (plus any published research, never its empty state). Otherwise, the published-research feed alone.
 */
export function EconomicIntelligence() {
  const query = useInternalDrafts();
  if (query.isLoading) {
    return <div role="status" aria-label="Loading AI analysis" className="space-y-3"><Skeleton className="h-24 w-full" /><Skeleton className="h-24 w-full" /></div>;
  }
  if (query.isError) {
    return (
      <section aria-labelledby="ai-intelligence-title">
        <h2 id="ai-intelligence-title" className="type-section">AI Economic Intelligence</h2>
        <div className="mt-4"><ErrorState error={query.error} onRetry={() => void query.refetch()} /></div>
      </section>
    );
  }
  if (!query.data) return <ResearchFeed />;
  return (
    <>
      <Intelligence feed={query.data} />
      <ResearchFeed hideWhenEmpty />
    </>
  );
}
