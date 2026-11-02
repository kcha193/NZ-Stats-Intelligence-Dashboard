import { keepPreviousData, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { ApiError, getJson } from "./client";
import type { DraftFeed, DraftItem } from "./drafts";
import { isStaticMode, pollEvery } from "./mode";
import type {
  CalendarOut, CountriesOut, Health, Overview, ReleaseDetail, ReleaseSummary, RevisionsOut,
  SeriesData, EctDashboard, CpiDashboard, GdpDashboard, LabourDashboard, ResearchFeed, ResearchDetail, ForecastComparison, ForecastHistory,
  ForecastEvaluation, Consensus, OpsStatus, Capabilities,
} from "./types";

const qs = (params: Record<string, string | number | undefined>): string => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
};

export const useOverview = () =>
  useQuery({ queryKey: ["overview"], queryFn: ({ signal }) => getJson<Overview>("/api/overview", signal), refetchInterval: pollEvery(60_000) });

export const useEct = () =>
  useQuery({
    queryKey: ["ect"],
    queryFn: ({ signal }) => getJson<EctDashboard>("/api/ect", signal),
    refetchInterval: pollEvery(60_000),
  });

export const useCpi = () =>
  useQuery({
    queryKey: ["cpi"],
    queryFn: ({ signal }) => getJson<CpiDashboard>("/api/cpi", signal),
    refetchInterval: pollEvery(60_000),
  });

export const useGdp = () =>
  useQuery({
    queryKey: ["gdp"],
    queryFn: ({ signal }) => getJson<GdpDashboard>("/api/gdp", signal),
    refetchInterval: pollEvery(60_000),
  });

export const useLabourMarket = () =>
  useQuery({
    queryKey: ["labour-market"],
    queryFn: ({ signal }) => getJson<LabourDashboard>("/api/labour-market", signal),
    refetchInterval: pollEvery(60_000),
  });

export const useReleases = (params: { status?: string; category?: string; limit?: number } = {}) =>
  useQuery({
    queryKey: ["releases", params],
    queryFn: ({ signal }) => getJson<ReleaseSummary[]>(`/api/releases${qs(params)}`, signal),
  });

export const useRelease = (id: number) =>
  useQuery({
    queryKey: ["release", id],
    queryFn: ({ signal }) => getJson<ReleaseDetail>(`/api/releases/${id}`, signal),
    enabled: Number.isFinite(id),
  });

export const useCalendar = (from?: string, to?: string) =>
  useQuery({
    queryKey: ["calendar", from, to],
    queryFn: ({ signal }) => getJson<CalendarOut>(`/api/calendar${qs({ from, to })}`, signal),
  });

export const useSeries = (key: string, vintage?: string) =>
  useQuery({
    queryKey: ["series", key, vintage],
    queryFn: ({ signal }) => getJson<SeriesData>(`/api/series/${key}${qs({ vintage })}`, signal),
  });

export const useRevisions = (key: string, base?: string, compare?: string) =>
  useQuery({
    queryKey: ["revisions", key, base, compare],
    queryFn: ({ signal }) => getJson<RevisionsOut>(`/api/revisions/${key}${qs({ base, compare })}`, signal),
  });

export const useCountries = (months = 12, top = 15) =>
  useQuery({
    queryKey: ["countries", months, top],
    queryFn: ({ signal }) => getJson<CountriesOut>(`/api/migration/countries${qs({ months, top })}`, signal),
  });

export const useHealth = () =>
  useQuery({ queryKey: ["health"], queryFn: ({ signal }) => getJson<Health>("/api/health", signal), refetchInterval: pollEvery(30_000) });

/** Operational status is a live, local-operator feature: a published snapshot has no scheduler to report on. */
export const useOpsStatus = () =>
  useQuery({
    queryKey: ["ops-status"],
    queryFn: ({ signal }) => getJson<OpsStatus>("/api/ops/status", signal),
    refetchInterval: pollEvery(30_000),
    enabled: !isStaticMode(),
    retry: false,
  });


/**
 * Research is "not published" (null) when the API answers 404: public research is switched off, nothing is eligible
 * for that address, or (static site) research is never in a snapshot. Every other failure is still an error.
 */
async function orUnpublished<T>(request: Promise<T>): Promise<T | null> {
  try {
    return await request;
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

/**
 * Internal drafts, only when the server says its switch is on. Off, unknown or the static site: no request, no draft.
 * These routes are outside the published API, so their types are in `drafts.ts`.
 */
async function draftsAreOn(client: QueryClient): Promise<boolean> {
  if (isStaticMode()) return false;
  try {
    const caps = await client.ensureQueryData({ queryKey: ["capabilities"], queryFn: ({ signal }) => getJson<Capabilities>("/api/capabilities", signal) });
    return caps.internal_drafts === true;
  } catch {
    return false;
  }
}

const DASHBOARD_CLIENT = { "X-NZStats-Client": "dashboard" };

export function useInternalDrafts() {
  const client = useQueryClient();
  return useQuery({
    queryKey: ["internal-drafts"],
    queryFn: async ({ signal }) =>
      (await draftsAreOn(client)) ? orUnpublished(getJson<DraftFeed>("/api/internal/drafts", signal, DASHBOARD_CLIENT)) : null,
  });
}

export function useInternalDraft(id: number) {
  const client = useQueryClient();
  return useQuery({
    queryKey: ["internal-draft", id],
    enabled: Number.isFinite(id),
    queryFn: async ({ signal }) =>
      (await draftsAreOn(client)) ? orUnpublished(getJson<DraftItem>(`/api/internal/drafts/${id}`, signal, DASHBOARD_CLIENT)) : null,
  });
}

export type FeedParams = {
  q?: string; institution?: string; topic?: string; indicator?: string;
  sort?: "newest" | "oldest" | "institution"; limit?: number; offset?: number;
};

/**
 * Live mode asks the server once whether public research is switched on. While it is off, the research hooks resolve to
 * "not published" without sending a request, so the browser does not log a 404 for every panel. The answer is cached
 * for the session; if the server cannot say (older server, network error) they try as before. The static site is
 * unchanged. Waiting for the answer happens inside each query, so its loading state stays truthful.
 */
async function researchIsOn(client: QueryClient): Promise<boolean> {
  if (isStaticMode()) return true;
  try {
    const caps = await client.ensureQueryData({ queryKey: ["capabilities"], queryFn: ({ signal }) => getJson<Capabilities>("/api/capabilities", signal), staleTime: Infinity });
    return caps.research_public;
  } catch {
    return true;
  }
}

async function research<T>(client: QueryClient, request: () => Promise<T>): Promise<T | null> {
  return (await researchIsOn(client)) ? orUnpublished(request()) : null;
}

export const useResearchFeed = (params: FeedParams = {}) => {
  const client = useQueryClient();
  return useQuery({
    queryKey: ["research-feed", params],
    queryFn: ({ signal }) => research(client, () => getJson<ResearchFeed>(`/api/research/feed${qs(params)}`, signal)),
    placeholderData: keepPreviousData,
  });
};

export const useResearchSummary = (id: number) => {
  const client = useQueryClient();
  return useQuery({
    queryKey: ["research-summary", id],
    queryFn: ({ signal }) => research(client, () => getJson<ResearchDetail>(`/api/research/summaries/${id}`, signal)),
    enabled: Number.isInteger(id) && id > 0,
  });
};

export type ForecastParams = { indicator?: string; institution?: string; horizon?: string };

export const useForecasts = (params: ForecastParams = {}) => {
  const client = useQueryClient();
  return useQuery({
    queryKey: ["research-forecasts", params],
    queryFn: ({ signal }) => research(client, () => getJson<ForecastComparison>(`/api/research/forecasts${qs(params)}`, signal)),
    placeholderData: keepPreviousData,
  });
};

export const useForecastHistory = (indicator: string) => {
  const client = useQueryClient();
  return useQuery({
    queryKey: ["research-forecast-history", indicator],
    queryFn: ({ signal }) => research(client, () => getJson<ForecastHistory>(`/api/research/forecast-history${qs({ indicator })}`, signal)),
    placeholderData: keepPreviousData,
  });
};

export const useForecastEvaluation = (indicator: string) => {
  const client = useQueryClient();
  return useQuery({
    queryKey: ["research-forecast-evaluation", indicator],
    queryFn: ({ signal }) => research(client, () => getJson<ForecastEvaluation>(`/api/research/forecast-evaluation${qs({ indicator })}`, signal)),
    placeholderData: keepPreviousData,
  });
};

export const useConsensus = (indicator: string) => {
  const client = useQueryClient();
  return useQuery({
    queryKey: ["research-consensus", indicator],
    queryFn: ({ signal }) => research(client, () => getJson<Consensus>(`/api/research/consensus${qs({ indicator })}`, signal)),
  });
};
