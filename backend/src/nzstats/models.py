"""Response contracts shared by insights and the API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ChangeOut(BaseModel):
    label: str
    comparison_period: str
    previous: float
    absolute: float
    percent: float | None  # None = not meaningful (zero/negative base or sign change)


class Evidence(BaseModel):
    series_key: str
    period: str
    value: float
    release_key: str  # the release whose vintage holds this observation


class Insight(BaseModel):
    id: str
    kind: Literal["observation", "inference"]
    text: str
    evidence: list[Evidence]
    caveat: str | None = None


class Metric(BaseModel):
    series_key: str
    label: str
    value: float
    unit: str
    frequency: str
    period: str
    period_label: str
    status: str
    std_error: float | None
    change_prior: ChangeOut | None
    change_year_ago: ChangeOut | None


class RevisionRowOut(BaseModel):
    period: str
    original: float
    revised: float
    absolute: float
    percent: float | None
    original_status: str
    revised_status: str


class RevisionBlock(BaseModel):
    available: bool
    note: str
    series_key: str
    against_title: str | None
    n_common: int
    n_revised: int
    mean_abs: float | None
    largest: list[RevisionRowOut]


class Decomposition(BaseModel):
    label: str
    series_key: str
    previous_release_title: str
    previous_period: str
    previous_published_value: float
    same_period_now: float
    new_period: str
    new_value: float
    revision_component: float
    new_period_component: float
    total_change: float


class PreviousComparison(BaseModel):
    available: bool
    note: str
    previous_release_title: str | None
    decompositions: list[Decomposition]


class Methodology(BaseModel):
    definitions: list[str]
    notes: list[str]
    source_url: str | None


class ReleaseSummary(BaseModel):
    id: int
    release_key: str
    title: str
    series_slug: str
    category: str
    importance: str
    period_label: str | None
    published_at: str  # Pacific/Auckland ISO-8601 with offset
    status: str
    headline: str | None
    page_url: str | None
    has_analysis: bool


class ReleaseAnalysis(BaseModel):
    release: ReleaseSummary
    executive_summary: list[Insight]
    headline_metrics: list[Metric]
    context: list[Insight]
    previous_comparison: PreviousComparison
    revisions: RevisionBlock
    interpretation: list[Insight]
    methodology: Methodology
    vintage_captured_at: str


class ReleaseDetail(BaseModel):
    release: ReleaseSummary
    analysis: ReleaseAnalysis | None
    unavailable_reason: str | None


class SourceHealthOut(BaseModel):
    source: str
    state: str
    last_checked_at: str | None
    last_success_at: str | None
    detail: str | None


class RunOut(BaseModel):
    release_key: str
    started_at: str
    outcome: str
    error_class: str | None
    detail: str | None


class HealthOut(BaseModel):
    generated_at: str
    database_ok: bool
    sources: list[SourceHealthOut]
    recent_runs: list[RunOut]
    release_counts: dict[str, int]
    series_count: int
    vintage_count: int


class CalendarOut(BaseModel):
    items: list[ReleaseSummary]
    last_checked_at: str | None
    last_success_at: str | None


class SeriesOut(BaseModel):
    key: str
    name: str
    unit: str
    frequency: str
    adjustment: str
    category: str
    definition: str
    definition_id: str
    latest_period: str | None
    n_vintages: int


class PointOut(BaseModel):
    period: str
    value: float
    status: str
    std_error: float | None
    released_in: str | None


class VintageOut(BaseModel):
    release_key: str
    title: str
    published_at: str
    captured_at: str
    source_kind: str
    layout_version: str
    # True when this vintage belongs to a bundle of its release that a later correction replaced
    # without this series, so its values are no longer part of the release as it stands.
    superseded: bool


class SeriesDataOut(BaseModel):
    series: SeriesOut
    vintage: VintageOut
    points: list[PointOut]
    source_url: str | None
    caveat: str


class RevisionHistoryRow(BaseModel):
    release_key: str
    title: str
    published_at: str
    n_common: int
    n_revised: int
    mean_abs: float | None
    max_abs_period: str | None
    max_abs: float | None


class Coverage(BaseModel):
    kind: Literal["release_files", "snapshot", "none"]
    n_vintages: int
    earliest_release: str | None
    note: str


class RevisionsOut(BaseModel):
    series: SeriesOut
    coverage: Coverage
    base: VintageOut | None
    compare: VintageOut | None
    source_url: str | None  # release page of the `compare` vintage
    n_common: int
    n_revised: int
    rows: list[RevisionRowOut]  # revised periods only, oldest first
    history: list[RevisionHistoryRow]


class CountryRank(BaseModel):
    name: str
    series_key: str
    value: float
    prior_value: float | None
    change: float | None
    change_percent: float | None
    share_percent: float | None
    provisional: bool
    # Whether the prior window includes a provisional month; None when the prior window is withheld.
    prior_provisional: bool | None = None


class CountryProvenance(BaseModel):
    release_key: str | None
    title: str | None
    published_at: str | None
    source_url: str | None
    captured_at: str | None
    bundle_sha256: str | None


class CountriesOut(BaseModel):
    provenance: CountryProvenance | None = None
    available: bool
    months: int
    period_start: str | None
    period_end: str | None
    total: float | None
    countries: list[CountryRank]
    regions: list[CountryRank]
    unallocated: CountryRank | None
    derived: bool
    note: str


class Kpi(BaseModel):
    metric: Metric
    release_id: int
    published_at: str
    source_url: str | None


class FeaturedOut(BaseModel):
    release: ReleaseSummary
    headline: str | None
    first_insight: str | None


class InactiveCategory(BaseModel):
    name: str
    reason: str


class OverviewOut(BaseModel):
    generated_at: str
    kpis: list[Kpi]
    latest_releases: list[ReleaseSummary]
    upcoming: list[ReleaseSummary]
    freshness: list[SourceHealthOut]
    featured: FeaturedOut | None
    inactive_categories: list[InactiveCategory]
