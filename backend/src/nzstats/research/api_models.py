"""Public response models for the research API (Phase 3C).

Every field here may be shown to anyone who can reach the API, so the models are an allowlist: nothing private is
copied in by accident. Raw model output, document text, reviewer names, review and publication notes, error text,
model parameters, usage and cost have no field. Verbatim quotes appear only at the `excerpt` display level.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

INTERPRETATION_LABEL = "AI interpretation of the document. Not an official statistic."
CHECKS_SCOPE = (
    "Automated checks matched every quote, number, unit, horizon and page against the stored document. They do"
    " not test economic accuracy; a person reviewed the summary before it was published here."
)
COMPARISON_NOTE = (
    "Forecasts are compared only when the indicator, unit, statistical basis and horizon all match, and central"
    " forecasts are never mixed with scenarios. Each institution's latest published forecast is shown."
)

Display = Literal["link_only", "summary", "excerpt"]
Kind = Literal["central", "scenario"]


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InstitutionOut(_Out):
    key: str
    name: str
    kind: str


class EvidenceOut(_Out):
    section_ordinal: int
    page: int | None
    quote: str | None  # None below the `excerpt` display level


class StatementOut(_Out):
    text: str
    evidence: list[EvidenceOut]


class DocumentOut(_Out):
    title: str
    url: str
    published_on: str | None  # the institution's publication date (Pacific/Auckland civil date)
    version_no: int
    fetched_at: str  # when this version was stored (Pacific/Auckland ISO-8601)
    format: str
    page_count: int | None


class VersionOut(_Out):
    version_no: int
    fetched_at: str
    current: bool


class ProcessingOut(_Out):
    ai_summary: Literal[True] = True
    evidence_verified: Literal[True] = True
    human_reviewed_on: str  # date only: the reviewer's name and note stay private
    published_here_on: str
    verifier_version: str
    warnings: int
    checks_scope: str = CHECKS_SCOPE


class ProvenanceOut(_Out):
    provider: str
    model: str
    hosted: bool
    prompt_version: str
    processing_version: str
    verifier_version: str
    created_at: str


class ForecastOut(_Out):
    summary_id: int
    institution: InstitutionOut
    document_title: str
    published_on: str | None  # the forecast's vintage
    indicator: str
    indicator_label: str
    horizon: str  # as the document states it
    value: float | None
    unit: str | None
    direction: str
    scenario: str | None  # None: the central forecast
    qualification: str | None
    evidence: list[EvidenceOut]


class ResearchItemOut(_Out):
    id: int
    institution: InstitutionOut
    document: DocumentOut
    display: Display
    topics: list[str]
    indicators: list[str]
    outlook: StatementOut | None  # None at `link_only`
    drivers: list[StatementOut]
    risks: list[StatementOut]
    uncertainty: StatementOut | None
    n_forecasts: int
    processing: ProcessingOut
    interpretation_label: str = INTERPRETATION_LABEL
    not_official_statistic: Literal[True] = True


class FacetOut(_Out):
    value: str
    label: str
    count: int


class ResearchFeedOut(_Out):
    items: list[ResearchItemOut]
    total: int
    limit: int
    offset: int
    institutions: list[FacetOut]
    topics: list[FacetOut]
    indicators: list[FacetOut]


class ResearchDetailOut(_Out):
    item: ResearchItemOut
    forecasts: list[ForecastOut]
    provenance: ProvenanceOut
    versions: list[VersionOut]


class ForecastRowOut(_Out):
    forecast: ForecastOut
    earlier_vintages: list[ForecastOut]


class ForecastGroupOut(_Out):
    key: str
    indicator: str
    indicator_name: str
    unit: str
    unit_label: str
    basis: str
    basis_label: str
    horizon_key: str
    horizon_label: str
    kind: Kind
    scenario: str | None
    rows: list[ForecastRowOut]
    comparable: bool  # two or more institutions
    note: str


class ExcludedForecastOut(_Out):
    forecast: ForecastOut
    reason: str


class ForecastComparisonOut(_Out):
    groups: list[ForecastGroupOut]
    excluded: list[ExcludedForecastOut]
    indicators: list[FacetOut]
    institutions: list[FacetOut]
    horizons: list[FacetOut]
    note: str = COMPARISON_NOTE


# --- Phase 3D-B: forecast history, evaluation and consensus -------------------------------------------------------
HISTORY_NOTE = (
    "A vintage is one published document's forecast. A revision is a change of value for the same institution, measure,"
    " horizon and kind; a change of measure (for example annual average to through the year) is shown separately and is"
    " never a revision."
)


class ForecastVintageOut(_Out):
    summary_id: int
    published_on: str | None
    document_title: str
    value: float
    indicator_label: str  # as the document states it
    horizon: str  # as the document states it
    qualification: str | None
    evidence: list[EvidenceOut]
    superseded: bool  # a later vintage of the same identity exists
    revision: float | None  # value minus the previous vintage's value; None for the first


class ForecastSeriesOut(_Out):
    key: str  # institution plus the comparison group key
    target_key: str  # the comparison group key: the same target for every institution
    institution: InstitutionOut
    indicator: str
    indicator_name: str
    unit: str
    unit_label: str
    basis: str
    basis_label: str
    horizon_key: str
    horizon_label: str
    kind: Kind
    scenario: str | None
    vintages: list[ForecastVintageOut]  # oldest first
    latest: ForecastVintageOut
    n_revisions: int
    total_revision: float | None  # latest minus first; None with one vintage


class MeasureChangeOut(_Out):
    institution: InstitutionOut
    indicator: str
    indicator_name: str
    horizon_key: str
    horizon_label: str
    kind: Kind
    scenario: str | None
    from_basis: str
    from_basis_label: str
    to_basis: str
    to_basis_label: str
    from_summary_id: int
    from_published_on: str | None
    to_summary_id: int
    to_published_on: str | None
    note: str


class ForecastHistoryOut(_Out):
    series: list[ForecastSeriesOut]
    measure_changes: list[MeasureChangeOut]
    excluded: list[ExcludedForecastOut]
    note: str = HISTORY_NOTE


EVALUATION_NOTE = (
    "Errors are forecast minus the official outcome. CPI, GDP and the unemployment rate can be evaluated here; the"
    " OCR cannot (no approved source). Each forecast is matched to the"
    " quarter it names, on the measure it states, and only if it was published before that quarter's figure was released."
    " First-published scores require an uncorrected source captured on the official release day; historical captures are earliest stored and are not scored as first published."
    " Summary statistics need at least four distinct outcome quarters, each scored on the institution's latest vintage in the horizon band, and a ranking needs at least eight targets forecast by every"
    " ranked institution at the same horizon. No significance test is run."
)
CONSENSUS_NOTE = (
    "A descriptive summary of the latest published central forecasts from independent institutions. It is not"
    " statistically calibrated and it is not an independent forecast."
)
Band = Literal["h0", "h1_2", "h3_4", "h5_8", "h9"]


class ActualOut(_Out):
    value: float
    release: str  # the Stats NZ release title
    released_on: str  # Pacific/Auckland date
    first_release: bool  # False: original-publication provenance is unverified (earliest stored)


class EvaluatedForecastOut(_Out):
    forecast: ForecastOut
    measure: str
    measure_label: str
    target_quarter: str  # YYYY-MM
    target_label: str
    horizon_quarters: int  # from the quarter of publication to the target quarter
    band: Band
    status: Literal["matched", "pending"]
    first: ActualOut | None
    latest: ActualOut | None
    error_first: float | None
    error_latest: float | None
    outcome_revision: float | None  # latest minus first actual


class AccuracySummaryOut(_Out):
    institution: InstitutionOut
    measure: str
    measure_label: str
    band: Band
    n: int
    sufficient: bool
    mean_error: float | None
    mae: float | None
    rmse: float | None


class RankingEntryOut(_Out):
    institution: InstitutionOut
    n: int
    mae: float
    rmse: float
    mean_error: float


class RankingOut(_Out):
    measure: str
    measure_label: str
    available: bool
    reason: str
    matched_cells: int
    entries: list[RankingEntryOut]


class CoverageOut(_Out):
    institution: InstitutionOut
    matched: int
    pending: int
    excluded: int


class ForecastEvaluationOut(_Out):
    indicator: str
    state: Literal["available", "no_official_series", "nothing_to_evaluate"]
    official_series: str | None
    unavailable_reason: str | None = None  # set with state "no_official_series"
    actuals_as_of: str | None  # the newest stored release's title for the indicator
    actuals_released_on: str | None  # its Pacific/Auckland publication date
    vintages_from: str | None
    vintages_to: str | None
    evaluated: list[EvaluatedForecastOut]
    excluded: list[ExcludedForecastOut]
    summaries: list[AccuracySummaryOut]
    rankings: list[RankingOut]
    coverage: list[CoverageOut]
    min_for_summary: int
    min_for_ranking: int
    note: str = EVALUATION_NOTE


class ContributorOut(_Out):
    key: str
    name: str
    value: float
    published_on: str | None
    summary_id: int


class ConsensusGroupOut(_Out):
    key: str
    indicator: str
    indicator_name: str
    unit: str
    unit_label: str
    basis: str
    basis_label: str
    horizon_key: str
    horizon_label: str
    kind: Literal["central"] = "central"  # scenarios never form a consensus
    status: Literal["available", "insufficient"]
    n: int
    mean: float | None
    median: float | None
    minimum: float | None
    maximum: float | None
    range: float | None
    std_dev: float | None  # three or more institutions
    outliers_assessed: bool  # five or more institutions
    outliers: list[ContributorOut]
    contributors: list[ContributorOut]
    excluded: list[ExcludedForecastOut]
    as_of: str | None
    note: str = CONSENSUS_NOTE


class ConsensusOut(_Out):
    groups: list[ConsensusGroupOut]
    note: str = CONSENSUS_NOTE
