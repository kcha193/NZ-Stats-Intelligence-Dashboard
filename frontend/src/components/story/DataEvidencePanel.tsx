import { InsightList } from "@/components/InsightList";
import { monthLabel } from "@/lib/format";
import type { Story } from "@/stories/types";

// Up to three decimals, unpadded, so a published 2,739.6 is not dressed up as 2,739.600.
const precise = (v: number) => v.toLocaleString("en-NZ", { maximumFractionDigits: 3 }).replace("-", "−");

/** The exact published values behind the story, and the release analysis they came from. */
export function DataEvidencePanel({ story }: { story: Story }) {
  return (
    <section aria-labelledby="story-evidence" className="space-y-3">
      <h2 id="story-evidence" className="text-lg font-semibold">Evidence</h2>
      <div className="overflow-x-auto" role="region" aria-label="Values used in this story" tabIndex={0}>
        <table className="w-full min-w-[34rem] text-left text-sm">
          <caption className="mb-1 text-left text-xs text-muted-foreground">
            Values used in this story, unrounded, from release {story.provenance.releaseKey}.
          </caption>
          <thead className="text-xs text-muted-foreground">
            <tr>
              <th scope="col" className="py-1 pr-4 font-medium">Measure</th>
              <th scope="col" className="py-1 pr-4 font-medium">Period</th>
              <th scope="col" className="py-1 pr-4 text-right font-medium">Value</th>
              <th scope="col" className="py-1 pr-4 font-medium">Unit</th>
              <th scope="col" className="py-1 pr-4 font-medium">Status</th>
              <th scope="col" className="py-1 font-medium">Series</th>
            </tr>
          </thead>
          <tbody>
            {story.evidence.map((e) => (
              <tr key={`${e.seriesKey}-${e.period}-${e.label}`} className="border-t">
                <th scope="row" className="py-1 pr-4 font-normal">{e.label}</th>
                <td className="py-1 pr-4 whitespace-nowrap">{monthLabel(e.period)}</td>
                <td className="py-1 pr-4 text-right tabular-nums">{precise(e.value)}</td>
                <td className="py-1 pr-4">{e.unit}</td>
                <td className="py-1 pr-4">{e.status}</td>
                <td className="py-1 font-mono text-xs">{e.seriesKey}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {story.insights.length > 0 && (
        <details className="rounded-md border p-3">
          <summary className="cursor-pointer text-sm font-medium">Release analysis findings ({story.insights.length})</summary>
          <p className="mt-2 text-xs text-muted-foreground">
            Deterministic findings computed from the same release. Observations are computed from published values; inferences are labelled.
          </p>
          <div className="mt-3"><InsightList insights={story.insights} /></div>
        </details>
      )}
    </section>
  );
}
