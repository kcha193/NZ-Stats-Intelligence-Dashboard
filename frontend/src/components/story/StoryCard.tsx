import { Link } from "react-router-dom";
import { StatusBadge } from "@/components/StatusBadge";
import { formatAklDate } from "@/lib/format";
import { TOPICS } from "@/stories/topics";
import { CATEGORY_LABEL, type Story, type StoryCategory } from "@/stories/types";
import { StoryGraphic } from "./StoryGraphic";

/** Status worth flagging on a card; "final" and "published" are the unremarkable default. */
const flagged = (s: Story) =>
  [s.provenance.status === "corrected" ? "corrected" : null, s.dataStatus === "provisional" ? "provisional" : null]
    .filter((x): x is string => x !== null);

/** The category, named in words; its tone is a short rule beside the name and never carries meaning alone. */
export function CategoryMark({ category, className = "" }: { category: StoryCategory; className?: string }) {
  return (
    <p className={`flex items-center gap-2 text-xs font-medium text-muted-foreground ${className}`}>
      <span aria-hidden className={`cat-rule ${TOPICS[category].tone}`} />
      {CATEGORY_LABEL[category]}
    </p>
  );
}

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

export type CardVariant = "prominent" | "supporting" | "standard";

/**
 * One story, three compositions sharing a grammar (category, headline, number, graphic, provenance):
 * prominent leads with a large graphic, supporting sets the number beside its graphic, standard is the compact card.
 * The whole card is one link (the headline); the graphic carries its own text alternative.
 */
export function StoryCard({ story, variant = "standard" }: { story: Story; variant?: CardVariant }) {
  const headline = (
    <h3 id={`story-${story.id}`} className={variant === "prominent" ? "type-section" : "type-card"}>
      <Link to={`/stories/${story.id}`} className="after:absolute after:inset-0 after:content-[''] focus-visible:outline-none">
        {story.headline}
      </Link>
    </h3>
  );
  const number = (
    <p className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
      <span className={`type-figure ${variant === "prominent" ? "text-5xl" : variant === "supporting" ? "text-4xl" : "text-3xl"}`}>{story.stat.value}</span>
      <span className="text-xs text-muted-foreground">{story.stat.unit}</span>
    </p>
  );
  const frame = "lift group relative flex h-full flex-col rounded-md border bg-card hover:border-rule-strong/40 focus-within:ring-2 focus-within:ring-accent-ink focus-within:ring-offset-2 focus-within:ring-offset-background";
  if (variant === "prominent") {
    return (
      <article aria-labelledby={`story-${story.id}`} className={`${frame} p-5 sm:p-7`}>
        <CategoryMark category={story.category} />
        <div className="mt-3">{headline}</div>
        <p className="mt-3 max-w-[60ch] text-[0.9375rem] leading-relaxed text-muted-foreground">{story.dek}</p>
        <div className="mt-5">{number}</div>
        <figure className="mt-5 border-t pt-4">
          <StoryGraphic thumb={story.thumb} size="lg" />
        </figure>
        <div className="mt-auto pt-5"><StoryMeta story={story} /></div>
      </article>
    );
  }
  if (variant === "supporting") {
    return (
      <article aria-labelledby={`story-${story.id}`} className={`${frame} p-5`}>
        <CategoryMark category={story.category} />
        <div className="mt-2.5">{headline}</div>
        <div className="mt-4 grid items-end gap-4 xl:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
          {number}
          <StoryGraphic thumb={story.thumb} />
        </div>
        <div className="mt-auto pt-4"><StoryMeta story={story} /></div>
      </article>
    );
  }
  return (
    <article aria-labelledby={`story-${story.id}`} className={`${frame} p-4`}>
      <CategoryMark category={story.category} />
      <div className="mt-2.5">{headline}</div>
      <div className="mt-3">{number}</div>
      <div className="mt-4"><StoryGraphic thumb={story.thumb} /></div>
      <div className="mt-auto pt-4"><StoryMeta story={story} /></div>
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
