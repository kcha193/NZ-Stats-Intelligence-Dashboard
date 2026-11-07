import textwrap
from pathlib import Path

import pytest

from nzstats.research.registry import (
    PRIORITY,
    ContentPolicy,
    LlmProcessing,
    ManualImport,
    Mechanism,
    PrivateDisplay,
    PublicDisplay,
    RegistryError,
    ReviewStatus,
    load_registry,
)

ALL_KEYS = {
    "rbnz", "treasury", "anz", "asb", "bnz", "westpac", "kiwibank", "nzier", "infometrics",
    "deloitte",
}  # fmt: skip


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "research.toml"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


BASE = """
    [institutions.ex]
    name = "Example"
    kind = "bank"
    allowed_hosts = ["www.example.co.nz"]
    landing_urls = ["https://www.example.co.nz/research"]
    categories = ["economic_outlook"]
    review_status = "needs_review"
    content_policy = "metadata_only"
    licence = "All rights reserved"
    verified_on = "2026-10-25"
    {extra}
"""


@pytest.mark.parametrize("value", ['"yes"', "1", '"approved"'])
def test_invalid_discovery_permission_is_rejected(tmp_path, value):
    with pytest.raises(RegistryError, match="discovery_probe"):
        load_registry(_write(tmp_path, BASE.format(extra=f"discovery_probe = {value}")))


def test_missing_discovery_permission_refuses_probe(tmp_path):
    from nzstats.research.ingest import refusal_for

    inst = load_registry(_write(tmp_path, BASE.format(extra="")))["ex"]
    assert refusal_for(inst, dry_run=True) is not None


def test_shipped_registry_has_all_ten_institutions_priority_first():
    registry = load_registry()
    assert set(registry) == ALL_KEYS
    assert tuple(registry)[:5] == PRIORITY == ("rbnz", "treasury", "anz", "asb", "westpac")


def test_no_shipped_source_is_approved_for_automated_access():
    # Approval is a human decision recorded in the file; none of the 2026-10-25 probes justified one.
    assert [k for k, i in load_registry().items() if i.automated_access_allowed] == []
    assert all(i.review_status is not ReviewStatus.APPROVED for i in load_registry().values())


def test_recorded_findings_from_the_2026_10_25_probes():
    r = load_registry()
    # 2026-10-31: owner read the terms and approved manual import only; automated access still needs written permission
    assert r["rbnz"].review_status is ReviewStatus.NEEDS_REVIEW
    assert r["rbnz"].manual_import is ManualImport.APPROVED
    assert r["rbnz"].content_policy is ContentPolicy.FULL_TEXT
    assert r["anz"].content_policy is ContentPolicy.METADATA_ONLY
    assert "/content/dam/asb/documents/" in r["asb"].blocked_path_prefixes
    assert set(r["westpac"].allowed_hosts) == {"www.westpac.co.nz", "assets.dam.westpac.co.nz"}
    assert r["infometrics"].allowed_hosts == (
        "economics.infometrics.co.nz",
        "www.infometrics.co.nz",
    )
    assert r["deloitte"].allowed_path_prefixes == ("/nz/",)
    assert r["treasury"].content_policy is ContentPolicy.FULL_TEXT  # CC BY 4.0, pending approval
    assert any(d.mechanism is Mechanism.RSS and not d.verified for d in r["rbnz"].discovery)


def test_every_url_is_https_on_an_allowed_host_and_hosts_are_plain_names():
    from urllib.parse import urlsplit

    for key, inst in load_registry().items():
        for host in inst.allowed_hosts:
            assert host == host.lower() and "*" not in host and not host[0].isdigit(), key
        urls = list(inst.landing_urls) + [d.url for d in inst.discovery if d.url]
        for url in urls:
            parts = urlsplit(url)
            assert parts.scheme == "https" and parts.hostname in inst.allowed_hosts, (key, url)
        assert inst.crawl_delay_seconds >= 10.0, key


def test_unprobed_sources_do_not_invent_landing_pages():
    bnz = load_registry()["bnz"]
    assert bnz.allowed_hosts == () and bnz.landing_urls == ()
    assert not bnz.automated_access_allowed


def test_approved_requires_approver_date_and_note(tmp_path):
    body = BASE.format(extra="").replace("needs_review", "approved")
    with pytest.raises(RegistryError, match="approved_by"):
        load_registry(_write(tmp_path, body))
    ok = BASE.format(
        extra='approved_by = "Kevin"\n approved_on = "2026-11-01"\n approval_note = "Read terms."\n'
        ' terms_evidence = "direct"'
    ).replace("needs_review", "approved")
    inst = load_registry(_write(tmp_path, ok))["ex"]
    assert inst.automated_access_allowed


def test_approved_full_text_requires_terms_read_directly(tmp_path):
    body = BASE.format(
        extra='approved_by = "K"\n approved_on = "2026-11-01"\n approval_note = "n"\n'
        ' terms_evidence = "search"'
    ).replace("needs_review", "approved").replace("metadata_only", "full_text")  # fmt: skip
    with pytest.raises(RegistryError, match="terms"):
        load_registry(_write(tmp_path, body))


def test_approved_needs_hosts_and_a_start_url(tmp_path):
    body = BASE.format(
        extra='approved_by = "K"\n approved_on = "2026-11-01"\n approval_note = "n"\n'
        ' terms_evidence = "direct"'
    ).replace("needs_review", "approved").replace(
        'allowed_hosts = ["www.example.co.nz"]', "allowed_hosts = []"
    ).replace('landing_urls = ["https://www.example.co.nz/research"]', "landing_urls = []")  # fmt: skip
    with pytest.raises(RegistryError, match="hosts"):
        load_registry(_write(tmp_path, body))


def test_approved_cannot_have_policy_none_and_restricted_never_allows_access(tmp_path):
    approved = BASE.format(
        extra='approved_by = "K"\n approved_on = "2026-11-01"\n approval_note = "n"\n'
        ' terms_evidence = "direct"'
    ).replace("needs_review", "approved").replace("metadata_only", "none")  # fmt: skip
    with pytest.raises(RegistryError, match="none"):
        load_registry(_write(tmp_path, approved))
    restricted = BASE.format(extra="").replace("needs_review", "restricted")
    assert not load_registry(_write(tmp_path, restricted))["ex"].automated_access_allowed


@pytest.mark.parametrize(
    "old,new,match",
    [
        ('"www.example.co.nz"]\n', '"http://www.example.co.nz"]\n', "host"),
        ('["www.example.co.nz"]', '["*.example.co.nz"]', "host"),
        ('["www.example.co.nz"]', '["127.0.0.1"]', "host"),
        ('["www.example.co.nz"]', '["localhost"]', "host"),
        ('["www.example.co.nz"]', '["WWW.Example.co.nz"]', "host"),
        ("https://www.example.co.nz/research", "http://www.example.co.nz/research", "https"),
        ("https://www.example.co.nz/research", "https://other.example.org/research", "allowed"),
        ('content_policy = "metadata_only"', 'content_policy = "everything"', "content_policy"),
        ('review_status = "needs_review"', 'review_status = "yes"', "review_status"),
    ],
)
def test_invalid_entries_fail_closed(tmp_path, old, new, match):
    body = BASE.format(extra="").replace(old, new)
    with pytest.raises(RegistryError, match=match):
        load_registry(_write(tmp_path, body))


def test_crawl_delay_below_ten_seconds_is_rejected(tmp_path):
    with pytest.raises(RegistryError, match="crawl_delay"):
        load_registry(_write(tmp_path, BASE.format(extra="crawl_delay_seconds = 5")))


def test_discovery_entries_are_validated(tmp_path):
    bad = BASE.format(extra="") + '\n[[institutions.ex.discovery]]\nmechanism = "html_links"\n' \
        'url = "https://www.example.co.nz/research"\n'  # fmt: skip
    with pytest.raises(RegistryError, match="link_pattern"):
        load_registry(_write(tmp_path, bad))
    unknown = BASE.format(extra="") + '\n[[institutions.ex.discovery]]\nmechanism = "scrape_all"\n'
    with pytest.raises(RegistryError, match="mechanism"):
        load_registry(_write(tmp_path, unknown))


def test_url_date_pattern_must_compile_and_have_one_group(tmp_path):
    with pytest.raises(RegistryError, match="url_date_regex"):
        load_registry(
            _write(tmp_path, BASE.format(extra='url_date_regex = "("\n url_date_format = "%Y"'))
        )
    with pytest.raises(RegistryError, match="url_date_regex"):
        load_registry(
            _write(
                tmp_path,
                BASE.format(extra='url_date_regex = "\\\\d+\\\\d+"\n url_date_format = "%Y"'),
            )
        )


def test_missing_file_is_an_error(tmp_path):
    with pytest.raises(RegistryError, match="not found"):
        load_registry(tmp_path / "nope.toml")


@pytest.mark.parametrize("key", ["../evil", "Ex", "ex key", "1ex", ""])
def test_institution_keys_are_plain_identifiers(tmp_path, key):
    # Keys name pacer files and stable document identities, so they must be safe path components.
    body = BASE.format(extra="").replace("[institutions.ex]", f'[institutions."{key}"]')
    with pytest.raises(RegistryError, match="key"):
        load_registry(_write(tmp_path, body))


@pytest.mark.parametrize(
    "extra,match",
    [
        ("crawl_delay_seconds = nan", "crawl_delay"),
        ("crawl_delay_seconds = inf", "crawl_delay"),
        ("max_documents_per_run = 0", "max_documents_per_run"),
        ("max_documents_per_run = -1", "max_documents_per_run"),
        ("min_text_chars = 0", "min_text_chars"),
    ],
)
def test_throttle_and_guard_settings_must_be_finite_and_positive(tmp_path, extra, match):
    with pytest.raises(RegistryError, match=match):
        load_registry(_write(tmp_path, BASE.format(extra=extra)))


def test_an_unparseable_port_is_a_registry_error_not_a_crash(tmp_path):
    body = BASE.format(extra="").replace(
        "https://www.example.co.nz/research", "https://www.example.co.nz:99999/research"
    )
    with pytest.raises(RegistryError, match="allowed host"):
        load_registry(_write(tmp_path, body))


@pytest.mark.parametrize("policy", ["metadata_only", "full_text"])
def test_any_approval_requires_the_terms_to_have_been_read_directly(tmp_path, policy):
    body = BASE.format(
        extra='approved_by = "K"\n approved_on = "2026-11-01"\n approval_note = "n"\n'
        ' terms_evidence = "none"'
    ).replace("needs_review", "approved").replace("metadata_only", policy)  # fmt: skip
    with pytest.raises(RegistryError, match="terms"):
        load_registry(_write(tmp_path, body))


@pytest.mark.parametrize(
    "extra",
    [
        "max_documents_per_run = 2.7",
        "max_documents_per_run = true",
        'max_documents_per_run = "5"',
        "max_documents_per_run = 1000000000",
        "min_text_chars = [1]",
        "min_text_chars = inf",
        "crawl_delay_seconds = 1e400",
        'crawl_delay_seconds = "x"',
    ],
)
def test_malformed_numeric_settings_are_registry_errors_not_raw_exceptions(tmp_path, extra):
    with pytest.raises(RegistryError):
        load_registry(_write(tmp_path, BASE.format(extra=extra)))


# --- Phase 3B: third-party (LLM) processing permission, default denied --------------------------
APPROVED_FULL = (
    'approved_by = "K"\n approved_on = "2026-11-01"\n approval_note = "n"\n terms_evidence = "direct"\n'
    " {llm}"
)


def _approved_full_text(tmp_path: Path, llm: str):
    body = BASE.format(extra=APPROVED_FULL.format(llm=llm)).replace("needs_review", "approved")
    return load_registry(_write(tmp_path, body.replace("metadata_only", "full_text")))["ex"]


def test_only_treasury_has_llm_processing_and_every_other_shipped_source_is_denied():
    """Phase 4X: the owner approved hosted processing for Treasury on 2026-11-08 (`research run-policy` only)."""
    reg = load_registry()
    assert {
        k: i.llm_processing for k, i in reg.items() if i.llm_processing is not LlmProcessing.DENIED
    } == {"treasury": LlmProcessing.HOSTED}
    assert reg["treasury"].llm_refusal(hosted=True, acquisition="manual") is None
    assert "2026-11-08" in reg["treasury"].llm_processing_note
    rbnz = reg["rbnz"]
    assert rbnz.llm_refusal(hosted=False) == "llm processing denied for this source"
    assert rbnz.llm_refusal(hosted=True) == "llm processing denied for this source"


def test_local_only_permits_local_models_but_never_a_hosted_provider(tmp_path):
    inst = _approved_full_text(
        tmp_path,
        'llm_processing = "local_only"\n llm_processing_note = "Terms allow internal use."',
    )
    assert inst.llm_processing is LlmProcessing.LOCAL_ONLY
    assert inst.llm_refusal(hosted=False) is None
    assert inst.llm_refusal(hosted=True) == "source permits local models only"


def test_hosted_permits_both(tmp_path):
    inst = _approved_full_text(
        tmp_path, 'llm_processing = "hosted"\n llm_processing_note = "CC BY 4.0, read directly."'
    )
    assert inst.llm_refusal(hosted=True) is None and inst.llm_refusal(hosted=False) is None


def test_llm_permission_needs_a_note(tmp_path):
    with pytest.raises(RegistryError, match="llm_processing_note"):
        _approved_full_text(tmp_path, 'llm_processing = "hosted"')


@pytest.mark.parametrize(
    ("swap", "match"),
    [
        (("approved", "needs_review"), "approved"),
        (("full_text", "metadata_only"), "full_text"),
    ],
)
def test_llm_permission_needs_an_approved_full_text_source(tmp_path, swap, match):
    body = BASE.format(
        extra=APPROVED_FULL.format(llm='llm_processing = "hosted"\n llm_processing_note = "n"')
    )
    body = body.replace("needs_review", "approved").replace("metadata_only", "full_text")
    body = body.replace(f'"{swap[0]}"', f'"{swap[1]}"')
    with pytest.raises(RegistryError, match=match):
        load_registry(_write(tmp_path, body))


def test_unknown_llm_processing_value_fails_closed(tmp_path):
    with pytest.raises(RegistryError, match="llm_processing"):
        _approved_full_text(tmp_path, 'llm_processing = "yes"\n llm_processing_note = "n"')


# Public display (Phase 3C): a third decision, separate from ingestion and LLM processing.
DISPLAY_APPROVAL = (
    'public_display_approved_by = "K"\n public_display_approved_on = "2026-11-02"\n'
    ' public_display_note = "Terms allow short quotes with attribution."\n'
)
LLM_LOCAL = 'llm_processing = "local_only"\n llm_processing_note = "n"\n'


def test_every_shipped_source_displays_nothing():
    assert {i.public_display for i in load_registry().values()} == {PublicDisplay.NONE}
    assert {i.display_level() for i in load_registry().values()} == {PublicDisplay.NONE}


@pytest.mark.parametrize("level", ["link_only", "summary", "excerpt"])
def test_public_display_needs_its_own_approval_record(tmp_path, level):
    for missing in (
        "public_display_approved_by",
        "public_display_approved_on",
        "public_display_note",
    ):
        approval = "\n".join(
            line for line in DISPLAY_APPROVAL.split("\n") if not line.strip().startswith(missing)
        )
        with pytest.raises(RegistryError, match=missing):
            _approved_full_text(tmp_path, f'{LLM_LOCAL} public_display = "{level}"\n {approval}')


def test_public_display_needs_an_approved_source(tmp_path):
    body = BASE.format(extra=f'public_display = "link_only"\n {DISPLAY_APPROVAL}')
    with pytest.raises(RegistryError, match="approved source"):
        load_registry(_write(tmp_path, body))


@pytest.mark.parametrize("level", ["summary", "excerpt"])
def test_ai_text_display_needs_a_full_text_source(tmp_path, level):
    body = BASE.format(
        extra=APPROVED_FULL.format(llm=f'public_display = "{level}"\n {DISPLAY_APPROVAL}')
    )
    with pytest.raises(RegistryError, match="full_text"):
        load_registry(_write(tmp_path, body.replace("needs_review", "approved")))


def test_link_only_is_allowed_for_a_metadata_only_source(tmp_path):
    body = BASE.format(
        extra=APPROVED_FULL.format(llm=f'public_display = "link_only"\n {DISPLAY_APPROVAL}')
    )
    inst = load_registry(_write(tmp_path, body.replace("needs_review", "approved")))["ex"]
    assert inst.public_display is PublicDisplay.LINK_ONLY
    assert inst.display_level() is PublicDisplay.LINK_ONLY
    assert inst.licence_snapshot()["public_display"] == "link_only"


def test_unknown_public_display_value_fails_closed(tmp_path):
    with pytest.raises(RegistryError, match="public_display"):
        _approved_full_text(tmp_path, f'public_display = "everything"\n {DISPLAY_APPROVAL}')


def test_ai_text_is_withdrawn_when_llm_processing_is_denied(tmp_path):
    # The loader accepts it (permissions can be revoked independently), but nothing the model wrote is shown.
    inst = _approved_full_text(tmp_path, f'public_display = "excerpt"\n {DISPLAY_APPROVAL}')
    assert inst.public_display is PublicDisplay.EXCERPT
    assert inst.display_level() is PublicDisplay.LINK_ONLY
    inst = _approved_full_text(
        tmp_path, f'{LLM_LOCAL} public_display = "excerpt"\n {DISPLAY_APPROVAL}'
    )
    assert inst.display_level() is PublicDisplay.EXCERPT
    assert [d.rank for d in PublicDisplay] == [0, 1, 2, 3]  # each level includes the one before


# Private display (Phase 4I): a fourth decision, separate from public display, for the loopback-only preview.
PRIVATE_APPROVAL = (
    'private_display = "summary"\n private_display_approved_by = "K"\n'
    ' private_display_approved_on = "2026-11-03"\n private_display_note = "Owner preview on this machine only."\n'
)


def test_every_shipped_source_shows_nothing_privately_either():
    assert {i.private_display for i in load_registry().values()} == {PrivateDisplay.NONE}
    assert {i.private_display_level() for i in load_registry().values()} == {PrivateDisplay.NONE}


def test_private_display_needs_its_own_approval_record(tmp_path):
    for missing in (
        "private_display_approved_by",
        "private_display_approved_on",
        "private_display_note",
    ):
        approval = "\n".join(
            line for line in PRIVATE_APPROVAL.split("\n") if not line.strip().startswith(missing)
        )
        with pytest.raises(RegistryError, match=missing):
            _approved_full_text(tmp_path, f"{LLM_LOCAL} {approval}")


def test_private_display_is_independent_of_public_display(tmp_path):
    inst = _approved_full_text(tmp_path, f"{LLM_LOCAL} {PRIVATE_APPROVAL}")
    assert inst.private_display_level() is PrivateDisplay.SUMMARY
    assert inst.public_display is PublicDisplay.NONE and inst.display_level() is PublicDisplay.NONE
    assert inst.licence_snapshot()["private_display"] == "summary"


def test_private_display_needs_a_permitted_full_text_source(tmp_path):
    with pytest.raises(RegistryError, match="approved source"):
        load_registry(_write(tmp_path, BASE.format(extra=PRIVATE_APPROVAL)))
    body = BASE.format(extra=APPROVED_FULL.format(llm=f"{LLM_LOCAL} {PRIVATE_APPROVAL}"))
    with pytest.raises(RegistryError, match="full_text"):
        load_registry(_write(tmp_path, body.replace("needs_review", "approved")))


def test_private_display_shows_nothing_while_llm_processing_is_denied(tmp_path):
    inst = _approved_full_text(tmp_path, PRIVATE_APPROVAL)  # llm_processing left at "denied"
    assert inst.private_display is PrivateDisplay.SUMMARY
    assert inst.private_display_level() is PrivateDisplay.NONE


def test_unknown_private_display_value_fails_closed(tmp_path):
    with pytest.raises(RegistryError, match="private_display"):
        _approved_full_text(tmp_path, PRIVATE_APPROVAL.replace('"summary"', '"excerpt"'))
