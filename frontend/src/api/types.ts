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
export type EctDashboard = S['EctDashboardOut'];
export type PointOut = S["PointOut"];
export type RevisionsOut = S["RevisionsOut"];
export type CountriesOut = S["CountriesOut"];
export type CountryRank = S["CountryRank"];
export type CalendarOut = S["CalendarOut"];
export type Health = S["HealthOut"];
export type SourceHealth = S["SourceHealthOut"];
export type CpiDashboard = S["CpiDashboardOut"];
export type CpiSeries = S["CpiSeriesOut"];
export type CpiPoint = S["CpiPoint"];
export type CpiContributionBlock = S["CpiContributionBlock"];
export type CpiUnderlying = S["CpiUnderlyingOut"];

// Phase 3C: public institutional research (only ever served when publication is enabled and approved).
export type ResearchFeed = S["ResearchFeedOut"];
export type ResearchItem = S["ResearchItemOut"];
export type ResearchDetail = S["ResearchDetailOut"];
export type ResearchStatement = S["StatementOut"];
export type ResearchEvidence = S["EvidenceOut"];
export type Facet = S["FacetOut"];
export type ForecastComparison = S["ForecastComparisonOut"];
export type ForecastGroup = S["ForecastGroupOut"];
export type Forecast = S["ForecastOut"];
export type ExcludedForecast = S["ExcludedForecastOut"];
