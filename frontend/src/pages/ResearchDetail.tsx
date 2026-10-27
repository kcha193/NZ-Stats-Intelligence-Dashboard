import { Link, useParams } from "react-router-dom";
import { useResearchSummary } from "@/api/hooks";
import type { Forecast, ResearchDetail as Detail, ResearchEvidence, ResearchStatement } from "@/api/types";
import { formatForecastValue } from "@/charts/forecasts";
import { ExternalLink } from "@/components/outlook/ExternalLink";
import { ProcessingBadges } from "@/components/outlook/ProcessingBadges";
import { AiLabel } from "@/components/outlook/ResearchEntry";
import { EmptyState, QueryBoundary } from "@/components/QueryBoundary";
import { formatAklDate, formatCivilDate } from "@/lib/format";
import { useDocumentTitle } from "@/seo/useDocumentTitle";

const UNIT_LABELS: Record<string, string> = {
  percent: "%", percentage_points: "percentage points", basis_points: "basis points", percent_of_gdp: "% of GDP",
  nzd: "NZ$", nzd_million: "NZ$ million", nzd_billion: "NZ$ billion", index: "index", persons: "people", ratio: "ratio",
};

function Evidence({ refs }: { refs: ResearchEvidence[] }) {
  return (
    <ul aria-label="Evidence" className="mt-2 space-y-2">
      {refs.map((e, i) => (
        <li key={i} className="border-l-2 border-accent-ink/40 pl-3 text-sm">
          <p className="text-xs text-muted-foreground">Section {e.section_ordinal + 1}{e.page ? `, page ${e.page}` : ""}</p>
          {e.quote && <blockquote className="mt-0.5 leading-relaxed">&ldquo;{e.quote}&rdquo;</blockquote>}
        </li>
      ))}
    </ul>
  );
}

function StatementBlock({ title, items }: { title: string; items: (ResearchStatement | null | undefined)[] }) {
  const list = items.filter((s): s is ResearchStatement => Boolean(s));
  if (list.length === 0) return null;
  return (
    <section aria-label={title}>
      <h3 className="font-display text-base font-semibold tracking-tight">{title}</h3>
      <ul className="mt-2 space-y-5">
        {list.map((s, i) => (
          <li key={i}>
            <p className="max-w-[72ch] leading-relaxed">{s.text}</p>
            <Evidence refs={s.evidence} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function ForecastRow({ f }: { f: Forecast }) {
  const unit = f.unit ? UNIT_LABELS[f.unit] ?? f.unit : null;
  return (
    <tr className="align-top">
      <th scope="row" className="py-2.5 pr-4 font-medium">{f.indicator_label}</th>
      <td className="py-2.5 pr-4">{f.horizon}</td>
      <td className="py-2.5 pr-4 tabular-nums">{f.value !== null && f.value !== undefined ? (unit ? formatForecastValue(f.value, unit) : String(f.value)) : "No number stated"}</td>
      <td className="py-2.5 pr-4">{f.direction}</td>
      <td className="py-2.5 pr-4">{f.scenario ? `Scenario: ${f.scenario}` : "Central"}</td>
      <td className="py-2.5 text-muted-foreground">
        {f.qualification ?? "None stated"}
        <Evidence refs={f.evidence} />
      </td>
    </tr>
  );
}

function DetailView({ d }: { d: Detail }) {
  const item = d.item;
  useDocumentTitle(item.document.title);
  const ai = item.display !== "link_only";
  return (
    <article className="space-y-10">
      <header className="border-b-2 border-rule-strong pb-6">
        <p className="text-sm"><Link className="text-accent-ink underline-offset-4 hover:underline" to="/economic-outlook">Economic outlook</Link></p>
        <p className="mt-4 text-sm font-semibold">{item.institution.name}</p>
        <h1 className="type-lead mt-1 max-w-[30ch]">{item.document.title}</h1>
        <dl className="mt-5 grid gap-x-8 gap-y-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
          <div><dt className="text-xs text-muted-foreground">Published by the institution</dt><dd>{formatCivilDate(item.document.published_on)}</dd></div>
          <div><dt className="text-xs text-muted-foreground">Document version</dt><dd>Version {item.document.version_no}, stored {formatAklDate(item.document.fetched_at)}</dd></div>
          <div><dt className="text-xs text-muted-foreground">Format</dt><dd>{item.document.format.toUpperCase()}{item.document.page_count ? `, ${item.document.page_count} pages` : ""}</dd></div>
          <div><dt className="text-xs text-muted-foreground">Original</dt><dd><ExternalLink href={item.document.url}>Read the original document</ExternalLink></dd></div>
        </dl>
        {ai && <div className="mt-4"><ProcessingBadges item={item} /></div>}
      </header>

      {ai ? (
        <section aria-labelledby="interpretation-title" className="space-y-8">
          <div>
            <h2 id="interpretation-title" className="type-section">What the document says</h2>
            <AiLabel className="mt-1.5" />
            <p className="mt-1 max-w-[72ch] text-sm text-muted-foreground">
              Each statement cites the section{item.display === "excerpt" ? " and the exact words" : ""} of the stored document it rests on.
              {item.display === "summary" ? " The source does not permit quoting, so locations are shown without excerpts." : ""}
            </p>
          </div>
          <StatementBlock title="Outlook" items={[item.outlook]} />
          <StatementBlock title="Key drivers" items={item.drivers} />
          <StatementBlock title="Risks" items={item.risks} />
          <StatementBlock title="Uncertainty" items={[item.uncertainty]} />
        </section>
      ) : (
        <EmptyState title="Link only" body="This source permits its publication details and a link only, so no summary or forecasts are shown here." />
      )}

      {ai && (
        <section aria-labelledby="forecast-claims-title">
          <h2 id="forecast-claims-title" className="type-section">Forecast claims</h2>
          <p className="mt-1.5 max-w-[72ch] text-sm text-muted-foreground">Forecasts the document states explicitly, with the horizon and qualification as written. Nothing is converted or inferred.</p>
          {d.forecasts.length === 0 ? (
            <p className="mt-4 text-sm text-muted-foreground">The document states no explicit forecast.</p>
          ) : (
            <div className="mt-4 overflow-x-auto">
              <table className="w-full min-w-[46rem] text-left text-sm">
                <caption className="sr-only">Forecast claims in this document</caption>
                <thead className="text-xs text-muted-foreground">
                  <tr>{["Indicator", "Horizon", "Value", "Direction", "Kind", "Qualification and evidence"].map((h) => <th key={h} scope="col" className="py-1.5 pr-4 font-medium">{h}</th>)}</tr>
                </thead>
                <tbody className="divide-y">{d.forecasts.map((f, i) => <ForecastRow key={i} f={f} />)}</tbody>
              </table>
            </div>
          )}
        </section>
      )}

      <section aria-labelledby="provenance-title" className="-mx-4 bg-surface-sunken px-4 py-8 lg:-mx-8 lg:px-8">
        <h2 id="provenance-title" className="type-section">Provenance</h2>
        <dl className="mt-5 grid gap-x-8 gap-y-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
          <div><dt className="text-xs text-muted-foreground">Model</dt><dd>{d.provenance.model} ({d.provenance.provider}, {d.provenance.hosted ? "hosted service" : "run locally"})</dd></div>
          <div><dt className="text-xs text-muted-foreground">Prompt and processing</dt><dd>{d.provenance.prompt_version}, {d.provenance.processing_version}</dd></div>
          <div><dt className="text-xs text-muted-foreground">Summary written</dt><dd>{formatAklDate(d.provenance.created_at)}</dd></div>
          <div><dt className="text-xs text-muted-foreground">Evidence checks</dt><dd>{d.provenance.verifier_version}, passed{item.processing.warnings ? ` with ${item.processing.warnings} warning${item.processing.warnings === 1 ? "" : "s"}` : ""}</dd></div>
          <div><dt className="text-xs text-muted-foreground">Human review</dt><dd>{formatCivilDate(item.processing.human_reviewed_on)}</dd></div>
          <div><dt className="text-xs text-muted-foreground">Approved for publication</dt><dd>{formatCivilDate(item.processing.published_here_on)}</dd></div>
        </dl>
        <p className="mt-5 max-w-[72ch] text-xs leading-relaxed text-muted-foreground">{item.processing.checks_scope}</p>
        <h3 className="mt-6 text-sm font-semibold">Document versions</h3>
        <ul className="mt-2 space-y-1 text-sm">
          {d.versions.map((v) => (
            <li key={v.version_no}>Version {v.version_no}, stored {formatAklDate(v.fetched_at)}{v.current ? " (current, summarised here)" : " (earlier)"}</li>
          ))}
        </ul>
      </section>
    </article>
  );
}

export default function ResearchDetail() {
  const { id = "" } = useParams();
  const n = /^\d{1,15}$/.test(id) ? Number(id) : NaN;
  const query = useResearchSummary(n);
  useDocumentTitle(query.data ? undefined : "Institutional research"); // the loaded page sets its own title
  const missing = (
    <div className="space-y-4">
      <EmptyState title="This research summary is not published here" body="It may never have been approved for publication, or it has been withdrawn or replaced by a newer summary." />
      <p className="text-sm"><Link className="font-medium text-accent-ink underline-offset-4 hover:underline" to="/economic-outlook">Back to the economic outlook</Link></p>
    </div>
  );
  if (!Number.isFinite(n)) return missing;
  return (
    <QueryBoundary query={query} isEmpty={(d) => d === null} empty={missing}>
      {(d) => (d ? <DetailView d={d} /> : missing)}
    </QueryBoundary>
  );
}
