import { Link } from "react-router-dom";
import { ROUTE_META } from "@/seo/routes";
import { useDocumentTitle } from "@/seo/useDocumentTitle";

/** No OCR figure is shown anywhere until access to the Reserve Bank's data is approved (docs/data-sources/ocr.md). */
export default function OfficialCashRate() {
  useDocumentTitle(ROUTE_META["/ocr"].title);
  return (
    <div className="max-w-3xl space-y-5">
      <header>
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Monetary policy</p>
        <h1 className="text-xl font-semibold tracking-tight">Official Cash Rate</h1>
      </header>
      <section aria-labelledby="ocr-status" className="rounded-md border p-4">
        <h2 id="ocr-status" className="text-lg font-semibold">Not shown yet</h2>
        <p className="mt-2 text-sm">
          The Official Cash Rate is set and published by the Reserve Bank of New Zealand. Access to its data for this site is not yet
          approved: its terms restrict automated access without permission, and no access decision has been recorded. Until one is,
          this site shows no OCR figure and does not evaluate OCR forecasts.
        </p>
      </section>
      <section aria-labelledby="ocr-dates" className="space-y-2">
        <h2 id="ocr-dates" className="text-lg font-semibold">What this page will distinguish</h2>
        <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
          <li>The date a decision is announced, and the date the new rate takes effect (usually the next day).</li>
          <li>The change at each decision, in basis points.</li>
          <li>Monthly figures as the rate in force at month end or as the average over the month, which differ in a month with a decision.</li>
        </ul>
        <p className="text-sm"><Link className="underline underline-offset-2" to="/economic-outlook">Economic outlook</Link></p>
      </section>
    </div>
  );
}
