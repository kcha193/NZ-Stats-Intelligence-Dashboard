import { useMemo } from "react";
import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import { EChart } from "@/charts/EChart";
import { useChartTheme } from "@/charts/theme";
import { formatAklDate } from "@/lib/format";
import { figureView, variantsOf } from "@/stories/figures";
import { termsFor } from "@/stories/glossary";
import type { Story } from "@/stories/types";
import { KeyStatistic } from "./KeyStatistic";
import { CategoryMark, StoryMeta } from "./StoryCard";
import { KeyTerms } from "./Term";

/**
 * The homepage lead: an asymmetric band on the feature surface. The words and the one number sit in the narrow
 * column; the story's own chart (same option as the story page, with its annotations, units and caveat) takes the wide
 * one. The first line of context is the comparison that makes the number meaningful.
 */
export function StoryHero({ story }: { story: Story }) {
  const theme = useChartTheme();
  const view = useMemo(() => figureView(story, variantsOf(story)?.initial ?? "", theme), [story, theme]);
  const p = story.provenance;
  const comparison = story.context[0];
  return (
    <section aria-labelledby="featured-story" className="-mx-4 bg-surface-feature px-4 py-8 sm:py-10 lg:-mx-8 lg:px-8 lg:py-12">
      <div className="grid gap-8 lg:grid-cols-12 lg:gap-10">
        <div className="min-w-0 lg:col-span-5">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <p className="kicker">Featured story</p>
            <CategoryMark category={story.category} />
          </div>
          <h2 id="featured-story" className="type-lead mt-3">{story.headline}</h2>
          <p className="mt-4 max-w-[52ch] text-[1.0625rem] leading-relaxed text-muted-foreground">{story.dek}</p>
          <div className="mt-7 border-t border-rule-strong/15 pt-5"><KeyStatistic stat={story.stat} size="xl" /></div>
          {comparison && <p className="mt-4 max-w-[52ch] border-l-2 border-accent-ink pl-3 text-sm leading-relaxed">{comparison}</p>}
          <div className="mt-7 flex flex-wrap items-center gap-x-5 gap-y-3">
            <Link
              className="inline-flex items-center gap-2 rounded-md bg-accent-ink px-4 py-2.5 text-sm font-semibold text-background transition-colors hover:bg-accent-ink/90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-ink"
              to={`/stories/${story.id}`}
            >
              Read the story <ArrowRight aria-hidden className="size-4" />
            </Link>
            <Link className="text-sm font-medium underline decoration-1 underline-offset-4 hover:decoration-2" to={story.dashboard.to}>
              {story.dashboard.label}
            </Link>
          </div>
          <div className="mt-6"><StoryMeta story={story} /></div>
        </div>
        <figure className="min-w-0 lg:col-span-7">
          <figcaption>
            <span className="block font-display text-base font-semibold tracking-tight">{view.title}</span>
            <span className="mt-0.5 block text-sm text-muted-foreground">{view.question}</span>
          </figcaption>
          <div className="mt-3 border-t border-rule-strong/15 pt-3">
            <EChart option={view.option} ariaLabel={view.ariaLabel} height={view.height + 40} />
          </div>
          <p className="type-note mt-2 max-w-[90ch]">
            Unit: {view.unit}. {view.caveat} Source:{" "}
            {p.pageUrl
              ? <a className="underline underline-offset-2" href={p.pageUrl} target="_blank" rel="noreferrer">Stats NZ, {p.title}</a>
              : `Stats NZ, ${p.title}`}
            , published {formatAklDate(p.publishedAt)}.
          </p>
          <KeyTerms className="mt-4" keys={termsFor(story)} />
        </figure>
      </div>
    </section>
  );
}
