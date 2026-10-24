import { Link } from "react-router-dom";
import { ROUTE_META } from "@/seo/routes";
import { useDocumentTitle } from "@/seo/useDocumentTitle";
import type { Overview as OverviewData } from "@/api/types";
import { useOverview } from "@/api/hooks";
import { isStaticMode } from "@/api/mode";
import { Freshness } from "@/components/Freshness";
import { Glance } from "@/components/home/Glance";
import { Indicators } from "@/components/home/Indicators";
import { Topics } from "@/components/home/Topics";
import { EmptyState, ErrorState, QueryBoundary } from "@/components/QueryBoundary";
import { ReleaseRow } from "@/components/ReleaseRow";
import { StoryCard } from "@/components/story/StoryCard";
import { StoryHero } from "@/components/story/StoryHero";
import { Skeleton } from "@/components/ui/skeleton";
import { formatAklDate, formatAklDateTime } from "@/lib/format";
import { arrangeCollection, glanceStories } from "@/stories/engine";
import type { Story } from "@/stories/types";
import { useStories } from "@/stories/useStories";

function Masthead({ d }: { d: OverviewData }) {
  const next = d.upcoming[0];
  return (
    <header className="grid gap-6 border-b-2 border-rule-strong pb-7 lg:grid-cols-12 lg:items-end">
      <div className="lg:col-span-8">
        <h1 className="type-masthead">New Zealand&rsquo;s economy, explained.</h1>
        <p className="mt-4 max-w-[58ch] text-lg leading-relaxed text-muted-foreground">
          Understand what&rsquo;s changing in prices, spending and migration through official statistics and interactive stories.
        </p>
      </div>
      <dl className="grid gap-3 text-sm sm:grid-cols-2 lg:col-span-4 lg:grid-cols-1 lg:border-l lg:pl-6">
        <div>
          <dt className="text-xs text-muted-foreground">Latest data</dt>
          <dd>
            {d.data_updated_at
              ? `${d.kpis.some((k) => k.metric.series_key.startsWith("ect.") || k.metric.series_key.startsWith("cpi.")) ? "Data" : "Migration data"} ingested ${formatAklDateTime(d.data_updated_at)}.`
              : isStaticMode() ? "No data has been published yet." : "No migration data has been ingested yet."}
          </dd>
        </div>
        {next && (
          <div>
            <dt className="text-xs text-muted-foreground">Next scheduled release</dt>
            <dd>{next.title}, {formatAklDate(next.published_at)}</dd>
          </div>
        )}
      </dl>
    </header>
  );
}

const SPAN: Record<number, string> = { 3: "lg:col-span-3", 4: "lg:col-span-4", 6: "lg:col-span-6", 12: "lg:col-span-12" };
/** Columns for the remaining stories at desktop: full rows of three, four in one row, and no empty cell at the end. */
function restSpan(i: number, n: number): string {
  if (n === 4) return SPAN[3];
  const rem = n % 3;
  return SPAN[rem && i >= n - rem ? (rem === 1 ? 12 : 6) : 4];
}

/** The collection under the lead: one prominent story, two supporting, then the rest, so the rhythm varies. */
function Collection({ lead, rest, total }: { lead: Story; rest: Story[]; total: number }) {
  const c = arrangeCollection(lead, rest);
  if (!c.prominent) return null;
  return (
    <section aria-labelledby="latest-stories">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="latest-stories" className="type-section">What&rsquo;s changing</h2>
        <Link className="text-sm font-medium text-accent-ink underline-offset-4 hover:underline" to="/stories">All {total} stories</Link>
      </div>
      <ul aria-label="Latest stories" className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-12">
        <li className="min-w-0 sm:col-span-2 lg:col-span-7 lg:row-span-2"><StoryCard story={c.prominent} variant="prominent" /></li>
        {c.supporting.map((s) => <li key={s.id} className="min-w-0 lg:col-span-5"><StoryCard story={s} variant="supporting" /></li>)}
        {c.rest.map((s, i) => <li key={s.id} className={`min-w-0 ${restSpan(i, c.rest.length)}`}><StoryCard story={s} /></li>)}
      </ul>
    </section>
  );
}

/** Everything built from the stories: the glance, the lead, the collection and the topic entrances. */
function StoryLayers() {
  const { stories, sources, isLoading, refetch } = useStories();
  // The lead is "the newest verified release", so it waits for every category rather than changing under the reader.
  if (isLoading) {
    return (
      <div role="status" aria-label="Loading stories" className="space-y-4">
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-80 w-full" />
      </div>
    );
  }
  const failed = Object.values(sources).includes("error");
  const error = failed && (
    <ErrorState error={new Error("Some story data could not be loaded, so those stories are missing below.")} onRetry={refetch} />
  );
  if (!stories.length) return error || null;
  const [lead, ...rest] = stories;
  return (
    <>
      {error}
      <Glance stories={glanceStories(stories)} />
      <StoryHero story={lead} />
      <Collection lead={lead} rest={rest} total={stories.length} />
      <Topics stories={stories} />
    </>
  );
}

function Operations({ d }: { d: OverviewData }) {
  const degraded = d.freshness.filter((s) => s.state !== "ok").length;
  return (
    <section aria-labelledby="operations-title" className="-mx-4 bg-surface-sunken px-4 py-10 lg:-mx-8 lg:px-8">
      <h2 id="operations-title" className="type-section">Releases and data quality</h2>
      <p className="mt-1.5 max-w-[65ch] text-sm text-muted-foreground">
        What Stats NZ has published, what comes next, and when this site last checked each source.
      </p>
      <div className="mt-6 grid gap-8 lg:grid-cols-12">
        <div className="space-y-8 lg:col-span-7">
          {d.featured && (
            <section aria-label="Featured release">
              <p className="text-xs font-medium text-muted-foreground">Featured release</p>
              <h3 className="mt-1 font-display text-lg font-semibold tracking-tight">{d.featured.release.title}</h3>
              {d.featured.first_insight && <p className="mt-1 max-w-[70ch] text-sm leading-relaxed">{d.featured.first_insight}</p>}
              <Link className="mt-2 inline-block text-sm font-medium underline underline-offset-4" to={`/releases/${d.featured.release.id}`}>
                Read the full release analysis
              </Link>
            </section>
          )}
          <section aria-label="Latest releases">
            <h3 className="border-b border-rule-strong/30 pb-2 font-display text-base font-semibold tracking-tight">Latest releases</h3>
            <ul className="divide-y">{d.latest_releases.map((r) => <ReleaseRow key={r.id} release={r} />)}</ul>
          </section>
        </div>
        <div className="space-y-8 lg:col-span-5">
          <section aria-label="Upcoming releases">
            <h3 className="border-b border-rule-strong/30 pb-2 font-display text-base font-semibold tracking-tight">Upcoming releases</h3>
            <ul className="divide-y">{d.upcoming.slice(0, 6).map((r) => <ReleaseRow key={r.id} release={r} />)}</ul>
            <Link className="mt-2 inline-block text-sm font-medium underline underline-offset-4" to="/calendar">Full release calendar</Link>
          </section>
          <section aria-label="Data freshness">
            <h3 className="border-b border-rule-strong/30 pb-2 font-display text-base font-semibold tracking-tight">Data freshness</h3>
            <details className="mt-3 group">
              <summary className="cursor-pointer text-sm">
                {d.freshness.length === 0
                  ? "No source has been checked yet"
                  : degraded ? `${degraded} of ${d.freshness.length} sources need attention` : `All ${d.freshness.length} sources checked and OK`}
                <span className="text-muted-foreground"> (show details)</span>
              </summary>
              <div className="mt-3"><Freshness sources={d.freshness} /></div>
            </details>
            <Link className="mt-3 inline-block text-sm font-medium underline underline-offset-4" to="/health">Data health</Link>
          </section>
          {d.inactive_categories.length > 0 && (
            <p className="text-xs text-muted-foreground">
              Not yet active (no verified source wired in): {d.inactive_categories.map((c) => c.name).join(", ")}.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}

export default function Overview() {
  useDocumentTitle(ROUTE_META["/"].title);
  const q = useOverview();
  return (
    <QueryBoundary
      query={q}
      isEmpty={(d) => d.kpis.length === 0 && d.latest_releases.length === 0 && d.upcoming.length === 0}
      empty={isStaticMode()
        ? <EmptyState title="No data has been published yet" body="This site publishes verified Stats NZ releases as they are checked. Nothing has passed verification yet." />
        : <EmptyState title="No data has been ingested yet" body="Run `nzstats discover` then `nzstats backfill`, or wait for the next scheduled check. The Data health page shows what has been attempted." />}
    >
      {(d) => (
        <div className="space-y-14 lg:space-y-16">
          <Masthead d={d} />
          <StoryLayers />
          {d.kpis.length > 0 && <Indicators kpis={d.kpis} />}
          <Operations d={d} />
        </div>
      )}
    </QueryBoundary>
  );
}
