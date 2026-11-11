"""Response models for the internal bank-intelligence routes (Phase 4AE). An allowlist, like `api_models`.

These are served only on the loopback draft router (`bank_api`). No raw model output, reviewer, note, error text or
document text beyond the evidence quotes the draft page already shows has a field here.
"""

from __future__ import annotations

from typing import Literal

from nzstats.research.api_models import (
    ConsensusGroupOut,
    ContributorOut,
    ForecastComparisonOut,
    ForecastHistoryOut,
    ForecastOut,
    _Out,
)
from nzstats.research.bank_forecast import Adjustment
from nzstats.research.bank_status import State
from nzstats.research.banks import ReportKind

NOT_A_MARKET_CONSENSUS = "Not a market consensus."
ConsensusTitle = Literal["Consensus of banks", "Two-bank comparison", "Insufficient banks"]


class BankExclusionOut(_Out):
    """A claim or forecast left out of an analysis. `code` and `reason` are fixed strings, never source text."""

    institution_key: str
    summary_id: int
    claim_path: str | None
    code: str
    reason: str


class BankConsensusGroupOut(ConsensusGroupOut):
    adjustment: Adjustment
    title: ConsensusTitle
    disclaimer: Literal["Not a market consensus."] = NOT_A_MARKET_CONSENSUS
    markers: list[ContributorOut]  # reference institutions on the same measure; never contributors


class BankConsensusOut(_Out):
    groups: list[BankConsensusGroupOut]
    excluded: list[BankExclusionOut]


class DivergenceBankOut(_Out):
    key: str
    name: str
    value: float
    distance_from_median: float  # signed: this bank minus the group median


class DivergenceOut(_Out):
    group_key: str
    indicator: str
    indicator_name: str
    basis_label: str  # the measure (annual or quarterly change...), from the group
    adjustment: Adjustment
    horizon_label: str
    unit_label: str
    spread: float  # maximum minus minimum
    median: float
    banks: list[DivergenceBankOut]


# --- the route responses ------------------------------------------------------------------------------------------
# Same wording as `drafts_api.NOTICE` (a test pins them together); kept here so this module needs no draft import.
NOTICE = (
    "AI-generated analysis for internal use. Claims are checked automatically against source documents but may"
    " contain errors. Not independently reviewed."
)
VIEW_REASONS = {
    "claim_failed_checks": "The claim failed an automated check against its source.",
    "claim_has_warning": "The claim raised an automated warning.",
    "third_party_issuer": "The forecast is attributed to another organisation, not to this bank.",
    "no_value": "The claim states a direction but no number.",
    "table_third_party": "The table attributes the figure to another organisation, not to this bank.",
    "reconciliation_rounding": (
        "The table figure differs from the bank's checked claim only by rounding; the claim is used."
    ),
    "table_unresolved_reconciliation": (
        "The table figure and the bank's checked claim differ in unit, horizon or attribution, or cannot be"
        " matched one-to-one; neither is guessed."
    ),
}


class BankRefOut(_Out):
    key: str
    name: str


class BankForecastOut(_Out):
    forecast: ForecastOut
    claim_path: str
    report_kind: ReportKind
    adjustment: Adjustment
    geography: str
    measure: str
    forecast_author: str | None
    verifier_version: str
    document_version_id: int


class BankComparisonOut(_Out):
    adjustment: Adjustment
    comparison: ForecastComparisonOut


class BankForecastsOut(_Out):
    notice: str = NOTICE
    banks: list[BankRefOut]
    forecasts: list[BankForecastOut]
    comparison: list[BankComparisonOut]
    excluded: list[BankExclusionOut]


class BankHistoryOut(_Out):
    adjustment: Adjustment
    history: ForecastHistoryOut


class BankRevisionsOut(_Out):
    histories: list[BankHistoryOut]
    excluded: list[BankExclusionOut]


class BankConsensusViewOut(_Out):
    consensus: BankConsensusOut
    divergence: list[DivergenceOut]


class BankStanceOut(_Out):
    text: str
    claim_status: Literal["clean", "warning", "failed"]
    label: Literal["AI interpretation"] = "AI interpretation"


class BankCardOut(_Out):
    key: str
    name: str
    state: State
    # The report series behind a series-level state (e.g. "Weekly Note" when only that series is missing), so a card
    # never says "nothing received" beside a report it did receive. None when the state applies to the whole bank.
    worst_series: str | None
    report_name: str | None
    published_on: str | None
    stance: BankStanceOut | None


class BankSummaryOut(_Out):
    notice: str = NOTICE
    cards: list[BankCardOut]


class SeriesStatusOut(_Out):
    series_key: str
    series_name: str
    state: State
    newest_published_on: str | None
    ingested_at: str | None  # Pacific/Auckland
    analysed_at: str | None
    last_checked_at: str | None


class BankStatusOut(_Out):
    key: str
    name: str
    state: State
    series: list[SeriesStatusOut]


class BankFreshnessOut(_Out):
    banks: list[BankStatusOut]
    exit_code: int
