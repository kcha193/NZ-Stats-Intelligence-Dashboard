import { useState } from "react";
import { useBankForecasts, useBankSummary, type BankForecasts, type BankSummary } from "@/api/bank";
import { DRAFT_NOTICE } from "@/components/outlook/InternalDrafts";
import { ErrorState } from "@/components/QueryBoundary";
import { Segmented } from "@/components/Segmented";
import { Skeleton } from "@/components/ui/skeleton";
import { BankCards } from "./BankCards";
import { BankForecastTable } from "./BankForecastTable";
import { INDICATORS } from "./labels";

/** Why there is nothing to read, in plain words (null when there is something). */
export function emptyReason(summary: BankSummary, forecasts: BankForecasts | null | undefined): string | null {
  const cards = summary.cards;
  if (cards.length > 0 && cards.every((c) => c.state === "permission_denied")) {
    return "No bank source has been granted access yet, so there is nothing to collect or show.";
  }
  if (cards.length > 0 && cards.every((c) => c.state === "permission_denied" || c.state === "missing") && !cards.some((c) => c.stance)) {
    return "No bank documents have been imported yet.";
  }
  if (forecasts && forecasts.forecasts.length === 0) {
    return "Bank documents are held, but no forecast is eligible yet: claims are left out until they pass the automated checks.";
  }
  return null;
}

/**
 * Bank outlooks (Phase 4AE): what ANZ, ASB, BNZ, Westpac and Kiwibank say and forecast, from reports held on this
 * machine. Shown only when the server has internal AI analysis on; the static site never asks for it.
 */
export function BankOutlook() {
  const summary = useBankSummary();
  const forecasts = useBankForecasts();
  const [indicator, setIndicator] = useState("cpi_inflation");
  const [bank, setBank] = useState("all");

  if (summary.isPending) {
    return <div role="status" aria-label="Loading bank outlooks" className="space-y-3"><Skeleton className="h-24 w-full" /></div>;
  }
  if (summary.isError) {
    return (
      <section aria-labelledby="bank-outlook-title">
        <h2 id="bank-outlook-title" className="type-section">Bank outlooks</h2>
        <div className="mt-4"><ErrorState error={summary.error} onRetry={() => void summary.refetch()} /></div>
      </section>
    );
  }
  if (!summary.data) return null;

  const cards = bank === "all" ? summary.data.cards : summary.data.cards.filter((c) => c.key === bank);
  const banks = (forecasts.data?.banks ?? summary.data.cards).filter((b) => bank === "all" || b.key === bank);
  const empty = emptyReason(summary.data, forecasts.data);
  return (
    <section aria-labelledby="bank-outlook-title" className="space-y-8">
      <div>
        <h2 id="bank-outlook-title" className="type-section">Bank outlooks</h2>
        <p className="mt-2 max-w-[70ch] text-sm text-muted-foreground">{DRAFT_NOTICE}</p>
      </div>
      <div className="flex flex-wrap gap-4">
        <Segmented
          label="Bank"
          value={bank}
          onChange={setBank}
          options={[{ value: "all", label: "All banks" }, ...summary.data.cards.map((c) => ({ value: c.key, label: c.name }))]}
        />
        <Segmented label="Indicator" value={indicator} onChange={setIndicator} options={INDICATORS} />
      </div>
      {empty && <p role="note" className="max-w-[70ch] rounded-md border p-4 text-sm">{empty}</p>}
      <BankCards cards={cards} />
      {forecasts.isError && <ErrorState error={forecasts.error} onRetry={() => void forecasts.refetch()} />}
      {forecasts.data && forecasts.data.forecasts.length > 0 && (
        <div className="space-y-3">
          <h3 className="type-card">Forecasts by bank</h3>
          <BankForecastTable data={forecasts.data} banks={banks} indicator={indicator} />
        </div>
      )}
    </section>
  );
}
