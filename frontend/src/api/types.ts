import type { components } from "./schema";

type S = components["schemas"];
export type Overview = S["OverviewOut"];
export type Kpi = S["Kpi"];
export type Metric = S["Metric"];
export type ChangeOut = S["ChangeOut"];
export type ReleaseSummary = S["ReleaseSummary"];
export type ReleaseDetail = S["ReleaseDetail"];
export type ReleaseAnalysis = S["ReleaseAnalysis"];
export type Insight = S["Insight"];
export type SeriesData = S["SeriesDataOut"];
export type PointOut = S["PointOut"];
export type RevisionsOut = S["RevisionsOut"];
export type CountriesOut = S["CountriesOut"];
export type CountryRank = S["CountryRank"];
export type CalendarOut = S["CalendarOut"];
export type Health = S["HealthOut"];
export type SourceHealth = S["SourceHealthOut"];
