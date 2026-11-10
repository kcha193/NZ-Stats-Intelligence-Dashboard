"""Phase 4AE: the five banks stay refused everywhere; only descriptive registry fields changed (SYNTHETIC FIXTURE)."""

import pytest

from nzstats.research.registry import ContentPolicy, ReviewStatus, load_registry

from .bank_support import BANK_KEYS


@pytest.fixture(scope="module")
def registry():
    return load_registry()


@pytest.mark.parametrize("key", BANK_KEYS)
def test_every_bank_is_refused_everywhere(registry, key):
    inst = registry[key]
    assert not inst.automated_access_allowed
    assert not inst.manual_import_allowed
    assert not inst.source_permitted
    assert inst.llm_refusal(hosted=True) is not None
    assert inst.llm_refusal(hosted=False) is not None
    assert inst.display_level().value == "none"
    assert inst.private_display_level().value == "none"
    assert inst.content_policy is not ContentPolicy.FULL_TEXT
    assert inst.review_status is ReviewStatus.NEEDS_REVIEW


def test_bnz_and_kiwibank_landing_urls_are_owner_supplied_and_unprobed(registry):
    bnz, kiwi = registry["bnz"], registry["kiwibank"]
    assert bnz.allowed_hosts == ("www.bnz.co.nz",)
    assert bnz.landing_urls == ("https://www.bnz.co.nz/institutional-banking/research/publications",)
    assert kiwi.landing_urls == ("https://www.kiwibank.co.nz/business-banking/thrive-hq/kiwi-economics/",)
    for inst in (bnz, kiwi):
        assert inst.landing_evidence == "none"
        assert inst.content_policy is ContentPolicy.NONE
        assert inst.review_status is ReviewStatus.NEEDS_REVIEW
        assert "not probed" in inst.access_notes.lower()


def test_cadence(registry):
    assert registry["anz"].expected_publication_days == 100
    assert registry["asb"].expected_publication_days == 10
    assert registry["westpac"].expected_publication_days == 10
