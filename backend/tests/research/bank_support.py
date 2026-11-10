"""Shared helpers for the Phase 4AE bank tests. Everything here is SYNTHETIC: no real report text or values."""

from collections.abc import Mapping

from nzstats.research.banks import BankAdapter, Series
from nzstats.research.registry import Institution

from .support import institution

BANK_KEYS = ("anz", "asb", "bnz", "westpac", "kiwibank")


def nf(
    institution: str = "bank_a",
    *,
    report_kind: str = "outlook",
    adjustment: str = "not_stated",
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
        verifier_version="verify-5",
        raw_value=f.value,
    )


def view_of(*forecasts, markers=()):
    from nzstats.research.bank_view import BankView

    return BankView(list(forecasts), [], list(markers), [])


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
