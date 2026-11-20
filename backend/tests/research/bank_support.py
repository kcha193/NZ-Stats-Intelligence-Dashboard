"""Shared helpers for the Phase 4AE bank tests. Everything here is SYNTHETIC: no real report text or values."""

from collections.abc import Mapping

from nzstats.research.banks import BankAdapter, Series
from nzstats.research.registry import Institution

from .support import institution

BANK_KEYS = ("anz", "asb", "bnz", "westpac", "kiwibank")
# Phase 4AI: the owner's recorded personal-research scope opens ANZ's manual import only. Every other bank stays refused.
PERSONAL_SCOPE_BANK = "anz"
DENIED_BANK_KEYS = tuple(k for k in BANK_KEYS if k != PERSONAL_SCOPE_BANK)


def assert_anz_holds_only_the_personal_scope(inst: Institution) -> None:
    """ANZ may be imported by hand and read locally, and nothing else: no crawler, no model, no public or private display."""
    from datetime import date

    from nzstats.research.registry import (
        ContentPolicy,
        LlmProcessing,
        ManualImport,
        PrivateDisplay,
        PublicDisplay,
        ReviewStatus,
    )

    assert inst.key == PERSONAL_SCOPE_BANK
    assert inst.manual_import is ManualImport.APPROVED and inst.manual_import_allowed
    assert inst.manual_import_approved_by == "Kevin Chang"
    assert inst.manual_import_approved_on == date(2026, 11, 15)
    note = inst.manual_import_note
    assert "docs/phase-4ai-authorization-assessment.md" in note and "not a licence from ANZ" in note
    assert "one browser-saved Economic Outlook PDF" in note and "loopback dashboard only" in note
    # Phase 4AO: C2W met, so the Phase 4AN workbook route is covered. Everything automated or shared stays excluded.
    assert "one browser-saved forecasts workbook (XLSX)" in note
    assert "docs/phase-4an-anz-workbook.md" in note and "conditions C2W met on 2026-11-21" in note
    assert "the forecasts workbook" not in note.split("Not covered:", 1)[1]
    for excluded in ("automated fetching", "any model", "public or shared display", "snapshots", "scheduling"):
        assert excluded in note.split("Not covered:", 1)[1], excluded
    assert inst.content_policy is ContentPolicy.FULL_TEXT
    # The crawler needs review_status approved, which this scope never gives.
    assert inst.review_status is ReviewStatus.NEEDS_REVIEW and not inst.automated_access_allowed
    assert (inst.approved_by, inst.approved_on, inst.approval_note) == (None, None, None)
    assert inst.llm_processing is LlmProcessing.DENIED
    assert inst.llm_refusal(hosted=True) is not None and inst.llm_refusal(hosted=False) is not None
    assert inst.public_display is PublicDisplay.NONE and inst.public_display_approved_by is None
    assert inst.private_display is PrivateDisplay.NONE and inst.private_display_approved_by is None
    assert inst.display_level().value == "none" and inst.private_display_level().value == "none"
    assert inst.holds("manual") and not inst.holds("crawler")


def nf(
    institution: str = "bank_a",
    *,
    report_kind: str = "outlook",
    adjustment: str = "not_stated",
    adjustment_conflict: bool = False,
    claim_path: str = "forecasts[0]",
    **kw,
):
    """A NormalizedForecast of a CPI forecast built without a database (SYNTHETIC). Overrides go to ForecastOut."""
    from nzstats.research.api_models import ForecastOut, InstitutionOut
    from nzstats.research.bank_forecast import NormalizedForecast

    data = {
        "summary_id": 1,
        "institution": InstitutionOut(
            key=institution, name=f"Example {institution}", kind=kw.pop("kind", "bank")
        ),
        "document_title": "SYNTHETIC outlook",
        "published_on": "2026-08-13",
        "indicator": "cpi_inflation",
        "indicator_label": "Annual CPI inflation",
        "horizon": "year to June 2027",
        "value": 2.1,
        "unit": "percent",
        "direction": "down",
        "scenario": None,
        "qualification": None,
        "evidence": [],
    }
    data.update(kw)
    f = ForecastOut(**data)
    return NormalizedForecast(
        forecast=f,
        institution_key=institution,
        document_version_id=f.summary_id,
        claim_path=claim_path,
        report_kind=report_kind,
        forecast_author=f.institution.name,
        geography="New Zealand",
        measure=f.indicator_label,
        adjustment=adjustment,
        adjustment_conflict=adjustment_conflict,
        verifier_version="verify-5",
        raw_value=f.value,
    )


def view_of(*forecasts, markers=(), excluded=()):
    from nzstats.research.bank_view import BankView

    return BankView(list(forecasts), list(excluded), list(markers), [])


def unusable(institution: str = "bank_a", code: str = "claim_failed_checks", **kw):
    """A claim the view left out (failed or warned), with the forecast it stated, as `bank_view` records it."""
    from nzstats.research.bank_view import ExcludedClaim

    n = nf(institution, **kw)
    return ExcludedClaim(institution, n.forecast.summary_id, n.claim_path, code, n)


SYNTH_BANKS = ("bank_a", "bank_b", "bank_c")
_MANUAL = {
    "manual_import": "approved",
    "manual_import_approved_by": "Test Reviewer",
    "manual_import_approved_on": "2026-11-10",
    "manual_import_note": "synthetic test source: manual import permitted",
}
_LOCAL = {"llm_processing": "local_only", "llm_processing_note": "synthetic test source"}


def synthetic_registry() -> dict[str, Institution]:
    """Three fake banks (manual import and local models permitted) and two reference institutions. No real names."""
    banks = [
        institution(key, name=f"Example Bank {key[-1].upper()}", **_MANUAL, **_LOCAL)
        for key in SYNTH_BANKS
    ]
    refs = [
        institution(
            "ref_central", name="Example Central Bank", kind="central_bank", **_MANUAL, **_LOCAL
        ),
        institution("ref_gov", name="Example Treasury", kind="government", **_MANUAL, **_LOCAL),
    ]
    return {i.key: i for i in (*banks, *refs)}


SYNTH_ADAPTERS: Mapping[str, BankAdapter] = {
    key: BankAdapter(key, (
        Series("outlook", "Quarterly Outlook", "outlook", 100, url_pattern=r"/research/outlook/"),
        Series("weekly", "Weekly Note", "weekly", 10, url_pattern=r"/research/weekly/"),
    ))
    for key in SYNTH_BANKS
}  # fmt: skip
