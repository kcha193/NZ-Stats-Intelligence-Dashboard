"""Phase 4AE: bank series adapters identify a report series, its kind and cadence; they hold no permissions
(SYNTHETIC FIXTURE)."""

import dataclasses

from nzstats.research.banks import ADAPTERS, BankAdapter, Series, adapter_for, report_kind_of

from .bank_support import SYNTH_ADAPTERS, synthetic_registry

ANZ_QEO = (
    "https://www.anz.co.nz/content/dam/anzconz/documents/economics-and-market-research/2026/"
    "ANZ-QEO-20260813.pdf"
)
WESTPAC_WEEKLY = (
    "https://assets.dam.westpac.co.nz/is/content/wnzl/dist/all-of-bank/economic-reports/"
    "weekly-commentary/Weekly-Commentary_191026_report_19Oct26.pdf"
)
ASB_WEEKLY = (
    "https://www.asb.co.nz/documents/economic-research/economic-weekly/some-weekly-note.html"
)
ASB_QEF = (
    "https://www.asb.co.nz/documents/economic-research/quarterly-economic-forecasts/some-round.html"
)


def test_adapter_for_known_and_unknown():
    assert adapter_for("anz") is not None
    assert adapter_for("bnz") is None
    assert adapter_for("kiwibank") is None
    injected = {"bank_a": BankAdapter(key="bank_a", series=())}
    assert adapter_for("bank_a", injected) is injected["bank_a"]
    assert adapter_for("anz", injected) is None


def test_series_of_matches_registry_url_shapes():
    assert (
        ADAPTERS["anz"].series_of(ANZ_QEO, "Quarterly Economic Outlook").key == "economic_outlook"
    )
    assert (
        ADAPTERS["westpac"].series_of(WESTPAC_WEEKLY, "Weekly Commentary").key
        == "weekly_commentary"
    )
    assert ADAPTERS["asb"].series_of(ASB_WEEKLY, "Economic Weekly").key == "economic_weekly"
    assert ADAPTERS["asb"].series_of(ASB_QEF, "Quarterly Economic Forecasts").key == (
        "quarterly_economic_forecasts"
    )


def test_report_kind_by_series_and_default_other():
    assert report_kind_of("anz", ANZ_QEO, "x") == "outlook"
    assert report_kind_of("asb", ASB_WEEKLY, "x") == "weekly"
    assert report_kind_of("westpac", WESTPAC_WEEKLY, "x") == "weekly"
    assert report_kind_of("anz", "https://www.anz.co.nz/other.pdf", "x") == "other"
    assert report_kind_of("bnz", "https://www.bnz.co.nz/x", "x") == "other"


def test_cadence_days():
    assert ADAPTERS["anz"].series[0].cadence_days == 100
    assert {s.key: s.cadence_days for s in ADAPTERS["asb"].series} == {
        "quarterly_economic_forecasts": 100,
        "economic_weekly": 10,
    }
    assert ADAPTERS["westpac"].series[0].cadence_days == 10


def test_canonical_url_strips_fragment_query_and_trailing_slash():
    adapter = ADAPTERS["asb"]
    assert adapter.canonical_url("HTTPS://WWW.ASB.CO.NZ/documents/a/b/?utm=1#top") == (
        "https://www.asb.co.nz/documents/a/b"
    )
    assert adapter.canonical_url("https://www.asb.co.nz/documents/a.pdf") == (
        "https://www.asb.co.nz/documents/a.pdf"
    )


def test_adapters_hold_no_permission_fields():
    names = {f.name for cls in (Series, BankAdapter) for f in dataclasses.fields(cls)}
    for word in ("approved", "permission", "llm", "display", "review", "content_policy"):
        assert not any(word in n for n in names), word


def test_synthetic_registry_and_adapters_for_happy_path_tests():
    registry = synthetic_registry()
    assert {"bank_a", "bank_b", "bank_c", "ref_central", "ref_gov"} <= set(registry)
    assert registry["bank_a"].kind == "bank" and registry["ref_central"].kind == "central_bank"
    assert registry["ref_gov"].kind == "government"
    for key in ("bank_a", "bank_b", "bank_c"):
        assert registry[key].manual_import_allowed
        assert registry[key].llm_refusal(hosted=False) is None
        assert registry[key].llm_refusal(hosted=True) is not None  # local models only
        assert adapter_for(key, SYNTH_ADAPTERS) is not None
