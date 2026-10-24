import { useQuery } from "@tanstack/react-query";
import { getJson } from "./client";
import { pollEvery } from "./mode";
import type {
  CalendarOut, CountriesOut, Health, Overview, ReleaseDetail, ReleaseSummary, RevisionsOut,
  SeriesData, EctDashboard, CpiDashboard,
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
