import { Link } from "react-router-dom";
import { useInternalDrafts } from "@/api/hooks";
import type { DraftClaimStatus, DraftItem, DraftReport } from "@/api/drafts";
import { ExternalLink } from "@/components/outlook/ExternalLink";
import { ErrorState } from "@/components/QueryBoundary";
import { formatCivilDate } from "@/lib/format";

const STATUS_LABELS: Record<DraftClaimStatus, string> = { failed: "Failed checks", warning: "Warning", clean: "No problem found" };
const STATUS_STYLES: Record<DraftClaimStatus, string> = {
  failed: "border-destructive bg-destructive/10 text-destructive",
  warning: "border-amber-600/50 bg-amber-50 text-amber-800 dark:bg-amber-950 dark:text-amber-200",
  clean: "border-rule-strong/30 text-muted-foreground",
};

/** A claim's result, always in words as well as colour. */
export function ClaimStatus({ status }: { status: DraftClaimStatus }) {
  return <span className={`inline-block rounded-full border px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[status]}`}>{STATUS_LABELS[status]}</span>;
}

export const draftHeadline = (d: DraftItem) => (d.checks_passed ? "Draft: passed the automated checks, not approved" : "Draft: failed checks, not approved");

export const draftCounts = (d: DraftItem) =>
  `${d.counts.clean} with no problem found, ${d.counts.warning} with a warning only, ${d.counts.failed} failed`;

/** Set when the institution has published after the report this draft covers, so it cannot read as the latest view. */
export function NewerReportNote({ draft }: { draft: DraftItem }) {
  if (!draft.newer_report) return null;
  return (
    <p className="mt-2 text-sm font-medium">
      This draft covers an earlier report. Newest held: {draft.newer_report.title}, published {formatCivilDate(draft.newer_report.published_on)}.
    </p>
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
            <p className="mt-1 text-sm">
              {r.draft_id === null
                ? "No internal draft available"
                : <Link className="underline underline-offset-4" to={`/economic-outlook/draft/${r.draft_id}`}>Read the unapproved AI draft</Link>}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Summaries the owner named, which may have failed checks, and the reports held. Renders nothing unless the server has the switch on. */
export function InternalDrafts() {
  const query = useInternalDrafts();
  if (query.isError) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  const items = query.data?.items ?? [];
  const reports = query.data?.reports ?? [];
  if (items.length === 0 && reports.length === 0) return null;
  return (
    <div className="space-y-6">
      {items.length > 0 && <DraftList items={items} />}
      {reports.length > 0 && <ReportsHeld reports={reports} />}
    </div>
  );
}

function DraftList({ items }: { items: DraftItem[] }) {
  return (
    <section aria-labelledby="internal-drafts-title" className="rounded-md border-2 border-destructive/60 p-5 sm:p-6">
      <h2 id="internal-drafts-title" className="type-section">Internal drafts</h2>
      <p className="mt-1.5 max-w-[72ch] text-sm leading-relaxed text-muted-foreground">
        Only on this machine. These AI summaries may have failed the automated checks and no person has approved them, so
        treat every line as unconfirmed. They are not published research and not official statistics.
      </p>
      <ul className="mt-4 divide-y">
        {items.map((d) => (
          <li key={d.id} className="py-4">
            <p className="text-sm font-semibold text-destructive">{draftHeadline(d)}</p>
            <h3 className="mt-1 font-display text-lg font-semibold tracking-tight">
              <Link className="underline-offset-4 hover:underline" to={`/economic-outlook/draft/${d.id}`}>{d.document.title}</Link>
            </h3>
            <p className="mt-1 text-sm text-muted-foreground">{d.institution_name}, {formatCivilDate(d.document.published_on)}</p>
            <p className="mt-1 text-sm">{d.claims.length} claims: {draftCounts(d)}.</p>
            <NewerReportNote draft={d} />
          </li>
        ))}
      </ul>
    </section>
  );
}
