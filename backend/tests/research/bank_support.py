"""Shared helpers for the Phase 4AE bank tests. Everything here is SYNTHETIC: no real report text or values."""

from collections.abc import Mapping

from nzstats.research.banks import BankAdapter, Series
from nzstats.research.registry import Institution

from .support import institution

BANK_KEYS = ("anz", "asb", "bnz", "westpac", "kiwibank")
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
