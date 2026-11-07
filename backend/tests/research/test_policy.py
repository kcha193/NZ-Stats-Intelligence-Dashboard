"""Phase 4W: the operator-run inference policy, its file, its source checks and its audit. Offline; SYNTHETIC FIXTURE data.

Nothing here contacts a provider. A policy file is a set of limits the code enforces; it is never evidence that rights or
account controls are genuine, so every check below reads the registry, the stored document or an append-only record.
"""

import json
import sqlite3
from dataclasses import replace
from datetime import timedelta

import pytest

from nzstats.research import policy as pol
from nzstats.research import summary_store as ss
from nzstats.research.registry import ContentPolicy, LlmProcessing, ManualImport

from .llm_support import NOW
from .policy_support import policy_dict, registry, world, write_policy
from .test_pilot_treasury_v3 import spend


def codes(assessment):
    return {c.code for c in assessment.checks if not c.ok}


def load(tmp_path, body=None, **kw):
    conn, reg, data, version = world(tmp_path, **kw)
    path = write_policy(data, body)
    policy, sha = pol.load_policy(path, data)
    return conn, reg, data, version, policy, sha


# --- the file and its identity -------------------------------------------------------------------------------------
def test_a_valid_policy_loads_with_a_stable_hash_independent_of_layout(tmp_path):
    conn, reg, data, version, policy, sha = load(tmp_path)
    assert len(sha) == 64 and pol.scope_name(sha) == f"policy-{sha[:16]}"
    again = write_policy(
        data, json.dumps(policy_dict(), indent=4, sort_keys=True), name="again.json"
    )
    assert pol.load_policy(again, data)[1] == sha


@pytest.mark.parametrize(
    "change",
    [
        {"policy_id": "other"},
        {"per_call_usd": 0.4},
        {"max_calls": 3},
        {"expires_at": (NOW + timedelta(days=5)).isoformat()},
        {"issued_by": "Someone Else"},
    ],
)
def test_any_change_to_a_policy_changes_its_identity(tmp_path, change):
    _, _, data, _, _, sha = load(tmp_path)
    path = write_policy(data, policy_dict(**change), name="changed.json")
    assert pol.load_policy(path, data)[1] != sha


@pytest.mark.parametrize(
    "change",
    [
        {"institution": "rbnz"},  # RBNZ is outside the initial policy
        {"series": "Budget"},
        {"document_scope": "series"},
        {"per_call_usd": 0.51},
        {"per_call_usd": 0},
        {"aggregate_usd": 2.01},
        {"aggregate_usd": 0.1},  # below one call
        {"max_calls": 5},
        {"max_calls": 0},
        {"expires_at": (NOW + timedelta(days=40)).isoformat()},  # a window over 30 days
        {"not_before": (NOW + timedelta(days=40)).isoformat()},
        {"not_before": "2026-10-26T00:00:00"},  # no timezone
        {"prompt_version": "outlook-v5"},
        {"verifier_version": "verify-4"},
        {"unknown_field": 1},
        {"route": {**policy_dict()["route"], "model": "openai/gpt-5.6-sol"}},
        {"route": {**policy_dict()["route"], "zdr": False}},
        {"route": {**policy_dict()["route"], "data_collection": "allow"}},
        {"route": {**policy_dict()["route"], "allow_fallbacks": True}},
        {"route": {**policy_dict()["route"], "reasoning_effort": "high"}},
        {"route": {**policy_dict()["route"], "max_output_tokens": 13000}},
    ],
)
def test_a_policy_outside_the_code_ceilings_is_invalid(tmp_path, change):
    conn, reg, data, version = world(tmp_path)
    path = write_policy(data, policy_dict(**change))
    with pytest.raises(pol.PolicyRefused) as info:
        pol.load_policy(path, data)
    assert info.value.code == "policy_invalid"


def test_the_ceilings_are_code_constants_a_file_can_only_tighten():
    assert (pol.POLICY_MAX_CALLS, pol.POLICY_MAX_PER_CALL_USD) == (4, 0.5)
    assert (pol.POLICY_MAX_AGGREGATE_USD, pol.POLICY_MAX_DAYS) == (2.0, 30)
    assert pol.POLICY_MAX_CALLS == ss.LIFETIME_ATTEMPTS - ss.LEGACY_LIFETIME_ATTEMPTS


def test_pins_that_do_not_match_the_code_are_refused_and_name_which(tmp_path):
    for field, code in (
        ("prompt_sha256", "prompt_pin_mismatch"),
        ("verifier_sha256", "verifier_pin_mismatch"),
    ):
        conn, reg, data, version = world(tmp_path / field)
        path = write_policy(data, policy_dict(**{field: "0" * 64}))
        with pytest.raises(pol.PolicyRefused) as info:
            pol.load_policy(path, data)
        assert info.value.code == code


def test_the_file_must_be_a_private_regular_file_inside_the_data_directory(tmp_path):
    conn, reg, data, version = world(tmp_path)
    outside = write_policy(tmp_path / "elsewhere", policy_dict())
    cases = {
        "policy_file_outside_data": outside,
        "policy_file_not_private": write_policy(data, policy_dict(), name="open.json", mode=0o644),
        "policy_file_missing": data / "nope.json",
        "policy_file_unreadable": write_policy(data, "not json", name="junk.json"),
    }
    link = data / "link.json"
    link.symlink_to(write_policy(data, policy_dict(), name="real.json"))
    cases["policy_file_symlink"] = link
    for code, path in cases.items():
        with pytest.raises(pol.PolicyRefused) as info:
            pol.load_policy(path, data)
        assert info.value.code == code, code


def test_the_validity_window_is_checked_at_call_time(tmp_path):
    conn, reg, data, version, policy, sha = load(tmp_path)
    assert pol.window_check(policy, NOW).ok
    assert pol.window_check(policy, NOW - timedelta(days=2)).code == "policy_not_yet_valid"
    assert pol.window_check(policy, NOW + timedelta(days=30)).code == "policy_expired"


# --- the source: every check reads the registry or the store, never the file -----------------------------------------
def test_a_permitted_current_manually_imported_version_is_eligible_with_all_sections(tmp_path):
    conn, reg, data, version, policy, sha = load(tmp_path)
    a = pol.assess_source(conn, reg, policy, sha, version, data)
    assert codes(a) == set() and a.ordinals == (0, 1, 2) and a.page_range == (1, 3)
    assert a.title.startswith("Fortnightly Economic Update") and a.published_on == "2026-10-29"
    assert len(a.content_sha256) == 64 and len(a.sections_sha256) == 64


def test_an_explicit_section_scope_is_honoured_and_a_missing_ordinal_refused(tmp_path):
    conn, reg, data, version, policy, sha = load(tmp_path)
    a = pol.assess_source(conn, reg, policy, sha, version, data, ordinals=(1, 2))
    assert a.ordinals == (1, 2) and a.page_range == (2, 3) and codes(a) == set()
    assert "section_scope_invalid" in codes(
        pol.assess_source(conn, reg, policy, sha, version, data, ordinals=(1, 9))
    )


@pytest.mark.parametrize(
    "kwargs,code",
    [
        ({"series": "Budget"}, "series_mismatch"),
        (
            {"acquisition": "crawler"},
            "source_permission_refused",
        ),  # only manual import is approved here
        ({"import_record": False}, "acquisition_provenance_missing"),
        ({"raw_ok": False}, "source_text_unavailable"),
        ({"sections": ()}, "source_text_unavailable"),
    ],
)
def test_source_and_provenance_failures_have_stable_codes(tmp_path, kwargs, code):
    conn, reg, data, version, policy, sha = load(tmp_path, **kwargs)
    assert code in codes(pol.assess_source(conn, reg, policy, sha, version, data))


@pytest.mark.parametrize(
    "change,code",
    [
        ({"llm_processing": LlmProcessing.DENIED}, "llm_processing_denied"),
        ({"llm_processing": LlmProcessing.LOCAL_ONLY}, "llm_processing_denied"),
        ({"manual_import": ManualImport.DENIED}, "source_permission_refused"),
        ({"content_policy": ContentPolicy.METADATA_ONLY}, "source_permission_refused"),
    ],
)
def test_a_revoked_or_missing_registry_permission_refuses_even_with_a_valid_policy(
    tmp_path, change, code
):
    conn, reg, data, version, policy, sha = load(tmp_path)
    changed = {
        "treasury": replace(reg["treasury"], **change)
    }  # a later registry edit, after the policy was issued
    assert code in codes(pol.assess_source(conn, changed, policy, sha, version, data))


def test_an_unregistered_source_is_refused(tmp_path):
    conn, reg, data, version, policy, sha = load(tmp_path)
    assert "source_permission_refused" in codes(
        pol.assess_source(conn, {}, policy, sha, version, data)
    )


def test_a_tampered_raw_file_or_symlink_is_unavailable_source_text(tmp_path):
    conn, reg, data, version, policy, sha = load(tmp_path)
    raw = next((data / "raw").rglob("*"))
    while raw.is_dir():
        raw = next(raw.iterdir())
    raw.write_bytes(b"changed after import")
    assert "source_text_unavailable" in codes(
        pol.assess_source(conn, reg, policy, sha, version, data)
    )


def test_a_new_version_supersedes_the_old_one_and_a_purged_one_is_refused(tmp_path):
    conn, reg, data, version, policy, sha = load(tmp_path)
    conn.execute(
        "UPDATE research_document_version SET superseded_at=? WHERE id=?",
        (NOW.isoformat(), version),
    )
    assert "version_not_current" in codes(pol.assess_source(conn, reg, policy, sha, version, data))
    assert "version_not_found" in codes(pol.assess_source(conn, reg, policy, sha, 999, data))


def test_the_licence_must_be_the_one_the_policy_pinned_in_the_registry_and_in_the_stored_version(
    tmp_path,
):
    conn, reg, data, version, policy, sha = load(tmp_path)
    reworded = registry(licence="Synthetic licence text B")
    assert "licence_changed" in codes(pol.assess_source(conn, reworded, policy, sha, version, data))
    conn2, reg2, data2, version2, policy2, sha2 = load(
        tmp_path / "b", snapshot_licence="An item-specific licence"
    )
    assert "licence_changed" in codes(
        pol.assess_source(conn2, reg2, policy2, sha2, version2, data2)
    )


def test_a_section_with_a_third_party_notice_is_excluded_not_sent(tmp_path):
    sections = (
        "SYNTHETIC cover.",
        "Copyright held by a non-Crown party. Reproduced with permission.",
        "Activity is expected to grow 2.5% in the year to March 2027.",
    )
    conn, reg, data, version, policy, sha = load(tmp_path, sections=sections)
    a = pol.assess_source(conn, reg, policy, sha, version, data)
    assert codes(a) == set() and a.ordinals == (0, 2) and a.excluded == (1,)
    explicit = pol.assess_source(conn, reg, policy, sha, version, data, ordinals=(1, 2))
    assert "third_party_content" in codes(
        explicit
    )  # an operator cannot name a flagged section into scope


def test_a_document_with_nothing_left_after_exclusions_is_refused(tmp_path):
    sections = ("© Example Ltd. All rights reserved.", "Used with permission of a third party.")
    conn, reg, data, version, policy, sha = load(tmp_path, sections=sections)
    assert "no_eligible_sections" in codes(pol.assess_source(conn, reg, policy, sha, version, data))


# --- one attempt per document version, from two independent records -------------------------------------------------
def test_a_version_with_any_recorded_attempt_is_ineligible_under_any_experiment_tag(tmp_path):
    conn, reg, data, version, policy, sha = load(tmp_path)
    spend(conn, version, None)  # an untagged legacy-style attempt
    assert "version_attempted" in codes(pol.assess_source(conn, reg, policy, sha, version, data))


def test_the_same_content_under_a_new_version_row_is_still_attempted(tmp_path):
    from nzstats.research import store
    from nzstats.store.db import transaction

    conn, reg, data, version, policy, sha = load(tmp_path)
    spend(conn, version, "phase-4s-treasury-v3")
    row = conn.execute(
        "SELECT content_sha256, institution_id FROM research_document_version v JOIN research_publication p"
        " ON p.id = v.publication_id WHERE v.id=?",
        (version,),
    ).fetchone()
    with transaction(
        conn
    ):  # the same bytes arrive again as a different publication and version row
        pub, _ = store.upsert_publication(
            conn, row["institution_id"], doc_key="treasury:research.example.org/renamed", url="https://research.example.org/renamed",
            title="Renamed", series="FEU", categories=[], published_on="2026-11-12", published_at=None,
            precision="day", content_status="extracted", now=NOW,
        )  # fmt: skip
        twin, _ = store.add_version(
            conn, pub, content_sha256=row["content_sha256"], text_sha256="f" * 64, fmt="pdf", fetched_at=NOW,
            extractor_version="pdf-1", raw_artifact_id=None, title="Renamed",
            sections=[store.SectionRow(0, None, "Activity is expected to grow.", 1, 1, 0, 29)], page_count=1,
            licence_snapshot=conn.execute("SELECT licence_snapshot FROM research_document_version WHERE id=?", (version,)).fetchone()[0],
            now=NOW, acquisition="manual",
        )  # fmt: skip
    assert (
        twin != version and pol.version_attempts(conn, twin) == 0
    )  # no attempt on the new row itself
    assert pol.content_attempted(conn, row["content_sha256"], exclude_version=twin)
    assert "content_already_attempted" in codes(
        pol.assess_source(conn, reg, policy, sha, twin, data)
    )
    assert not pol.content_attempted(conn, "0" * 64)


def test_an_audited_execution_blocks_its_content_even_if_the_ledger_were_edited(tmp_path):
    conn, reg, data, version, policy, sha = load(tmp_path)
    a = pol.assess_source(conn, reg, policy, sha, version, data)
    pol.record_event(
        conn, "executed", policy, sha, operator="synthetic", now=NOW, version_id=version,
        content_sha256=a.content_sha256, request_sha256="c" * 64, outcome="failed_verification", cost_usd=0.1,
    )  # fmt: skip
    again = pol.assess_source(conn, reg, policy, sha, version, data)
    assert "content_already_executed" in codes(again)


def test_usage_counts_the_larger_of_the_ledger_and_the_audit_so_retagging_restores_nothing(
    tmp_path,
):
    conn, reg, data, version, policy, sha = load(tmp_path)
    name = pol.scope_name(sha)
    spend(conn, version, name, cost=0.1)
    assert pol.policy_usage(conn, sha) == (1, pytest.approx(0.1))
    try:  # retag the run so the ledger forgets the policy, if the schema even allows it
        conn.execute("UPDATE research_llm_run SET limits='{}'")
    except Exception:
        pass
    pol.record_event(
        conn, "executed", policy, sha, operator="synthetic", now=NOW, version_id=version,
        content_sha256="e" * 64, request_sha256="c" * 64, outcome="provider_error", cost_usd=0.1,
    )  # fmt: skip
    assert pol.policy_usage(conn, sha) == (1, pytest.approx(0.1))


def test_capacity_checks_name_the_exhausted_limit(tmp_path):
    conn, reg, data, version, policy, sha = load(tmp_path)
    assert pol.capacity_checks(conn, policy, sha, 0.4).failures == ()
    assert [c.code for c in pol.capacity_checks(conn, policy, sha, 0.6).failures] == [
        "per_call_cap_exceeded"
    ]
    pol.record_event(
        conn, "executed", policy, sha, operator="s", now=NOW, version_id=version, content_sha256="1" * 64,
        request_sha256="2" * 64, outcome="verified", cost_usd=1.7,
    )  # fmt: skip
    assert [c.code for c in pol.capacity_checks(conn, policy, sha, 0.4).failures] == [
        "policy_budget_exhausted"
    ]
    for i in range(3):  # a fourth call is refused by the call limit whatever it costs
        pol.record_event(
            conn, "executed", policy, sha, operator="s", now=NOW, version_id=version,
            content_sha256=f"{i + 2}" * 64, request_sha256="2" * 64, outcome="provider_error", cost_usd=0.0,
        )  # fmt: skip
    assert "policy_calls_exhausted" in {
        c.code for c in pol.capacity_checks(conn, policy, sha, 0.1).failures
    }


def test_a_revoked_policy_is_refused_and_revocation_is_append_only(tmp_path):
    conn, reg, data, version, policy, sha = load(tmp_path)
    assert not pol.is_revoked(conn, sha)
    pol.record_event(
        conn, "revoked", policy, sha, operator="synthetic", now=NOW, detail="owner withdrew it"
    )
    assert pol.is_revoked(conn, sha)
    assert "policy_revoked" in {
        c.code for c in pol.capacity_checks(conn, policy, sha, 0.1).failures
    }
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM research_policy_event")


def test_refusals_are_logged_without_consuming_anything(tmp_path):
    conn, reg, data, version, policy, sha = load(tmp_path)
    pol.record_event(
        conn, "refused", policy, sha, operator="synthetic", now=NOW, version_id=version,
        refusal_code="llm_processing_denied",
    )  # fmt: skip
    assert pol.policy_usage(conn, sha) == (0, 0.0)
    a = pol.assess_source(conn, reg, policy, sha, version, data)
    assert codes(a) == set()


def test_policy_py_imports_no_provider_and_its_output_cap_matches_the_reviewed_route():
    import ast
    from pathlib import Path

    from nzstats.research import openrouter

    tree = ast.parse(Path(pol.__file__).read_text())
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert not imported & {
        "nzstats.research.openrouter",
        "nzstats.research.providers",
        "nzstats.research.pilot",
        "httpx",
    }
    assert pol.MAX_OUTPUT_TOKENS == openrouter.MAX_OUTPUT_TOKENS
