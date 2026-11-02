import { Link } from "react-router-dom";
import { useInternalDrafts } from "@/api/hooks";
import type { DraftClaimStatus, DraftItem } from "@/api/drafts";
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

/** Summaries the owner named, which may have failed checks. Renders nothing unless the server has the switch on. */
export function InternalDrafts() {
  const query = useInternalDrafts();
  if (query.isError) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  const items = query.data?.items ?? [];
  if (items.length === 0) return null;
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
          </li>
        ))}
      </ul>
    </section>
  );
}
