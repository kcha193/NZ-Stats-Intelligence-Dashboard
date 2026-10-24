import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useReleases } from "@/api/hooks";
import { ChartCard } from "@/charts/ChartCard";
import { useChartTheme } from "@/charts/theme";
import { EmptyState, QueryBoundary } from "@/components/QueryBoundary";
import { Segmented } from "@/components/Segmented";
import { DataEvidencePanel } from "@/components/story/DataEvidencePanel";
import { KeyStatistic } from "@/components/story/KeyStatistic";
import { SourceAttribution } from "@/components/story/SourceAttribution";
import { StoryCard, StoryMeta } from "@/components/story/StoryCard";
import { KeyTerms } from "@/components/story/Term";
import { StoryExport } from "@/components/story/StoryExport";
import { formatAklDate } from "@/lib/format";
import { useDocumentTitle } from "@/seo/useDocumentTitle";
import { isPublished } from "@/lib/releaseStatus";
import { categoryOfId, neighbours, relatedStories, resolveStory } from "@/stories/engine";
import { figureView, variantsOf, type FigureView } from "@/stories/figures";
import { termsFor } from "@/stories/glossary";
import { inSentence, monthName } from "@/stories/text";
import { TOPICS } from "@/stories/topics";
import { CATEGORY_LABEL, type Story } from "@/stories/types";
import { useStories } from "@/stories/useStories";

/** A release Stats NZ has published for the same series, newer than the one this story uses and not yet ingested here. */
function NewerRelease({ story }: { story: Story }) {
  const q = useReleases({ limit: 200 });
  const [now] = useState(() => Date.now());
  const used = Date.parse(story.provenance.publishedAt);
  const newer = (q.data ?? [])
    .filter((r) => isPublished(r.status) && !r.has_analysis && r.series_slug === story.provenance.seriesSlug && r.release_key !== story.provenance.releaseKey)
    .filter((r) => Date.parse(r.published_at) > used && Date.parse(r.published_at) <= now)
    .sort((a, b) => Date.parse(b.published_at) - Date.parse(a.published_at))[0];
  if (!newer) return null;
  return (
    <p role="note" className="rounded-md border border-amber-600/50 bg-amber-50 p-3 text-sm text-amber-950 dark:bg-amber-950/30 dark:text-amber-100">
      Stats NZ published {newer.title} on {formatAklDate(newer.published_at)}. It has not been verified here yet, so this
      story still shows the {inSentence(story.referenceLabel)}.
    </p>
  );
}

function StoryFigure({ story, view, variant, setVariant }: { story: Story; view: FigureView; variant: string; setVariant: (v: string) => void }) {
  const variants = variantsOf(story);
  const p = story.provenance;
  return (
    <ChartCard
      title={view.title} question={view.question} unit={view.unit} caveat={view.caveat}
      source={{ label: `Stats NZ, ${p.title}`, url: p.pageUrl, updated: p.publishedAt, captured: p.capturedAt }}
      option={view.option} ariaLabel={view.ariaLabel} height={view.height}
      csvFilename={view.csvFilename} csvRows={view.csvRows}
      controls={variants && variants.options.length > 1 && <Segmented label={variants.label} value={variant} onChange={setVariant} options={variants.options} />}
    />
  );
}

function StoryBody({ story, stories }: { story: Story; stories: Story[] }) {
  useDocumentTitle(story.headline);
  const theme = useChartTheme();
  // One variant drives the chart, its CSV and the presentation export, so all three show the same values.
  const [variant, setVariant] = useState(variantsOf(story)?.initial ?? "");
  const view = figureView(story, variant, theme);
  const related = relatedStories(stories, story, 3);
  const { previous, next } = neighbours(stories, story.id);
  return (
    <article className="space-y-12" aria-labelledby="story-headline">
      <header className="grid gap-8 border-b-2 border-rule-strong pb-8 lg:grid-cols-12 lg:items-end">
        <div className="min-w-0 lg:col-span-8">
          <Link to={`/stories?category=${story.category}`} className="inline-flex items-center gap-2 rounded-sm text-xs font-medium text-muted-foreground hover:text-foreground hover:underline">
            <span aria-hidden className={`cat-rule ${TOPICS[story.category].tone}`} />
            {CATEGORY_LABEL[story.category]}
          </Link>
          <h1 id="story-headline" className="type-lead mt-3 max-w-[24ch]">{story.headline}</h1>
          <p className="mt-4 max-w-[62ch] text-lg leading-relaxed text-muted-foreground">{story.dek}</p>
          <div className="mt-5"><StoryMeta story={story} /></div>
        </div>
        <div className="min-w-0 lg:col-span-4 lg:border-l lg:pl-8">
          <KeyStatistic stat={story.stat} />
          {story.glance && <p className="mt-4 max-w-[40ch] text-sm leading-relaxed">{story.glance.plain}</p>}
        </div>
      </header>
      <NewerRelease story={story} />
      <div className="grid gap-8 lg:grid-cols-12">
        <div className="min-w-0 space-y-3 lg:col-span-8">
          <StoryFigure story={story} view={view} variant={variant} setVariant={setVariant} />
          <StoryExport story={story} view={view} theme={theme} />
        </div>
        <aside className="space-y-6 lg:col-span-4" aria-label="Key figures">
          {story.context.length > 0 && (
            <section aria-labelledby="story-context">
              <h2 id="story-context" className="font-display text-base font-semibold tracking-tight">In context</h2>
              <ul className="mt-3 space-y-3 text-sm leading-relaxed">
                {story.context.map((c) => <li key={c} className="border-l-2 border-accent-ink/60 pl-3">{c}</li>)}
              </ul>
            </section>
          )}
          <KeyTerms keys={termsFor(story)} />
        </aside>
      </div>
      <section aria-labelledby="story-explain" className="max-w-[68ch] space-y-4">
        <h2 id="story-explain" className="type-section">What the data shows</h2>
        {story.explanation.map((t) => <p key={t} className="text-[1.0625rem] leading-relaxed">{t}</p>)}
        <h3 className="pt-2 font-display text-base font-semibold tracking-tight">Read with care</h3>
        <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
          {story.caveats.map((c) => <li key={c}>{c}</li>)}
        </ul>
      </section>
      <section aria-labelledby="story-record" className="-mx-4 space-y-8 bg-surface-sunken px-4 py-10 lg:-mx-8 lg:px-8">
        <div>
          <h2 id="story-record" className="type-section">Data, definitions and sources</h2>
          <p className="mt-1.5 max-w-[65ch] text-sm text-muted-foreground">
            The exact published values behind this story, how they are defined, and where they come from.
          </p>
        </div>
        <DataEvidencePanel story={story} />
        <section aria-labelledby="story-method" className="max-w-[72ch]">
          <details>
            <summary className="cursor-pointer"><h3 id="story-method" className="inline font-display text-lg font-semibold tracking-tight">Methodology</h3></summary>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
              {story.methodology.map((m) => <li key={m}>{m}</li>)}
            </ul>
          </details>
        </section>
        <SourceAttribution story={story} />
      </section>
      {related.length > 0 && (
        <section aria-labelledby="story-related">
          <h2 id="story-related" className="type-section">Related stories</h2>
          <ul aria-label="Related stories" className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {related.map((s) => <li key={s.id} className="min-w-0"><StoryCard story={s} /></li>)}
          </ul>
        </section>
      )}
      <nav aria-label="Story navigation" className="grid gap-4 border-t pt-6 text-sm sm:grid-cols-2">
        {previous ? (
          <Link className="group rounded-sm" to={`/stories/${previous.id}`}>
            <span className="block text-xs text-muted-foreground">Previous story</span>
            <span className="font-medium group-hover:underline">{previous.headline}</span>
          </Link>
        ) : <span />}
        {next && (
          <Link className="group rounded-sm sm:text-right" to={`/stories/${next.id}`}>
            <span className="block text-xs text-muted-foreground">Next story</span>
            <span className="font-medium group-hover:underline">{next.headline}</span>
          </Link>
        )}
        <div className="flex flex-wrap gap-x-6 gap-y-2 font-medium sm:col-span-2">
          <Link className="text-accent-ink underline underline-offset-4" to={story.dashboard.to}>{story.dashboard.label}</Link>
          <Link className="underline underline-offset-4" to="/stories">All stories</Link>
        </div>
      </nav>
    </article>
  );
}

export default function StoryPage() {
  const { id = "" } = useParams();
  const { stories, sources, refetch } = useStories();
  // Only the story's own category has to settle before "not found" or "superseded" can be said; others load on.
  const category = categoryOfId(id);
  const found = stories.some((s) => s.id === id);
  const isLoading = !found && category !== null && sources[category] === "loading";
  // A failed request is not a missing story: say so and offer a retry. The message is generic; the request's own error is not shown.
  const isError = !found && category !== null && sources[category] === "error";
  const error = isError ? new Error("The data for this story could not be loaded.") : null;
  return (
    <QueryBoundary query={{ data: isLoading ? undefined : stories, error, isLoading, isError, refetch }}>
      {(all) => {
        const r = resolveStory(all, id);
        if (r.kind === "found") return <StoryBody key={r.story.id} story={r.story} stories={all} />;
        if (r.kind === "superseded") {
          return (
            <section className="max-w-[65ch] space-y-3 rounded-md border p-5">
              <h1 className="text-xl font-semibold">This story has been superseded</h1>
              <p className="text-sm text-muted-foreground">
                The address refers to {monthName(r.requested)} data, which a newer release has replaced. Figures for earlier
                periods are not reshown here, so that an old link never displays numbers it did not originally refer to.
              </p>
              <p className="text-sm">Current story: <Link className="font-medium underline underline-offset-2" to={`/stories/${r.current.id}`}>{r.current.headline}</Link></p>
            </section>
          );
        }
        return (
          <div className="space-y-3">
            <h1 className="text-xl font-semibold">Story not found</h1>
            <EmptyState title="No story matches this address" body="It may refer to data that has not been ingested. Browse the stories that are available." />
            <Link className="text-sm underline underline-offset-2" to="/stories">All stories</Link>
          </div>
        );
      }}
    </QueryBoundary>
  );
}
