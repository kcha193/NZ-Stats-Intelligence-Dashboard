import { useState } from "react";
import { ROUTE_META } from "@/seo/routes";
import { useDocumentTitle } from "@/seo/useDocumentTitle";
import { useRelease, useReleases } from "@/api/hooks";
import { InsightList } from "@/components/InsightList";
import { QueryBoundary } from "@/components/QueryBoundary";
import { Segmented } from "@/components/Segmented";
import {
  ArrivalsDeparturesChart, CitizenshipChart, CountryChart, MonthlyVsAnnualChart, NetTrendChart,
  RevisionChart, type Range,
} from "./migration/charts";

const RANGE_OPTIONS = [
  { value: "5", label: "5 years" },
  { value: "10", label: "10 years" },
  { value: "all", label: "Since 2001" },
] as const;

function FindingsBody({ id }: { id: number }) {
  const detail = useRelease(id);
  return (
    <QueryBoundary query={detail}>
      {(d) =>
        d.analysis ? (
          <>
            <p className="mb-2 text-xs text-muted-foreground">From {d.release.title}. Observations are computed from published values; inferences are labelled.</p>
            <InsightList insights={[...d.analysis.executive_summary, ...d.analysis.context]} />
          </>
        ) : null
      }
    </QueryBoundary>
  );
}

function KeyFindings() {
  const list = useReleases({ category: "Migration", limit: 20 });
  return (
    <section aria-labelledby="findings" className="rounded-md border p-4">
      <h2 id="findings" className="text-lg font-semibold">Key statistical findings</h2>
      <QueryBoundary
        query={list}
        isEmpty={(rs) => !rs.some((r) => r.has_analysis)}
        empty={<p className="text-sm text-muted-foreground">No migration release has been analysed yet.</p>}
      >
        {(rs) => <FindingsBody id={rs.find((r) => r.has_analysis)!.id} />}
      </QueryBoundary>
    </section>
  );
}

export default function Migration() {
  useDocumentTitle(ROUTE_META["/migration"].title);
  const [range, setRange] = useState<Range>(10);
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">International migration</h1>
          <p className="text-sm text-muted-foreground">
            Outcomes-based estimates of long-term migrant arrivals and departures. Monthly and year-ended figures are separate series.
          </p>
        </div>
        <Segmented
          value={String(range ?? "all")}
          onChange={(v) => setRange(v === "all" ? null : (Number(v) as 5 | 10))}
          options={RANGE_OPTIONS}
          label="Date range"
        />
      </div>
      <KeyFindings />
      <div className="grid gap-5 xl:grid-cols-2">
        <NetTrendChart range={range} />
        <ArrivalsDeparturesChart range={range} />
      </div>
      <MonthlyVsAnnualChart range={range} />
      <div className="grid gap-5 xl:grid-cols-2">
        <CitizenshipChart range={range} />
        <CountryChart />
      </div>
      <RevisionChart />
    </div>
  );
}
