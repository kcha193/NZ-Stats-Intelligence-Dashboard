import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { formatAklDate, formatAklDateTime } from "@/lib/format";
import type { Story } from "@/stories/types";

const STATUS: Record<string, string> = { published: "Published", corrected: "Corrected by Stats NZ" };

export function SourceAttribution({ story }: { story: Story }) {
  const p = story.provenance;
  const source = p.pageUrl
    ? <a className="underline underline-offset-2" href={p.pageUrl} target="_blank" rel="noreferrer">Stats NZ, {p.title}</a>
    : `Stats NZ, ${p.title}`;
  const rows: [string, ReactNode][] = [
    ["Source", source],
    ["Published", formatAklDate(p.publishedAt)],
    ["Reference period", story.referenceLabel],
    ["Release status", STATUS[p.status] ?? p.status],
    ["Data captured", `${formatAklDateTime(p.capturedAt)} (vintage)`],
    ["Licence", "Creative Commons Attribution 4.0 (CC BY 4.0). Independent; not endorsed by Stats NZ."],
  ];
  return (
    <section aria-labelledby="story-source" className="rounded-md border p-4">
      <h2 id="story-source" className="text-base font-semibold">Source</h2>
      <dl className="mt-2 grid grid-cols-1 gap-x-6 gap-y-1.5 text-sm sm:grid-cols-[10rem_1fr]">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-muted-foreground">{k}</dt>
            <dd className="min-w-0 break-words">{v}</dd>
          </div>
        ))}
      </dl>
      {p.releaseId !== null && (
        <Link className="mt-3 inline-block text-sm underline underline-offset-2" to={`/releases/${p.releaseId}`}>Full release analysis</Link>
      )}
    </section>
  );
}
