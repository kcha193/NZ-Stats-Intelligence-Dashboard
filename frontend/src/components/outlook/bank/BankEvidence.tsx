import { useEffect, useId, useRef, type KeyboardEvent } from "react";
import type { BankForecast } from "@/api/bank";
import { formatForecastValue } from "@/charts/forecasts";
import { formatCivilDate } from "@/lib/format";
import { UNIT_LABELS } from "@/pages/ResearchDetail";
import { ADJUSTMENT_LABELS, KIND_LABELS } from "./labels";

const FOCUSABLE = 'a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex="-1"])';

/**
 * The evidence behind one bank forecast: the source passage, where it sits in the report, who made the forecast and
 * which checker passed it. A modal dialog: focus moves in, Tab stays inside, Escape or Close returns focus to the cell.
 */
export function BankEvidence({ item, onClose }: { item: BankForecast; onClose: () => void }) {
  const titleId = useId();
  const panel = useRef<HTMLDivElement>(null);
  const opener = useRef<Element | null>(typeof document === "undefined" ? null : document.activeElement);
  const f = item.forecast;
  const unit = UNIT_LABELS[f.unit ?? ""] ?? f.unit ?? "";
  const kind = KIND_LABELS[item.report_kind] ?? "quarterly outlook";

  useEffect(() => {
    const returnTo = opener.current;
    panel.current?.querySelector<HTMLElement>("button")?.focus();
    return () => {
      if (returnTo instanceof HTMLElement) returnTo.focus();
    };
  }, []);

  function onKeyDown(e: KeyboardEvent) {
    if (e.key === "Escape") {
      e.stopPropagation();
      onClose();
      return;
    }
    if (e.key !== "Tab" || !panel.current) return;
    const items = Array.from(panel.current.querySelectorAll<HTMLElement>(FOCUSABLE));
    if (items.length === 0) return;
    const first = items[0];
    const last = items[items.length - 1];
    const active = document.activeElement;
    if (e.shiftKey && active === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && active === last) {
      e.preventDefault();
      first.focus();
    } else if (!panel.current.contains(active)) {
      e.preventDefault();
      first.focus();
    }
  }

  const rows: [string, string][] = [
    ["Report", f.document_title],
    ["Report type", kind],
    ["Published", formatCivilDate(f.published_on)],
    ["Measure", item.measure],
    ["Period", f.horizon],
    ["Forecast", f.value === null || f.value === undefined ? "No number stated" : formatForecastValue(f.value, unit)],
    ["Adjustment", ADJUSTMENT_LABELS[item.adjustment] ?? "not stated"],
    ["Geography", item.geography],
    ["Forecast made by", item.forecast_author ?? "not stated"],
  ];
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 sm:items-center" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onKeyDown={onKeyDown}
        className="max-h-[90vh] w-full max-w-2xl space-y-4 overflow-y-auto rounded-t-lg border bg-background p-5 shadow-lg sm:rounded-lg"
      >
        <div className="flex items-start justify-between gap-4">
          <h2 id={titleId} className="type-card">{f.institution.name}: {f.indicator_label}, {f.horizon}</h2>
          <button type="button" onClick={onClose} className="min-h-11 rounded border px-3 text-sm hover:bg-muted focus-visible:outline focus-visible:outline-2">Close</button>
        </div>
        <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[10rem_1fr]">
          {rows.map(([term, value]) => (
            <div key={term} className="contents"><dt className="text-muted-foreground">{term}</dt><dd>{value}</dd></div>
          ))}
        </dl>
        <section aria-label="Source passages" className="space-y-3">
          <h3 className="text-sm font-semibold">Source passage{f.evidence.length === 1 ? "" : "s"}</h3>
          {f.evidence.map((e, i) => (
            <figure key={i} className="border-l-2 pl-3">
              <blockquote className="text-sm leading-relaxed">{e.quote}</blockquote>
              <figcaption className="mt-1 text-xs text-muted-foreground">Section {e.section_ordinal}{e.page ? `, page ${e.page}` : ""}</figcaption>
            </figure>
          ))}
        </section>
        <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[10rem_1fr]">
          <dt className="text-muted-foreground">Claim</dt><dd><code>{item.claim_path}</code></dd>
          <dt className="text-muted-foreground">Checker</dt><dd><span>{item.verifier_version}</span></dd>
          <dt className="text-muted-foreground">Result</dt>
          <dd>No automated issue detected. Automated checks, not a person, produced this result, and they can miss errors.</dd>
        </dl>
      </div>
    </div>
  );
}
