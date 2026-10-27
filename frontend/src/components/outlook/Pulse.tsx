import { useState } from "react";
import { Link } from "react-router-dom";
import type { Overview } from "@/api/types";
import { StatusBadge } from "@/components/StatusBadge";
import { formatAklDate } from "@/lib/format";
import { buildPulse, type PulseItem } from "@/lib/pulse";
import { TOPICS } from "@/stories/topics";
import { ExternalLink } from "./ExternalLink";

/** Columns by count, so no row ever ends with an empty cell: three stack until there is room for all three. */
const COLUMNS: Record<number, string> = { 2: "md:grid-cols-2", 3: "lg:grid-cols-3" };

function PulseEntry({ item }: { item: PulseItem }) {
  const m = item.kpi.metric;
  const stale = item.freshness.state === "stale";
  return (
    <li className="flex min-w-0 flex-col bg-background p-5">
      <h3 className="flex items-center gap-2 font-display text-base font-semibold tracking-tight">
        <span aria-hidden className={`cat-rule ${TOPICS[item.key].tone}`} />
        {item.title}
      </h3>
      <p className="mt-4 flex flex-wrap items-baseline gap-x-2">
        <span className="font-display text-4xl font-semibold tracking-tight [font-variant-numeric:proportional-nums]">{item.value}</span>
        <span className="text-sm text-muted-foreground">{item.unitNote}</span>
      </p>
      <p className="mt-3 max-w-[48ch] text-sm leading-relaxed">{item.sentence}</p>
      <dl className="mt-4 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 border-t pt-3 text-xs">
        <dt className="text-muted-foreground">Observation period</dt>
        <dd className="flex flex-wrap items-center gap-1.5">{m.period_label} <StatusBadge status={m.status} /></dd>
        <dt className="text-muted-foreground">Published</dt>
        <dd>{formatAklDate(item.kpi.published_at)}</dd>
        <dt className="text-muted-foreground">Freshness</dt>
        <dd>
          <span className={stale ? "font-medium text-amber-800 dark:text-amber-300" : ""}>{item.freshness.label}</span>
          {stale && <span className="block text-muted-foreground">{item.freshness.detail}</span>}
        </dd>
        {item.next && (
          <>
            <dt className="text-muted-foreground">Next release</dt>
            <dd>{formatAklDate(item.next.published_at)}</dd>
          </>
        )}
      </dl>
      <p className="mt-auto flex flex-wrap gap-x-4 gap-y-1 pt-4 text-sm">
        <Link className="font-medium text-accent-ink underline-offset-4 hover:underline" to={item.dashboard.to}>{item.dashboard.label}</Link>
        <ExternalLink className="text-muted-foreground" href={item.kpi.source_url}>Stats NZ release</ExternalLink>
      </p>
    </li>
  );
}

/** Section A: the latest verified official indicators, each with its period, publication date and freshness. */
export function Pulse({ overview, now }: { overview: Overview; now?: Date }) {
  const [renderedAt] = useState(() => new Date());
  const items = buildPulse(overview, now ?? renderedAt);
  return (
    <section aria-labelledby="pulse-title">
      <h2 id="pulse-title" className="type-section">Economic pulse</h2>
      <p className="mt-1.5 max-w-[65ch] text-sm text-muted-foreground">
        The latest official figures this site has downloaded and checked. Observation period is what a figure measures;
        published is when Stats NZ released it.
      </p>
      {items.length === 0 ? (
        <p className="mt-5 rounded-md border border-dashed p-5 text-sm text-muted-foreground">
          No verified Stats NZ release has been loaded yet, so there are no indicators to show.
        </p>
      ) : (
        <ul aria-label="Latest indicators" className={`mt-5 grid gap-px overflow-hidden rounded-md border bg-border ${COLUMNS[items.length] ?? ""}`}>
          {items.map((i) => <PulseEntry key={i.key} item={i} />)}
        </ul>
      )}
    </section>
  );
}
