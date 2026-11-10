"""Response models for the internal bank-intelligence routes (Phase 4AE). An allowlist, like `api_models`.

These are served only on the loopback draft router (`bank_api`). No raw model output, reviewer, note, error text or
document text beyond the evidence quotes the draft page already shows has a field here.
"""

from __future__ import annotations

from typing import Literal

from nzstats.research.api_models import ConsensusGroupOut, ContributorOut, _Out
from nzstats.research.bank_forecast import Adjustment

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
    adjustment: Adjustment
    horizon_label: str
    unit_label: str
    spread: float  # maximum minus minimum
    median: float
    banks: list[DivergenceBankOut]
