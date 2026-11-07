import { Link } from "react-router-dom";
import { useInternalDrafts } from "@/api/hooks";
import type { DraftClaimStatus, DraftItem, DraftReport, ValidationCategory } from "@/api/drafts";
import { ExternalLink } from "@/components/outlook/ExternalLink";
import { ErrorState } from "@/components/QueryBoundary";
import { formatCivilDate } from "@/lib/format";

/** The persistent notice on every internal draft view. Its wording is fixed by the owner (Phase 4T). */
export const DRAFT_NOTICE = "AI-generated research draft. Automated checks may miss errors. Not independently reviewed.";

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

/** The notice, in the same words wherever a draft is shown. */
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

/** The model's overall reading of the document, if it gave one. */
const outlookText = (d: DraftItem) => d.claims.find((c) => c.kind === "institutional_view" && c.role === "outlook")?.text ?? null;

/** Set when the institution has published after the report this draft covers, so it cannot read as the latest view. */
export function NewerReportNote({ draft }: { draft: DraftItem }) {
  if (!draft.newer_report) return null;
  return (
    <p className="mt-2 text-sm font-medium">
      This draft covers an earlier report. Newest held: {draft.newer_report.title}, published {formatCivilDate(draft.newer_report.published_on)}.
    </p>
  );
}

function reportStatus(r: DraftReport) {
  if (r.draft_id !== null) {
    return <Link className="underline underline-offset-4" to={`/economic-outlook/draft/${r.draft_id}`}>Read the AI draft</Link>;
  }
  return r.validation === "unusable_response" ? "The AI response was unusable, so nothing is shown" : "No AI commentary";
}

/** The newest report from Treasury and from the Reserve Bank, with its AI commentary when there is one. */
function LatestCommentary({ items, reports }: { items: DraftItem[]; reports: DraftReport[] }) {
  const cards = LEADING.flatMap(([key, short]) => {
    const latest = reports.find((r) => r.institution === key && r.newest) ?? reports.find((r) => r.institution === key);
    return latest ? [{ key, short, latest, draft: items.find((d) => d.id === latest.draft_id) ?? null }] : [];
  });
  if (cards.length === 0) return null;
  return (
    <section aria-labelledby="latest-commentary-title">
      <h2 id="latest-commentary-title" className="type-section">Latest institutional commentary</h2>
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        {cards.map(({ key, short, latest, draft }) => (
          <article key={key} aria-label={`Latest ${short} commentary`} className="flex flex-col rounded-md border p-4 sm:p-5">
            <p className="text-xs font-medium text-muted-foreground">{latest.institution_name}</p>
            <h3 className="mt-1 font-display text-base font-semibold tracking-tight">
              <ExternalLink href={latest.url}>{latest.title}</ExternalLink>
            </h3>
            <p className="mt-1 text-sm text-muted-foreground">
              {latest.published_on ? `Published ${formatCivilDate(latest.published_on)}` : "Publication date not stated"}
              {draft?.document_date ? `. Document date: ${draft.document_date}` : ""}
            </p>
            {draft ? (
              <>
                <div className="mt-3"><ValidationBadge category={draft.validation} /></div>
                {outlookText(draft) && (
                  <div className="mt-3">
                    <p className="text-xs font-medium text-muted-foreground">AI interpretation</p>
                    <p className="mt-0.5 max-w-[60ch] leading-relaxed">{outlookText(draft)}</p>
                  </div>
                )}
                <p className="mt-3 text-sm">{draft.claims.length} claims: {draftCounts(draft)}.</p>
                <p className="mt-auto pt-3 text-sm font-medium">
                  <Link className="text-accent-ink underline underline-offset-4" to={`/economic-outlook/draft/${draft.id}`}>Read the full draft and its checks</Link>
                </p>
              </>
            ) : (
              <p className="mt-3 text-sm">
                {latest.validation === "unusable_response" ? "The AI response for this report was unusable, so nothing is shown." : "No AI commentary for this report yet."}
              </p>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}

/** Every report held, newest publication first. A listed report has not necessarily been summarised or checked. */
function ReportsHeld({ reports }: { reports: DraftReport[] }) {
  return (
    <section aria-labelledby="reports-held-title" className="rounded-md border p-5 sm:p-6">
      <h2 id="reports-held-title" className="type-section">Reports held</h2>
      <p className="mt-1.5 max-w-[72ch] text-sm leading-relaxed text-muted-foreground">
        Only on this machine, newest first by the date each institution published it. A report listed here is the institution's own document, and
        being listed does not mean it has been summarised or checked.
      </p>
      <ul className="mt-4 divide-y">
        {reports.map((r) => (
          <li key={r.url} className="py-3">
            <p className="text-sm font-semibold">
              <ExternalLink href={r.url}>{r.title}</ExternalLink>
              {r.newest && <span className="ml-2 inline-block rounded-full border border-rule-strong/40 px-2 py-0.5 text-xs font-medium">Newest</span>}
            </p>
            <p className="mt-1 text-sm text-muted-foreground">{r.institution_name}, {r.published_on ? `published ${formatCivilDate(r.published_on)}` : "publication date not stated"}</p>
            <p className="mt-1 flex flex-wrap items-center gap-2 text-sm">
              {r.validation && <ValidationBadge category={r.validation} />}
              <span>{reportStatus(r)}</span>
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** AI drafts on this machine, which may have failed checks, and the reports held. Renders nothing unless the server has the switch on. */
export function InternalDrafts() {
  const query = useInternalDrafts();
  if (query.isError) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  const items = query.data?.items ?? [];
  const reports = query.data?.reports ?? [];
  if (items.length === 0 && reports.length === 0) return null;
  return (
    <div className="space-y-6">
      <DraftNotice />
      <LatestCommentary items={items} reports={reports} />
      {items.length > 0 && <DraftList items={items} />}
      {reports.length > 0 && <ReportsHeld reports={reports} />}
    </div>
  );
}

function DraftRows({ items }: { items: DraftItem[] }) {
  return (
    <ul className="mt-2 divide-y">
      {items.map((d) => (
        <li key={d.id} className="py-4">
          <p className="flex flex-wrap items-center gap-2 text-sm">
            <ValidationBadge category={d.validation} />
            <span className="text-muted-foreground">Not independently reviewed</span>
          </p>
          <h4 className="mt-1.5 font-display text-lg font-semibold tracking-tight">
            <Link className="underline-offset-4 hover:underline" to={`/economic-outlook/draft/${d.id}`}>{d.document.title}</Link>
          </h4>
          <p className="mt-1 text-sm text-muted-foreground">
            {d.institution_name}, published {formatCivilDate(d.document.published_on)}
            {d.document_date ? `. Document date: ${d.document_date}` : ""}
          </p>
          <p className="mt-1 text-sm">{d.claims.length} claims: {draftCounts(d)}.</p>
          <NewerReportNote draft={d} />
        </li>
      ))}
    </ul>
  );
}

function DraftList({ items }: { items: DraftItem[] }) {
  const current = items.filter((d) => !d.newer_report);
  const earlier = items.filter((d) => d.newer_report);
  return (
    <section aria-labelledby="internal-drafts-title" className="rounded-md border-2 border-destructive/60 p-5 sm:p-6">
      <h2 id="internal-drafts-title" className="type-section">Internal drafts</h2>
      <p className="mt-1.5 max-w-[72ch] text-sm leading-relaxed text-muted-foreground">
        Only on this machine. Each claim shows what the automated checks found. They are not published research and not official statistics.
      </p>
      {current.length > 0 && (
        <section aria-label="Current reports" className="mt-4">
          <h3 className="text-sm font-semibold">Current reports</h3>
          <DraftRows items={current} />
        </section>
      )}
      {earlier.length > 0 && (
        <section aria-label="Earlier reports" className="mt-4">
          <h3 className="text-sm font-semibold">Earlier reports</h3>
          <p className="mt-0.5 text-xs text-muted-foreground">The institution has published a newer report since.</p>
          <DraftRows items={earlier} />
        </section>
      )}
    </section>
  );
}
