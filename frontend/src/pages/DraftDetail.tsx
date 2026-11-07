import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import type { DraftClaim, DraftItem } from "@/api/drafts";
import { useInternalDraft } from "@/api/hooks";
import { formatForecastValue } from "@/charts/forecasts";
import { ExternalLink } from "@/components/outlook/ExternalLink";
import { ClaimStatus, DRAFT_NOTICE, draftCounts, draftHeadline, NewerReportNote, ValidationBadge } from "@/components/outlook/InternalDrafts";
import { EmptyState, QueryBoundary } from "@/components/QueryBoundary";
import { formatAklDate, formatCivilDate } from "@/lib/format";
import { useDocumentTitle } from "@/seo/useDocumentTitle";
import { Evidence, UNIT_LABELS } from "./ResearchDetail";

const PROBLEM_LABELS: Record<string, string> = {
  period_not_supported: "Period not stated near the evidence",
  horizon_not_supported: "Horizon not stated near the evidence",
  fiscal_calendar_mismatch: "Fiscal and calendar year basis conflict",
  issuer_not_in_evidence: "Issuer not named in or near the evidence",
  horizon_without_period: "Horizon names no period",
  source_not_named: "Source not named near the evidence",
  definition_not_stated: "Statistical definition not stated",
};

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

function valueText(value: number | null, unit: string | null) {
  if (value === null) return "No number stated";
  const label = unit ? UNIT_LABELS[unit] ?? unit : null;
  return label ? formatForecastValue(value, label) : String(value);
}

function Status({ claim }: { claim: DraftClaim }) {
  return (
    <div>
      <ClaimStatus status={claim.status} />
      {claim.problems.length > 0 && (
        <details className="mt-1 text-xs" open={claim.status === "failed"}>
          <summary className="cursor-pointer text-muted-foreground">Why</summary>
          <ul className="mt-1 space-y-1">
            {claim.problems.map((p, i) => (
              <li key={i}>
                <span className="font-medium">{PROBLEM_LABELS[p.code] ?? p.code}</span>
                <span className="block break-words text-muted-foreground">{p.message}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

const anchor = (path: string) => `claim-${path.replace(/[^a-z0-9]+/gi, "-")}`;

/** The model's words, marked as interpretation so they cannot read as the report's own. */
function Interpretation({ text }: { text: string }) {
  return (
    <div className="mt-1.5">
      <p className="text-xs font-medium text-muted-foreground">AI interpretation</p>
      <p className="max-w-[72ch] leading-relaxed">{text}</p>
    </div>
  );
}

/** What the report itself says: the quoted evidence a claim cites. */
function Quoted({ refs }: { refs: DraftClaim["evidence"] }) {
  if (refs.length === 0) return <p className="mt-2 text-xs font-medium text-destructive">No evidence cited from the report</p>;
  return (
    <div className="mt-2">
      <p className="text-xs font-medium text-muted-foreground">Statement in the official report</p>
      <Evidence refs={refs} />
    </div>
  );
}

function Statements({ title, claims }: { title: string; claims: DraftClaim[] }) {
  if (claims.length === 0) return null;
  return (
    <section aria-label={title}>
      <h3 className="font-display text-base font-semibold tracking-tight">{title}</h3>
      <ul className="mt-2 space-y-5">
        {claims.map((c) => (
          <li key={c.path} id={anchor(c.path)}>
            <Status claim={c} />
            <Interpretation text={c.text} />
            {c.scenario && <p className="mt-1 text-sm text-muted-foreground">Scenario: {c.scenario}</p>}
            <Quoted refs={c.evidence} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function ForecastRow({ c }: { c: DraftClaim }) {
  return (
    <tr className="align-top" id={anchor(c.path)}>
      <th scope="row" className="py-2.5 pr-4 font-medium">{c.text}</th>
      <td className="py-2.5 pr-4">{c.issuer ?? "Not stated"}<span className="block text-xs text-muted-foreground">{c.kind === "third_party_forecast" ? "Third party, not the report's author" : "The document's author"}</span></td>
      <td className="py-2.5 pr-4">{c.horizon}</td>
      <td className="py-2.5 pr-4 tabular-nums">{valueText(c.value, c.unit)}</td>
      <td className="py-2.5 pr-4">{c.scenario ? `Scenario: ${c.scenario}` : "Central"}</td>
      <td className="py-2.5 pr-4"><Status claim={c} /></td>
      <td className="py-2.5 text-muted-foreground">
        {c.qualification ?? "None stated"}
        <Quoted refs={c.evidence} />
      </td>
    </tr>
  );
}

/** Every claim the checks failed, with its reasons in view, so a failure is never buried in the page. */
function FailedClaims({ claims }: { claims: DraftClaim[] }) {
  const failed = claims.filter((c) => c.status === "failed");
  if (failed.length === 0) return null;
  return (
    <section aria-labelledby="failed-claims-title" className="rounded-md border border-destructive/60 p-4 sm:p-5">
      <h2 id="failed-claims-title" className="font-display text-base font-semibold tracking-tight text-destructive">
        {plural(failed.length, "claim")} failed the automated checks
      </h2>
      <p className="mt-1 max-w-[72ch] text-sm text-muted-foreground">Disputed or unsupported: treat these as wrong until you have checked the report.</p>
      <ul className="mt-3 space-y-3">
        {failed.map((c) => (
          <li key={c.path} className="text-sm">
            <a className="font-medium underline underline-offset-4" href={`#${anchor(c.path)}`}>{c.text}</a>
            <ul className="mt-1 space-y-0.5">
              {c.problems.filter((p) => p.severity === "error").map((p, i) => (
                <li key={i}>
                  <span className="font-medium">{PROBLEM_LABELS[p.code] ?? p.code}</span>
                  <span className="block break-words text-muted-foreground">{p.message}</span>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </section>
  );
}

function View({ d }: { d: DraftItem }) {
  useDocumentTitle(`Draft: ${d.document.title}`);
  const [issuesOnly, setIssuesOnly] = useState(false);
  const shown = issuesOnly ? d.claims.filter((c) => c.status !== "clean") : d.claims;
  const of = (kind: DraftClaim["kind"], role?: string) => shown.filter((c) => c.kind === kind && (role === undefined || c.role === role));
  const forecasts = shown.filter((c) => c.kind === "forecast" || c.kind === "third_party_forecast");
  const figures = of("reported_figure");
  const decisions = of("policy_decision");
  return (
    <article className="space-y-10">
      <div role="alert" className="rounded-md border-2 border-destructive bg-destructive/10 p-4 sm:p-5">
        <p className="font-semibold">{DRAFT_NOTICE}</p>
        <p className="mt-1 font-semibold text-destructive">{draftHeadline(d)}.</p>
        <p className="mt-1 max-w-[72ch] text-sm leading-relaxed">
          Treat every line as unconfirmed. Only on this machine. It is not published research and not an official statistic.
        </p>
        <p className="mt-2 text-sm">{plural(d.claims.length, "claim")}: {draftCounts(d)}.</p>
        <NewerReportNote draft={d} />
      </div>

      <header className="border-b-2 border-rule-strong pb-6">
        <p className="text-sm"><Link className="text-accent-ink underline-offset-4 hover:underline" to="/economic-outlook">Economic outlook</Link></p>
        <p className="mt-4 text-sm font-semibold">{d.institution_name}</p>
        <h1 className="type-lead mt-1 max-w-[30ch]">{d.document.title}</h1>
        <dl className="mt-5 grid gap-x-8 gap-y-2 text-sm sm:grid-cols-2 lg:grid-cols-5">
          <div><dt className="text-xs text-muted-foreground">Published by the institution</dt><dd>{formatCivilDate(d.document.published_on)}</dd></div>
          <div><dt className="text-xs text-muted-foreground">Document date</dt><dd>{d.document_date ?? "Not stated in the document"}</dd></div>
          <div><dt className="text-xs text-muted-foreground">Document version</dt><dd>Version {d.document.version_no}, stored {formatAklDate(d.document.fetched_at)}</dd></div>
          <div><dt className="text-xs text-muted-foreground">Format</dt><dd>{d.document.format.toUpperCase()}{d.document.page_count ? `, ${d.document.page_count} pages` : ""}</dd></div>
          <div><dt className="text-xs text-muted-foreground">Original</dt><dd><ExternalLink href={d.document.url}>Read the original document</ExternalLink></dd></div>
        </dl>
        <ul aria-label="Processing and review" className="mt-4 flex flex-wrap gap-x-3 gap-y-1 text-xs font-medium">
          <li>AI summary</li>
          <li><ValidationBadge category={d.validation} /></li>
          <li className="text-destructive">{d.human_reviewed ? "Reviewed, not approved for publication" : "Not independently reviewed"}</li>
          <li className="text-destructive">Not published</li>
        </ul>
      </header>

      <FailedClaims claims={d.claims} />

      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={issuesOnly} onChange={(e) => setIssuesOnly(e.target.checked)} />
        Show only claims with an automated warning or failure
      </label>

      <section aria-labelledby="interpretation-title" className="space-y-8">
        <div>
          <h2 id="interpretation-title" className="type-section">What the document says</h2>
          <p className="mt-1.5 text-xs font-medium text-muted-foreground">AI interpretation of the document, not independently reviewed. Not an official statistic.</p>
          <p className="mt-1 max-w-[72ch] text-sm text-muted-foreground">Each statement cites the section and the exact words of the stored document it rests on.</p>
        </div>
        <Statements title="Outlook" claims={of("institutional_view", "outlook")} />
        <Statements title="Key drivers" claims={of("institutional_view", "driver")} />
        <Statements title="Risks" claims={of("institutional_view", "risk")} />
        <Statements title="Uncertainty" claims={of("institutional_view", "uncertainty")} />
      </section>

      <section aria-labelledby="forecast-claims-title">
        <h2 id="forecast-claims-title" className="type-section">Forecast claims</h2>
        <p className="mt-1.5 max-w-[72ch] text-sm text-muted-foreground">As the model extracted them. Check each issuer and horizon against the document.</p>
        {forecasts.length === 0 ? (
          <p className="mt-4 text-sm text-muted-foreground">This draft has no forecast claims.</p>
        ) : (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[52rem] text-left text-sm">
              <caption className="sr-only">Forecast claims in this draft</caption>
              <thead className="text-xs text-muted-foreground">
                <tr>{["Indicator", "Issuer", "Horizon", "Value", "Kind", "Status", "Qualification and evidence"].map((h) => <th key={h} scope="col" className="py-1.5 pr-4 font-medium">{h}</th>)}</tr>
              </thead>
              <tbody className="divide-y">{forecasts.map((c) => <ForecastRow key={c.path} c={c} />)}</tbody>
            </table>
          </div>
        )}
      </section>

      {figures.length > 0 && (
        <section aria-labelledby="figures-title">
          <h2 id="figures-title" className="type-section">Figures as the document reports them</h2>
          <p className="mt-1.5 max-w-[72ch] text-sm text-muted-foreground">Not the official series. Official Stats NZ figures are on the dashboard pages.</p>
          <ul className="mt-4 space-y-5">
            {figures.map((c) => (
              <li key={c.path} id={anchor(c.path)}>
                <Status claim={c} />
                <Interpretation text={c.text} />
                <p className="mt-1 text-sm text-muted-foreground">Source: {c.source ?? "Not stated"}. Period: {c.period ?? "Not stated"}. Value: {valueText(c.value, c.unit)}.{c.measure ? ` Measure: ${c.measure}.` : ""}</p>
                <Quoted refs={c.evidence} />
              </li>
            ))}
          </ul>
        </section>
      )}

      {decisions.length > 0 && (
        <section aria-labelledby="decisions-title">
          <h2 id="decisions-title" className="type-section">Policy decisions</h2>
          <ul className="mt-4 space-y-5">
            {decisions.map((c) => (
              <li key={c.path} id={anchor(c.path)}>
                <Status claim={c} />
                <Interpretation text={`${c.issuer}: ${c.action}, ${c.rate}%, ${formatCivilDate(c.decided_on)}${c.vote_for !== null ? `, vote ${c.vote_for}–${c.vote_against}` : ""}.`} />
                <Quoted refs={c.evidence} />
              </li>
            ))}
          </ul>
        </section>
      )}

      <Statements title="Forward guidance" claims={of("forward_guidance")} />
      <Statements title="Assumptions" claims={of("assumption")} />

      <section aria-labelledby="provenance-title" className="-mx-4 bg-surface-sunken px-4 py-8 lg:-mx-8 lg:px-8">
        <h2 id="provenance-title" className="type-section">Provenance</h2>
        <dl className="mt-5 grid gap-x-8 gap-y-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
          <div><dt className="text-xs text-muted-foreground">Model</dt><dd>{d.provenance.model} ({d.provenance.provider}, {d.provenance.hosted ? "hosted service" : "run locally"})</dd></div>
          <div><dt className="text-xs text-muted-foreground">Prompt and processing</dt><dd>{d.provenance.prompt_version}, {d.provenance.processing_version}</dd></div>
          <div><dt className="text-xs text-muted-foreground">Summary written</dt><dd>{formatAklDate(d.provenance.written_at)}</dd></div>
          <div><dt className="text-xs text-muted-foreground">Automated checks</dt><dd>{d.provenance.verifier_version}, {d.checks_passed ? "no failure" : "failed"} with {plural(d.errors, "error")} and {plural(d.warnings, "warning")}</dd></div>
          <div><dt className="text-xs text-muted-foreground">Independent review</dt><dd>{d.human_reviewed ? "Reviewed, not approved for publication" : "None"}</dd></div>
          <div><dt className="text-xs text-muted-foreground">Publication status</dt><dd>Unpublished</dd></div>
        </dl>
        <p className="mt-5 max-w-[72ch] text-xs leading-relaxed text-muted-foreground">
          &ldquo;No automated issue detected&rdquo; means only that the automated checks raised nothing. It is not verification. They test where a quote, number, unit and horizon sit in the document, not economic accuracy.
        </p>
        <p className="mt-3 max-w-[72ch] text-xs text-muted-foreground">Source: {d.institution_name}. {d.licence}</p>
      </section>
    </article>
  );
}

export default function DraftDetail() {
  const { id = "" } = useParams();
  const n = /^\d{1,15}$/.test(id) ? Number(id) : NaN;
  const query = useInternalDraft(n);
  useDocumentTitle(query.data ? undefined : "Internal draft");
  const missing = (
    <div className="space-y-4">
      <EmptyState title="This draft is not available" body="AI drafts appear only on this machine, when the server has them switched on and the summary passes the draft rules." />
      <p className="text-sm"><Link className="font-medium text-accent-ink underline-offset-4 hover:underline" to="/economic-outlook">Back to the economic outlook</Link></p>
    </div>
  );
  if (!Number.isFinite(n)) return missing;
  return (
    <QueryBoundary query={query} isEmpty={(d) => d === null} empty={missing}>
      {(d) => (d ? <View d={d} /> : missing)}
    </QueryBoundary>
  );
}
