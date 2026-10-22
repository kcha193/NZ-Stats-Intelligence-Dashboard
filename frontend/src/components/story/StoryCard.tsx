import { Link } from "react-router-dom";
import { StatusBadge } from "@/components/StatusBadge";
import { formatAklDate } from "@/lib/format";
import { CATEGORY_LABEL, type Story } from "@/stories/types";
import { MiniChart } from "./MiniChart";

/** Status worth flagging on a card; "final" and "published" are the unremarkable default. */
export const flagged = (s: Story) =>
  [s.provenance.status === "corrected" ? "corrected" : null, s.dataStatus === "provisional" ? "provisional" : null]
    .filter((x): x is string => x !== null);

export function StoryMeta({ story }: { story: Story }) {
  return (
    <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
      <span>{story.referenceLabel}</span>
      <span aria-hidden>·</span>
      <span>Published {formatAklDate(story.provenance.publishedAt)}</span>
      {flagged(story).map((f) => <StatusBadge key={f} status={f} />)}
    </p>
  );
}

export function StoryCard({ story }: { story: Story }) {
  return (
    <article aria-labelledby={`story-${story.id}`} className="relative flex h-full flex-col rounded-md border bg-card p-4 transition-colors hover:border-accent-ink/60 focus-within:ring-2 focus-within:ring-accent-ink focus-within:ring-offset-2 focus-within:ring-offset-background">
      <p className="kicker">{CATEGORY_LABEL[story.category]}</p>
      <div className="mt-3"><MiniChart thumb={story.thumb} /></div>
      <h3 id={`story-${story.id}`} className="mt-3 text-base font-semibold leading-snug text-balance">
        <Link to={`/stories/${story.id}`} className="after:absolute after:inset-0 after:content-[''] focus-visible:outline-none">
          {story.headline}
        </Link>
      </h3>
      <p className="mt-2 flex flex-wrap items-baseline gap-x-2">
        <span className="whitespace-nowrap text-2xl font-semibold tracking-tight tabular-nums">{story.stat.value}</span>
        <span className="text-xs text-muted-foreground">{story.stat.unit}</span>
      </p>
      <div className="mt-auto pt-3"><StoryMeta story={story} /></div>
    </article>
  );
}

export function StoryGrid({ stories, label = "Stories" }: { stories: Story[]; label?: string }) {
  return (
    <ul aria-label={label} className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {stories.map((s) => <li key={s.id} className="min-w-0"><StoryCard story={s} /></li>)}
    </ul>
  );
}
