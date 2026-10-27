import { useId, useState } from "react";
import { ChevronDown } from "lucide-react";
import { Link } from "react-router-dom";
import type { ResearchItem, ResearchStatement } from "@/api/types";
import { formatCivilDate } from "@/lib/format";
import { researchPath } from "@/lib/research";
import { ExternalLink } from "./ExternalLink";
import { ProcessingBadges } from "./ProcessingBadges";

/** The label every piece of model-written text carries. */
export function AiLabel({ className = "" }: { className?: string }) {
  return <p className={`text-xs font-medium text-muted-foreground ${className}`}>AI interpretation of the document. Not an official statistic.</p>;
}

function Statements({ title, items }: { title: string; items: ResearchStatement[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <h4 className="text-xs font-semibold text-foreground">{title}</h4>
      <ul className="mt-1 list-disc space-y-1 pl-4 text-sm leading-relaxed">
        {items.map((s, i) => <li key={i}>{s.text}</li>)}
      </ul>
    </div>
  );
}

/** One institutional research summary in the feed. The outlook is visible; drivers, risks and uncertainty expand. */
export function ResearchEntry({ item, headingLevel = 3 }: { item: ResearchItem; headingLevel?: 3 | 4 }) {
  const [open, setOpen] = useState(false);
  const panel = useId();
  const titleId = useId();
  const H = headingLevel === 3 ? "h3" : "h4";
  const more = item.drivers.length + item.risks.length + (item.uncertainty ? 1 : 0);
  return (
    <article aria-labelledby={titleId} className="py-5">
      <p className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
        <span className="font-semibold text-foreground">{item.institution.name}</span>
        <span>Published {formatCivilDate(item.document.published_on)}</span>
      </p>
      <H id={titleId} className="type-card mt-1">
        <Link className="rounded-sm hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-ink" to={researchPath(item.id)}>
          {item.document.title}
        </Link>
      </H>
      <ProcessingBadges item={item} />
      {item.outlook ? (
        <div className="mt-3 max-w-[72ch]">
          <AiLabel />
          <p className="mt-1 leading-relaxed">{item.outlook.text}</p>
        </div>
      ) : (
        <p className="mt-3 max-w-[72ch] text-sm text-muted-foreground">
          This source permits a link and its publication details only, so no summary is shown here.
        </p>
      )}
      {more > 0 && (
        <>
          <button
            type="button" aria-expanded={open} aria-controls={panel} onClick={() => setOpen((o) => !o)}
            className="mt-3 inline-flex items-center gap-1 rounded-sm text-sm font-medium text-accent-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-ink"
          >
            {open ? "Hide" : "Show"} drivers, risks and uncertainty
            <ChevronDown aria-hidden className={`size-4 transition-transform ${open ? "rotate-180" : ""}`} />
          </button>
          <div id={panel} hidden={!open} className="mt-3 grid max-w-[72ch] gap-4 sm:grid-cols-2">
            <Statements title="Key drivers" items={item.drivers} />
            <Statements title="Risks" items={item.risks} />
            {item.uncertainty && <Statements title="Uncertainty" items={[item.uncertainty]} />}
          </div>
        </>
      )}
      <p className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-sm">
        <Link className="font-medium text-accent-ink underline-offset-4 hover:underline" to={researchPath(item.id)}>
          Evidence{item.n_forecasts > 0 ? ` and ${item.n_forecasts} forecast${item.n_forecasts === 1 ? "" : "s"}` : ""}
        </Link>
        <ExternalLink className="text-muted-foreground" href={item.document.url}>Original document</ExternalLink>
      </p>
    </article>
  );
}
