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
import { StoryMeta } from "@/components/story/StoryCard";
import { StoryExport } from "@/components/story/StoryExport";
import { formatAklDate } from "@/lib/format";
import { resolveStory } from "@/stories/engine";
import { figureView, variantsOf, type FigureView } from "@/stories/figures";
import { inSentence, monthName } from "@/stories/text";
import { CATEGORY_LABEL, type Story } from "@/stories/types";
import { useStories } from "@/stories/useStories";

/** A release Stats NZ has already published for the same series, newer than the one this story uses. */
function NewerRelease({ story }: { story: Story }) {
  const q = useReleases({ limit: 200 });
  const [now] = useState(() => Date.now());
  const used = Date.parse(story.provenance.publishedAt);
  const newer = (q.data ?? [])
    .filter((r) => r.series_slug === story.provenance.seriesSlug && r.release_key !== story.provenance.releaseKey)
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
      controls={variants && <Segmented label={variants.label} value={variant} onChange={setVariant} options={variants.options} />}
    />
  );
}

function StoryBody({ story }: { story: Story }) {
  const theme = useChartTheme();
  // One variant drives the chart, its CSV and the presentation export, so all three show the same values.
  const [variant, setVariant] = useState(variantsOf(story)?.initial ?? "");
  const view = figureView(story, variant, theme);
  return (
    <article className="space-y-8" aria-labelledby="story-headline">
      <header className="max-w-[72ch] space-y-3">
        <Link to={`/stories?category=${story.category}`} className="kicker hover:underline">{CATEGORY_LABEL[story.category]}</Link>
        <h1 id="story-headline" className="text-3xl font-semibold leading-tight tracking-tight text-balance sm:text-4xl lg:text-[2.75rem]">
          {story.headline}
        </h1>
        <p className="text-lg leading-relaxed text-muted-foreground">{story.dek}</p>
        <StoryMeta story={story} />
        <StoryExport story={story} view={view} theme={theme} />
      </header>
      <NewerRelease story={story} />
      <div className="grid gap-6 lg:grid-cols-12">
        <aside className="space-y-5 lg:col-span-4" aria-label="Key figures">
          <div className="border-t-2 border-accent-ink pt-4"><KeyStatistic stat={story.stat} /></div>
          {story.context.length > 0 && (
            <section aria-labelledby="story-context">
              <h2 id="story-context" className="text-sm font-semibold">In context</h2>
              <ul className="mt-2 space-y-2 text-sm leading-relaxed">
                {story.context.map((c) => <li key={c} className="border-l-2 pl-3">{c}</li>)}
              </ul>
            </section>
          )}
        </aside>
        <div className="min-w-0 lg:col-span-8"><StoryFigure story={story} view={view} variant={variant} setVariant={setVariant} /></div>
      </div>
      <section aria-labelledby="story-explain" className="max-w-[72ch] space-y-3">
        <h2 id="story-explain" className="text-lg font-semibold">What the data shows</h2>
        {story.explanation.map((t) => <p key={t} className="text-base leading-relaxed">{t}</p>)}
        <h3 className="pt-2 text-sm font-semibold">Read with care</h3>
        <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
          {story.caveats.map((c) => <li key={c}>{c}</li>)}
        </ul>
      </section>
      <DataEvidencePanel story={story} />
      <section aria-labelledby="story-method" className="max-w-[72ch]">
        <details>
          <summary className="cursor-pointer"><h2 id="story-method" className="inline text-lg font-semibold">Methodology</h2></summary>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
            {story.methodology.map((m) => <li key={m}>{m}</li>)}
          </ul>
        </details>
      </section>
      <SourceAttribution story={story} />
      <nav aria-label="Related" className="flex flex-wrap gap-x-6 gap-y-2 text-sm font-medium">
        <Link className="text-accent-ink underline underline-offset-4" to={story.dashboard.to}>{story.dashboard.label}</Link>
        <Link className="underline underline-offset-4" to="/stories">All stories</Link>
      </nav>
    </article>
  );
}

export default function StoryPage() {
  const { id = "" } = useParams();
  const { stories, isLoading } = useStories();
  return (
    <QueryBoundary query={{ data: isLoading ? undefined : stories, error: null, isLoading, isError: false, refetch: () => undefined }}>
      {(all) => {
        const r = resolveStory(all, id);
        if (r.kind === "found") return <StoryBody story={r.story} />;
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
