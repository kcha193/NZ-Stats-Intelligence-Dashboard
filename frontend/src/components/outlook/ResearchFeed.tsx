import { useDeferredValue, useId, useState, type ReactNode } from "react";
import { Search } from "lucide-react";
import { useResearchFeed, type FeedParams } from "@/api/hooks";
import { ErrorState } from "@/components/QueryBoundary";
import { Segmented } from "@/components/Segmented";
import { Skeleton } from "@/components/ui/skeleton";
import { groupItems, PAGE_SIZE, type GroupBy, type Sort } from "@/lib/research";
import { ResearchEntry } from "./ResearchEntry";

/**
 * Shown when no research is published here. Phase 4AA: it no longer lists the publication conditions (which include a
 * person's approval): the owner's AI analysis needs none of them and appears on the local dashboard instead.
 */
export function UnpublishedResearch() {
  return (
    <div className="rounded-md border border-dashed bg-surface-sunken p-5 sm:p-6">
      <p className="font-display text-lg font-semibold tracking-tight">No AI economic analysis is shown here</p>
      <p className="mt-1.5 max-w-[65ch] text-sm leading-relaxed text-muted-foreground">
        AI analysis of Treasury and Reserve Bank reports appears on the local dashboard when internal AI analysis is switched
        on. It is off in this view, so nothing is shown in its place.
      </p>
    </div>
  );
}

function Field({ label, children }: { label: string; children: (id: string) => ReactNode }) {
  const id = useId();
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <label htmlFor={id} className="text-xs font-medium text-muted-foreground">{label}</label>
      {children(id)}
    </div>
  );
}

const control = "h-9 w-full min-w-0 rounded-md border bg-background px-2.5 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent-ink";

/** Section B: published research summaries, with search, filters, sort and grouping. `hideWhenEmpty`: render nothing
 * rather than the empty state (the internal view, which has its own). */
export function ResearchFeed({ hideWhenEmpty = false }: { hideWhenEmpty?: boolean }) {
  const [text, setText] = useState("");
  const q = useDeferredValue(text.trim());
  const [institution, setInstitution] = useState("");
  const [topic, setTopic] = useState("");
  const [sort, setSort] = useState<Sort>("newest");
  const [groupBy, setGroupBy] = useState<GroupBy>("date");
  const [page, setPage] = useState(0);
  const params: FeedParams = { q: q || undefined, institution: institution || undefined, topic: topic || undefined, sort, limit: PAGE_SIZE, offset: page * PAGE_SIZE };
  const query = useResearchFeed(params);
  const filtered = Boolean(q || institution || topic);
  const reset = (fn: () => void) => () => { fn(); setPage(0); };

  const empty = !query.data || (query.data.total === 0 && !filtered && query.data.institutions.length === 0);
  if (hideWhenEmpty && !query.isError && (query.isLoading || empty)) return null;
  let body: ReactNode;
  if (query.isLoading) {
    body = <div role="status" aria-label="Loading research" className="space-y-3"><Skeleton className="h-24 w-full" /><Skeleton className="h-24 w-full" /></div>;
  } else if (query.isError) {
    body = <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  } else if (empty || !query.data) {
    return (
      <section aria-labelledby="research-title">
        <h2 id="research-title" className="type-section">Institutional research</h2>
        <div className="mt-5"><UnpublishedResearch /></div>
      </section>
    );
  } else {
    const d = query.data;
    const topicLabels = Object.fromEntries(d.topics.map((t) => [t.value, t.label]));
    const first = d.offset + 1;
    const last = d.offset + d.items.length;
    body = (
      <>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_minmax(0,1fr)_auto] lg:items-end">
          <Field label="Search titles and summaries">
            {(id) => (
              <div className="relative">
                <Search aria-hidden className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <input id={id} type="search" value={text} maxLength={100} onChange={(e) => { setText(e.target.value); setPage(0); }} className={`${control} pl-8`} />
              </div>
            )}
          </Field>
          <Field label="Institution">
            {(id) => (
              <select id={id} value={institution} onChange={(e) => reset(() => setInstitution(e.target.value))()} className={control}>
                <option value="">All institutions</option>
                {d.institutions.map((f) => <option key={f.value} value={f.value}>{f.label} ({f.count})</option>)}
              </select>
            )}
          </Field>
          <Field label="Topic">
            {(id) => (
              <select id={id} value={topic} onChange={(e) => reset(() => setTopic(e.target.value))()} className={control}>
                <option value="">All topics</option>
                {d.topics.map((f) => <option key={f.value} value={f.value}>{f.label} ({f.count})</option>)}
              </select>
            )}
          </Field>
          <div className="flex flex-col gap-1.5">
            <span aria-hidden className="text-xs font-medium text-muted-foreground">Sort</span>
            <Segmented<Sort> label="Sort" value={sort} onChange={(v) => reset(() => setSort(v))()} options={[
              { value: "newest", label: "Newest" }, { value: "oldest", label: "Oldest" }, { value: "institution", label: "Institution" },
            ]} />
          </div>
        </div>
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-b pb-3">
          <p aria-live="polite" className="text-sm text-muted-foreground">
            {d.total === 0 ? "No research matches these filters." : `Showing ${first} to ${last} of ${d.total}`}
          </p>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span aria-hidden>Group by</span>
            <Segmented<GroupBy> label="Group by" value={groupBy} onChange={setGroupBy} options={[
              { value: "date", label: "Month" }, { value: "institution", label: "Institution" }, { value: "topic", label: "Topic" },
            ]} />
          </div>
        </div>
        {d.total === 0 ? (
          <div className="py-6 text-sm">
            <button type="button" className="font-medium text-accent-ink underline underline-offset-4" onClick={reset(() => { setText(""); setInstitution(""); setTopic(""); })}>
              Clear search and filters
            </button>
          </div>
        ) : (
          <div className={query.isPlaceholderData ? "opacity-60 transition-opacity" : ""}>
            {groupItems(d.items, groupBy, topicLabels).map((g) => (
              <section key={g.label} aria-label={g.label} className="border-b last:border-b-0">
                <h3 className="pt-5 text-xs font-semibold text-muted-foreground">{g.label}</h3>
                <div className="divide-y">
                  {g.items.map((item) => <ResearchEntry key={item.id} item={item} headingLevel={4} />)}
                </div>
              </section>
            ))}
          </div>
        )}
        {d.total > PAGE_SIZE && (
          <nav aria-label="Research pages" className="mt-4 flex items-center gap-3 text-sm">
            <button type="button" disabled={page === 0} onClick={() => setPage((p) => p - 1)} className="rounded-md border px-3 py-1.5 disabled:opacity-40">Previous</button>
            <button type="button" disabled={last >= d.total} onClick={() => setPage((p) => p + 1)} className="rounded-md border px-3 py-1.5 disabled:opacity-40">Next</button>
          </nav>
        )}
      </>
    );
  }
  return (
    <section aria-labelledby="research-title">
      <h2 id="research-title" className="type-section">Institutional research</h2>
      <p className="mt-1.5 max-w-[65ch] text-sm text-muted-foreground">
        AI summaries of published commentary, each checked against its document and reviewed by a person. They are
        interpretations, not official statistics.
      </p>
      <div className="mt-5">{body}</div>
    </section>
  );
}
