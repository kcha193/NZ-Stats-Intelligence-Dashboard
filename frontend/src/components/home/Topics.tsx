import { Link } from "react-router-dom";
import { Term } from "@/components/story/Term";
import { TOPICS } from "@/stories/topics";
import type { Story, StoryCategory } from "@/stories/types";
import { GLANCE_ORDER } from "@/stories/engine";

/** Topic entrances: what is measured (fact), the newest finding (a link), and the two ways in: stories and data. */
export function Topics({ stories }: { stories: Story[] }) {
  return (
    <section aria-labelledby="topics-title">
      <h2 id="topics-title" className="type-section">Explore by topic</h2>
      <ul className="mt-5 space-y-3">
        {GLANCE_ORDER.map((c: StoryCategory) => {
          const t = TOPICS[c];
          const own = stories.filter((s) => s.category === c);
          return (
            <li key={c} className={`grid gap-x-8 gap-y-3 rounded-md ${t.wash} p-5 md:grid-cols-[minmax(0,16rem)_minmax(0,1fr)_auto] md:items-center`}>
              <div>
                <span aria-hidden className={`cat-rule ${t.tone}`} />
                <h3 className="mt-2 font-display text-xl font-semibold tracking-tight">{t.title}</h3>
              </div>
              <div className="min-w-0 space-y-1.5 text-sm">
                <p className="leading-relaxed">{t.blurb}</p>
                <p className="text-muted-foreground">
                  Measured by: <Term k={t.term}>{t.measured}</Term>
                </p>
                {own[0] && (
                  <p>
                    <span className="text-muted-foreground">Latest finding: </span>
                    <Link className="font-medium underline decoration-1 underline-offset-4 hover:decoration-2" to={`/stories/${own[0].id}`}>{own[0].headline}</Link>
                  </p>
                )}
              </div>
              <div className="flex flex-wrap gap-x-5 gap-y-2 text-sm font-medium md:flex-col md:items-end">
                <Link className="text-accent-ink underline-offset-4 hover:underline" to={`/stories?category=${c}`}>
                  {own.length} {own.length === 1 ? "story" : "stories"}
                </Link>
                <Link className="underline-offset-4 hover:underline" to={t.dashboard.to}>{t.dashboard.label}</Link>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
