import { useOverview } from "@/api/hooks";
import { useState } from "react";
import { ForecastComparison } from "@/components/outlook/ForecastComparison";
import { ForecastTrack } from "@/components/outlook/ForecastTrack";
import { InternalDrafts } from "@/components/outlook/InternalDrafts";
import { Pulse } from "@/components/outlook/Pulse";
import { ResearchFeed } from "@/components/outlook/ResearchFeed";
import { QueryBoundary } from "@/components/QueryBoundary";
import { ROUTE_META } from "@/seo/routes";
import { useDocumentTitle } from "@/seo/useDocumentTitle";

const READING_NOTES = [
  ["Observations and forecasts", "Stats NZ figures describe a period that has passed. Forecasts are institutions' expectations for a later one, and are always labelled as forecasts."],
  ["Publication date and observation period", "A release published in October can describe June. Every figure on this page shows both."],
  ["Interpretation is not evidence", "An official figure shown beside a forecast does not confirm or test any institution's explanation of it."],
  ["What is not here", "GDP, the labour market and the official cash rate are not series this site ingests, so only institutions' forecasts of them appear, never invented official values, and those forecasts are never scored."],
  ["Revisions and accuracy", "A revision is an institution changing its forecast for the same measure and horizon. Accuracy compares a forecast with the official outcome it named, published later. They answer different questions and are shown apart."],
  ["Agreement is not a forecast", "The median and range across institutions describe what was published. They are not calibrated, and agreement says nothing about being right."],
] as const;

export default function EconomicOutlook() {
  useDocumentTitle(ROUTE_META["/economic-outlook"].title);
  const overview = useOverview();
  const [indicator, setIndicator] = useState("cpi_inflation");
  const cpi = overview.data?.kpis.find((k) => k.metric.series_key === "cpi.index.nsa.all_groups");
  return (
    <div className="space-y-14">
      <header className="grid gap-6 border-b-2 border-rule-strong pb-7 lg:grid-cols-12 lg:items-end">
        <div className="lg:col-span-8">
          <h1 className="type-masthead">Economic outlook</h1>
          <p className="mt-4 max-w-[58ch] text-lg leading-relaxed text-muted-foreground">
            Official Stats NZ figures beside what institutions expect next, with every claim traced to its source.
          </p>
        </div>
        <dl className="grid gap-3 text-sm sm:grid-cols-2 lg:col-span-4 lg:grid-cols-1 lg:border-l lg:pl-6">
          <div>
            <dt className="text-xs text-muted-foreground">Official statistics</dt>
            <dd>Stats NZ releases, shown as published (CC BY 4.0)</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Institutional research</dt>
            <dd>Internal AI drafts on this machine, checked by automated rules only and not reviewed by a person. Summaries a person has approved appear only in the separate publishing workflow below.</dd>
          </div>
        </dl>
      </header>
      <QueryBoundary query={overview}>{(d) => <Pulse overview={d} />}</QueryBoundary>
      <InternalDrafts />
      <ResearchFeed />
      <ForecastComparison cpi={cpi} indicator={indicator} onIndicatorChange={setIndicator} />
      <ForecastTrack indicator={indicator} />
      <section aria-labelledby="reading-title" className="-mx-4 bg-surface-sunken px-4 py-10 lg:-mx-8 lg:px-8">
        <h2 id="reading-title" className="type-section">How to read this page</h2>
        <dl className="mt-6 grid gap-x-10 gap-y-6 md:grid-cols-2">
          {READING_NOTES.map(([term, body]) => (
            <div key={term} className="border-t border-rule-strong/30 pt-3">
              <dt className="text-sm font-semibold">{term}</dt>
              <dd className="mt-1 max-w-[60ch] text-sm leading-relaxed text-muted-foreground">{body}</dd>
            </div>
          ))}
        </dl>
      </section>
    </div>
  );
}
