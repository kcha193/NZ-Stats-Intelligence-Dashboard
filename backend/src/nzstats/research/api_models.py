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
