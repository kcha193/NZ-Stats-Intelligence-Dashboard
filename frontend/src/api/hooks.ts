import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ApiError, getJson } from "./client";
import { pollEvery } from "./mode";
import type {
  CalendarOut, CountriesOut, Health, Overview, ReleaseDetail, ReleaseSummary, RevisionsOut,
  SeriesData, EctDashboard, CpiDashboard, ResearchFeed, ResearchDetail, ForecastComparison,
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

export type FeedParams = {
  q?: string; institution?: string; topic?: string; indicator?: string;
  sort?: "newest" | "oldest" | "institution"; limit?: number; offset?: number;
};

export const useResearchFeed = (params: FeedParams = {}) =>
  useQuery({
    queryKey: ["research-feed", params],
    queryFn: ({ signal }) => orUnpublished(getJson<ResearchFeed>(`/api/research/feed${qs(params)}`, signal)),
    placeholderData: keepPreviousData,
  });

export const useResearchSummary = (id: number) =>
  useQuery({
    queryKey: ["research-summary", id],
    queryFn: ({ signal }) => orUnpublished(getJson<ResearchDetail>(`/api/research/summaries/${id}`, signal)),
    enabled: Number.isInteger(id) && id > 0,
  });

export type ForecastParams = { indicator?: string; institution?: string; horizon?: string };

export const useForecasts = (params: ForecastParams = {}) =>
  useQuery({
    queryKey: ["research-forecasts", params],
    queryFn: ({ signal }) => orUnpublished(getJson<ForecastComparison>(`/api/research/forecasts${qs(params)}`, signal)),
    placeholderData: keepPreviousData,
  });
