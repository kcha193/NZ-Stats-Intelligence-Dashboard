"""The bank forecast view (Phase 4AE): read-only, per request, over drafts the existing gate lets through.

It adds no permission of its own. `drafts.draft_summaries` decides which summaries may be shown (loopback-only
callers, current held document, reviewed route, no instruction-like section, and so on), and a bank has to pass all of
it: a source that is not permitted, or whose content policy is not `full_text`, yields nothing here.

From each admitted draft the view keeps only claims that are the institution's own forecast, carry a number, and
passed every automated check with no warning (the draft's claim status is `clean`). Everything else is listed by
fixed code, never by text. Reference institutions (central bank, government) are returned separately as markers for
charts; they are never bank contributors. Nothing is written and no provider or network client is used.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from nzstats.research.api_models import EvidenceOut, ForecastOut, InstitutionOut
from nzstats.research.bank_forecast import (
    NormalizedForecast,
    adjustment_conflicts,
    canonical_label,
    derive_adjustment,
    derive_geography,
)
from nzstats.research.banks import ADAPTERS, BankAdapter, report_kind_of
from nzstats.research.contract import ForecastClaim, IssuerRole
from nzstats.research.drafts import DraftAllowlist, DraftSummary, draft_summaries
from nzstats.research.registry import Institution
from nzstats.research.verify import resolve_verifier

ExclusionCode = Literal[
    "claim_failed_checks", "claim_has_warning", "third_party_issuer", "no_value"
]
_MARKER_KINDS = ("central_bank", "government")


@dataclass(frozen=True)
class ExcludedClaim:
    institution_key: str
    summary_id: int
    claim_path: str
    code: ExclusionCode
    # The forecast a failed or warned claim stated, so analytics can tell that a bank's newer figure is unusable and
    # must not be replaced by its older one. None for claims that are not the bank's own numeric view of a measure.
    normalized: NormalizedForecast | None = None


@dataclass(frozen=True)
class BankView:
    forecasts: list[NormalizedForecast]
    excluded: list[ExcludedClaim]
    markers: list[NormalizedForecast]
    banks: list[Institution]


def _forecast_out(d: DraftSummary, claim: ForecastClaim, label: str) -> ForecastOut:
    row = d.row
    return ForecastOut(
        summary_id=d.id,
        institution=InstitutionOut(
            key=d.institution.key, name=d.institution.name, kind=d.institution.kind
        ),
        document_title=row["title"],
        published_on=row["published_on"],
        indicator=claim.indicator.value,
        indicator_label=label,
        horizon=claim.horizon,
        value=claim.value,
        unit=claim.unit,
        direction=claim.direction.value,
        scenario=claim.scenario,
        qualification=claim.qualification,
        evidence=[
            EvidenceOut(section_ordinal=e.section_ordinal, page=e.page, quote=e.quote)
            for e in claim.evidence
        ],
    )


def _normalized(
    d: DraftSummary, claim: ForecastClaim, path: str, adapters: Mapping[str, BankAdapter]
) -> NormalizedForecast:
    row = d.row
    quotes = " ".join(e.quote for e in claim.evidence)
    adjustment = derive_adjustment(claim.indicator_label, quotes)
    # The wrapped forecast carries the label without its adjustment wording, so the same measure has the same identity
    # whether the bank states the adjustment in the label or the evidence; `measure` keeps the label as stated.
    forecast = _forecast_out(d, claim, canonical_label(claim.indicator_label, adjustment))
    return NormalizedForecast(
        forecast=forecast,
        institution_key=d.institution.key,
        document_version_id=int(row["version_id"]),
        claim_path=path,
        report_kind=report_kind_of(d.institution.key, row["canonical_url"], row["title"], adapters),
        forecast_author=claim.issuer,
        geography=derive_geography(
            forecast.indicator, claim.indicator_label, claim.horizon, claim.unit
        ),
        measure=claim.indicator_label,
        adjustment=adjustment,
        adjustment_conflict=adjustment_conflicts(claim.indicator_label, quotes),
        verifier_version=resolve_verifier(row["verifier_version"]),
        raw_value=claim.value,
    )


def bank_view(
    conn: sqlite3.Connection,
    registry: Mapping[str, Institution],
    allowlist: DraftAllowlist,
    adapters: Mapping[str, BankAdapter] = ADAPTERS,
    *,
    drafts: list[DraftSummary] | None = None,
) -> BankView:
    """`drafts` lets a caller that already ran the gate (the API builds cards from the same list) reuse its result."""
    forecasts: list[NormalizedForecast] = []
    markers: list[NormalizedForecast] = []
    excluded: list[ExcludedClaim] = []
    for d in drafts if drafts is not None else draft_summaries(conn, registry, allowlist):
        kind = d.institution.kind
        if kind != "bank" and kind not in _MARKER_KINDS:
            continue
        status = {c.path: c.status for c in d.claims}
        target = forecasts if kind == "bank" else markers
        for i, claim in enumerate(d.summary.forecasts):
            path = f"forecasts[{i}]"
            code: ExclusionCode | None = None
            if claim.issuer_role is IssuerRole.THIRD_PARTY:
                code = "third_party_issuer"
            elif claim.value is None:
                code = "no_value"
            elif status.get(path) == "failed":
                code = "claim_failed_checks"
            elif status.get(path) != "clean":
                code = "claim_has_warning"
            if code is None:
                target.append(_normalized(d, claim, path, adapters))
            elif kind == "bank":
                own = (
                    _normalized(d, claim, path, adapters)
                    if code in ("claim_failed_checks", "claim_has_warning")
                    else None
                )
                excluded.append(ExcludedClaim(d.institution.key, d.id, path, code, own))
    banks = sorted((i for i in registry.values() if i.kind == "bank"), key=lambda i: i.key)
    return BankView(forecasts, excluded, markers, banks)
