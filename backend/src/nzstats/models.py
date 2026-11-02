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


class CorrectionRowOut(BaseModel):
    period: str
    original: float | None
    revised: float | None
    original_status: str | None
    revised_status: str | None
    original_std_error: float | None
    revised_std_error: float | None
    original_released_in: str | None
    revised_released_in: str | None


class CorrectionSeriesOut(BaseModel):
    series_key: str
    label: str
    unit: str
    n_changed: int
    changes: list[CorrectionRowOut]  # first eight changed periods; n_changed covers all periods


class CorrectionBlock(BaseModel):
    available: bool
    note: str
    against_captured_at: str | None
    captured_at: str
    series: list[CorrectionSeriesOut]


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
    corrections: CorrectionBlock
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


class CapabilitiesOut(BaseModel):
    """Feature switches the UI reads so it does not request routes the server has not turned on."""

    research_public: bool
    internal_drafts: bool = False


class RefreshRequest(BaseModel):
    manual: bool = False  # "Check now": skips the recent-check window, not the failure cooldown


class RefreshFailureOut(BaseModel):
    key: str  # a release key, or "calendar"
    outcome: str
    error_class: str | None


class RefreshPendingOut(BaseModel):
    release_key: str
    reason: Literal[
        "not_published_yet",
        "rejected_today",
        "blocked_cooldown",
        "catch_up_limit",
        "request_budget",
        "stopped",
    ]
    series_slug: str | None
    label: str | None
    reference_period: str | None
    period_label: str | None
    published_at: str | None


class LatestStatisticOut(BaseModel):
    series_slug: str
    label: str
    reference_period: str | None  # what the statistics describe, not when they were checked
    period_label: str | None  # as Stats NZ words it, e.g. "June 2026 quarter"
    published_at: str


class RefreshStatusOut(BaseModel):
    """The on-open refresh as the dashboard header shows it. Times are Pacific/Auckland ISO-8601."""

    mode: Literal["on_open", "scheduler", "off"]
    state: Literal["never", "running", "completed", "failed", "interrupted"]
    phase: Literal["checking", "downloading", "validating"] | None = None
    run_id: int | None = None
    trigger: Literal["open", "manual"] | None = None
    started_at: str | None = None
    finished_at: str | None = None
    last_success_at: str | None = None
    discovered: int = 0
    ingested: int = 0
    unchanged: int = 0
    requests: int = 0
    failures: list[RefreshFailureOut] = []
    pending: list[RefreshPendingOut] = []
    error_class: str | None = None
    data_version: str | None = None  # changes whenever verified data is committed, by any process
    latest: list[LatestStatisticOut] = []
    started: bool = False  # this request started a check (a reuse leaves it False)


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


class EctDashboardOut(BaseModel):
    analysis: ReleaseAnalysis
    series: list[SeriesDataOut]


class CpiPoint(BaseModel):
    period: str
    index: float
    quarterly_pct: float | None  # percent change from the preceding quarter, None if not computable
    annual_pct: float | None  # percent change from the same quarter a year earlier


class CpiSeriesOut(BaseModel):
    key: str
    slug: str
    name: str
    unit: str  # always "index"
    adjustment: str
    classification: str
    source_reference: str | None
    status: str
    points: list[CpiPoint]
    source_url: str | None


class CpiContributionItem(BaseModel):
    slug: str
    group: str
    points: float  # percentage points, exactly as Stats NZ published
    rank: int


class CpiContributionBlock(BaseModel):
    horizon: Literal["quarterly", "annual"]
    available: bool
    reference_period: str | None
    unit: str  # "percentage points"
    items: list[CpiContributionItem]
    sum_points: float | None
    headline_pct: float | None  # all-groups percentage change, computed from the published index
    gap_points: float | None  # headline_pct - sum_points: shown, never absorbed
    note: str


class CpiUnderlyingOut(BaseModel):
    key: str
    name: str
    unit: str  # "percent": quarterly change as published
    points: list[PointOut]


class CpiDashboardOut(BaseModel):
    analysis: ReleaseAnalysis
    reference_period: str
    published_at: str
    captured_at: str
    base: str
    series: list[CpiSeriesOut]
    contributions: list[CpiContributionBlock]
    underlying: list[CpiUnderlyingOut]
    sources: list[str]
    caveats: list[str]


class GdpSeriesOut(BaseModel):
    key: str
    name: str
    unit: str
    measure: Literal["level", "quarterly_change", "annual_change", "annual_average_change"]
    approach: Literal["production", "expenditure"]
    price_basis: Literal["chain_volume", "current_prices"]
    adjustment: str
    per_capita: bool
    definition: str
    points: list[PointOut]
    source_url: str | None


class FirstLatestRow(BaseModel):
    period: str
    first_value: float
    first_release: str  # title of the release the first value comes from
    first_is_publication: (
        bool  # False: original-publication provenance is unverified (earliest stored instead)
    )
    latest_value: float
    latest_release: str
    revision: float  # percentage points, latest minus first, as published to 1 d.p.


class FirstLatestTable(BaseModel):
    series_key: str
    label: str
    available: bool
    note: str
    rows: list[FirstLatestRow]


class GdpDashboardOut(BaseModel):
    analysis: ReleaseAnalysis
    reference_period: str
    published_at: str
    captured_at: str
    series: list[GdpSeriesOut]
    revisions: list[FirstLatestTable]
    sources: list[str]
    caveats: list[str]


class LabourSeriesOut(BaseModel):
    key: str
    name: str
    unit: str
    survey: Literal[
        "hlfs", "lci"
    ]  # Household Labour Force Survey or Labour Cost Index: never combined
    measure: Literal["rate", "level", "index", "quarterly_change", "annual_change"]
    adjustment: str
    definition: str
    points: list[PointOut]
    source_url: str | None


class LabourDashboardOut(BaseModel):
    analysis: ReleaseAnalysis
    reference_period: str
    published_at: str
    captured_at: str
    series: list[LabourSeriesOut]
    revisions: list[FirstLatestTable]
    sources: list[str]
    caveats: list[str]


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
    data_updated_at: str | None
    kpis: list[Kpi]
    latest_releases: list[ReleaseSummary]
    upcoming: list[ReleaseSummary]
    freshness: list[SourceHealthOut]
    featured: FeaturedOut | None
    inactive_categories: list[InactiveCategory]
