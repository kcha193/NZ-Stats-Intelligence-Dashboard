import textwrap
from pathlib import Path

import pytest

from nzstats.research.registry import (
    PRIORITY,
    ContentPolicy,
    Mechanism,
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
    assert r["rbnz"].review_status is ReviewStatus.RESTRICTED
    assert r["rbnz"].content_policy is ContentPolicy.NONE
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
