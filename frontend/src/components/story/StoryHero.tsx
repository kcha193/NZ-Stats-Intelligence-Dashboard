import { useMemo } from "react";
import { Link } from "react-router-dom";
import { EChart } from "@/charts/EChart";
import { useChartTheme } from "@/charts/theme";
import { formatAklDate } from "@/lib/format";
import { figureView, variantsOf } from "@/stories/figures";
import { CATEGORY_LABEL, type Story } from "@/stories/types";
import { KeyStatistic } from "./KeyStatistic";
import { StoryMeta } from "./StoryCard";

/** The homepage lead: the finding in words, its number, and the chart that shows it, above the fold. */
export function StoryHero({ story }: { story: Story }) {
  const theme = useChartTheme();
  const view = useMemo(() => figureView(story, variantsOf(story)?.initial ?? "", theme), [story, theme]);
  return (
    <section aria-labelledby="featured-story" className="grid gap-6 border-y-2 border-accent-ink py-6 lg:grid-cols-12 lg:gap-8">
      <div className="min-w-0 lg:col-span-5">
        <p className="kicker">Featured story · {CATEGORY_LABEL[story.category]}</p>
        <h2 id="featured-story" className="mt-2 text-3xl font-semibold leading-tight tracking-tight text-balance sm:text-4xl">
          {story.headline}
        </h2>
        <p className="mt-3 max-w-[60ch] text-base leading-relaxed text-muted-foreground">{story.dek}</p>
        <div className="mt-5"><KeyStatistic stat={story.stat} /></div>
        <div className="mt-4"><StoryMeta story={story} /></div>
        <div className="mt-5 flex flex-wrap gap-x-5 gap-y-2 text-sm font-medium">
          <Link className="text-accent-ink underline underline-offset-4" to={`/stories/${story.id}`}>Read the story</Link>
          <Link className="underline underline-offset-4" to={story.dashboard.to}>{story.dashboard.label}</Link>
        </div>
      </div>
      <figure className="min-w-0 lg:col-span-7">
        <figcaption className="text-sm font-medium">{view.title}</figcaption>
        <div className="mt-2"><EChart option={view.option} ariaLabel={view.ariaLabel} height={300} /></div>
        <p className="mt-2 text-xs text-muted-foreground">
          Unit: {view.unit}. Source: Stats NZ, {story.provenance.title}, published {formatAklDate(story.provenance.publishedAt)}. {view.caveat}
        </p>
      </figure>
    </section>
  );
}
