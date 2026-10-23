import { ArrowDownRight, ArrowRight, ArrowUpRight } from "lucide-react";
import { Link } from "react-router-dom";
import { StatusBadge } from "@/components/StatusBadge";
import { CategoryMark } from "@/components/story/StoryCard";
import { Term } from "@/components/story/Term";
import { TOPICS } from "@/stories/topics";
import type { Glance as GlanceT, Story } from "@/stories/types";

const ARROW = { up: ArrowUpRight, down: ArrowDownRight, flat: ArrowRight } as const;

/**
 * Three headline measures, each in four layers: the number, what it measures (with an explainer), how it moved against
 * its proper comparator, and one plain sentence. Arrows are neutral ink: a rise is not "good" or "bad" here.
 */
export function Glance({ stories }: { stories: (Story & { glance: GlanceT })[] }) {
  if (!stories.length) return null;
  return (
    <section aria-labelledby="glance-title">
      <h2 id="glance-title" className="type-section">The economy at a glance</h2>
      <ul className="mt-5 grid border-y sm:grid-cols-3 sm:divide-x max-sm:divide-y">
        {stories.map((s) => {
          const g = s.glance;
          const Arrow = ARROW[g.direction];
          return (
            <li key={s.id} className="min-w-0">
              <article aria-labelledby={`glance-${s.id}`} className="group relative flex h-full flex-col py-5 sm:px-5 sm:first:pl-0 sm:last:pr-0">
                <CategoryMark category={s.category} />
                <h3 id={`glance-${s.id}`} className="mt-3 font-display text-lg font-semibold tracking-tight">
                  <Link to={`/stories/${s.id}`} className="after:absolute after:inset-0 after:content-[''] hover:underline hover:underline-offset-4 focus-visible:underline focus-visible:outline-none">
                    {g.metric}
                  </Link>
                </h3>
                <p className="type-figure mt-2 text-5xl md:text-[2.75rem] lg:text-6xl">{g.value}</p>
                <p className="mt-2 text-sm">
                  <span className="relative z-10"><Term k={TOPICS[s.category].term}>{g.measure}</Term></span>
                  <span className="text-muted-foreground">, {s.referenceLabel.replace(/^Year ended/, "year ended")}</span>
                </p>
                <p className="mt-3 flex items-start gap-1.5 text-sm font-medium">
                  <Arrow aria-hidden className="mt-0.5 size-4 shrink-0" />
                  {g.comparison}
                </p>
                <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">{g.plain}</p>
                {s.dataStatus === "provisional" && <p className="mt-3"><StatusBadge status="provisional" /></p>}
              </article>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
