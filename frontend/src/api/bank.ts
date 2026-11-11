/**
 * Internal bank-intelligence responses (Phase 4AE), hand-written like `drafts.ts`: these routes are mounted only by
 * `nzstats serve` on loopback with the internal drafts on, and are not in the published API that `schema.d.ts` is
 * generated from. They mirror `research/bank_models.py`. Nothing here is ever requested on the static site.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getJson } from "./client";
import { DASHBOARD_CLIENT, draftsAreOn, orUnpublished } from "./hooks";
import type { Consensus, ConsensusGroup, Forecast, ForecastComparison, ForecastEvaluation, ForecastHistory } from "./types";

export type BankState = "ok" | "stale" | "undated" | "missing" | "blocked" | "unsupported" | "permission_denied";
export type Adjustment = "seasonally_adjusted" | "unadjusted" | "not_stated";
export type ReportKind = "outlook" | "weekly" | "commentary" | "other";
export type Contributor = Consensus["groups"][number]["contributors"][number];

export type BankStance = { text: string; claim_status: "clean" | "warning" | "failed"; label: "AI interpretation" };
export type BankCard = {
  key: string;
  name: string;
  state: BankState;
  /** The report series behind a series-level state (null when the state applies to the whole bank). */
  worst_series: string | null;
  report_name: string | null;
  published_on: string | null;
  stance: BankStance | null;
};
export type BankSummary = { notice: string; cards: BankCard[] };

export type BankForecast = {
  forecast: Forecast;
  claim_path: string;
  report_kind: ReportKind;
  adjustment: Adjustment;
  geography: string;
  measure: string;
  forecast_author: string | null;
  verifier_version: string;
  document_version_id: number;
  /** How the figure was read: a checked model claim, or read directly from a table in the PDF (Phase 4AF). */
  extraction_method: "llm_verified" | "table";
};
export type BankExclusion = {
  institution_key: string;
  summary_id: number;
  claim_path: string | null;
  code: string;
  reason: string;
};
export type BankForecasts = {
  notice: string;
  banks: { key: string; name: string }[];
  forecasts: BankForecast[];
  comparison: { adjustment: Adjustment; comparison: ForecastComparison }[];
  excluded: BankExclusion[];
  /** Table figures against checked claims, by fixed class (counts only). Agreement is not proof. */
  table_reconciliation: Record<string, number>;
};

export type BankRevisions = { histories: { adjustment: Adjustment; history: ForecastHistory }[]; excluded: BankExclusion[] };

export type BankConsensusGroup = ConsensusGroup & {
  adjustment: Adjustment;
  title: "Consensus of banks" | "Two-bank comparison" | "Insufficient banks";
  disclaimer: "Not a market consensus.";
  markers: Contributor[];
};
export type Divergence = {
  group_key: string;
  indicator: string;
  indicator_name: string;
  basis_label: string;
  adjustment: Adjustment;
  horizon_label: string;
  unit_label: string;
  spread: number;
  median: number;
  banks: { key: string; name: string; value: number; distance_from_median: number }[];
};
export type BankConsensus = {
  consensus: { groups: BankConsensusGroup[]; excluded: BankExclusion[] };
  divergence: Divergence[];
};

export type BankSeriesStatus = {
  series_key: string;
  series_name: string;
  state: BankState;
  newest_published_on: string | null;
  ingested_at: string | null;
  analysed_at: string | null;
  last_checked_at: string | null;
};
export type BankStatus = { key: string; name: string; state: BankState; series: BankSeriesStatus[] };
export type BankFreshness = { banks: BankStatus[]; exit_code: number };

const ROOT = "/api/internal/bank-intelligence";

/** One internal route, only when the server says internal drafts are on. Off, unknown, 404 or static: no data. */
function useBankRoute<T>(name: string, query = "") {
  const client = useQueryClient();
  return useQuery({
    queryKey: ["bank-intelligence", name, query],
    queryFn: async ({ signal }) =>
      (await draftsAreOn(client)) ? orUnpublished(getJson<T>(`${ROOT}/${name}${query}`, signal, DASHBOARD_CLIENT)) : null,
  });
}

export const useBankSummary = () => useBankRoute<BankSummary>("summary");
export const useBankForecasts = () => useBankRoute<BankForecasts>("forecasts");
export const useBankRevisions = () => useBankRoute<BankRevisions>("revisions");
export const useBankConsensus = () => useBankRoute<BankConsensus>("consensus");
export const useBankFreshness = () => useBankRoute<BankFreshness>("freshness");
export const useBankEvaluation = (indicator: string) =>
  useBankRoute<ForecastEvaluation>("evaluation", `?indicator=${encodeURIComponent(indicator)}`);
