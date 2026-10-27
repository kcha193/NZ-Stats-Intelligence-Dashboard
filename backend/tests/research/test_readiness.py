"""Phase 3D-A: the four pilot permissions are evaluated separately, from the registry and environment only."""

from __future__ import annotations

from nzstats.research.providers import LlmSettings
from nzstats.research.readiness import assess, pipeline_state

from .llm_support import seed_version
from .public_support import displayable, registry, store_summary
from .support import institution

UNREVIEWED = {"review_status": "needs_review", "terms_evidence": "search", "approved_by": None,
              "approved_on": None, "approval_note": None}  # fmt: skip
LOCAL = LlmSettings(
    provider="openai_compatible", model="local-1", base_url="http://127.0.0.1:8080/v1"
)
HOSTED = LlmSettings(provider="anthropic", model="claude-haiku-5-5", api_key="secret-key-value")


def gates(report):
    return {g.name: g for g in report.gates}


def test_an_unreviewed_source_grants_nothing_and_names_the_terms_as_the_first_blocker():
    report = assess(institution("treasury", **UNREVIEWED), LlmSettings(), env={})
    g = gates(report)
    assert [x.granted for x in report.gates] == [False, False, False, False]
    assert "terms" in g["fetch"].blocker and "direct" in g["fetch"].blocker
    assert report.first_blocker == g["fetch"].blocker
    # Later gates say they wait on the earlier one rather than repeating its reason.
    assert "decision 1" in g["store"].blocker
    assert any("terms_evidence: search" in e for e in g["fetch"].evidence)


def test_a_restricted_source_stays_restricted():
    report = assess(
        institution("rbnz", review_status="restricted", content_policy="none"),
        LlmSettings(),
        env={},
    )
    assert not gates(report)["fetch"].granted
    assert "restricted" in gates(report)["fetch"].blocker


def test_storage_needs_full_text_not_metadata_only():
    report = assess(institution(content_policy="metadata_only"), LlmSettings(), env={})
    g = gates(report)
    assert g["fetch"].granted and not g["store"].granted
    assert "metadata_only" in g["store"].blocker


def test_llm_is_refused_while_the_source_denies_it_even_with_a_provider():
    g = gates(assess(institution(), LOCAL, env={}))
    assert g["store"].granted and not g["llm"].granted
    assert "llm_processing" in g["llm"].blocker


def test_a_local_only_source_refuses_a_hosted_provider_and_accepts_a_local_one():
    inst = institution(llm_processing="local_only", llm_processing_note="synthetic")
    hosted = gates(assess(inst, HOSTED, env={}))["llm"]
    assert not hosted.granted and "local models only" in hosted.blocker
    local = gates(assess(inst, LOCAL, env={}))["llm"]
    assert local.granted and local.blocker is None


def test_llm_permission_without_a_configured_provider_is_not_ready():
    inst = institution(llm_processing="hosted", llm_processing_note="synthetic")
    g = gates(assess(inst, LlmSettings(), env={}))["llm"]
    assert not g.granted and "no LLM provider" in g.blocker


def test_the_api_key_never_appears_in_the_report():
    inst = institution(llm_processing="hosted", llm_processing_note="synthetic")
    text = repr(assess(inst, HOSTED, env={}))
    assert "secret-key-value" not in text


def test_publication_reports_the_level_and_whether_the_api_switch_is_on():
    inst = displayable(level="link_only")
    off = gates(assess(inst, LOCAL, env={}))["publish"]
    assert off.granted and "link_only" in off.detail and "off" in off.detail
    on = gates(assess(inst, LOCAL, env={"NZSTATS_PUBLIC_RESEARCH": "1"}))["publish"]
    assert "on" in on.detail
    assert not gates(assess(institution(), LOCAL, env={}))["publish"].granted


def test_pipeline_state_counts_versions_summaries_and_public_items(conn):
    reg = registry()
    version = seed_version(conn)
    store_summary(conn, version)
    store_summary(conn, seed_version(conn, doc="b"), review=None, publish=False)
    state = pipeline_state(conn, reg["example"], reg)
    assert state.publications == 2 and state.current_versions == 2
    assert state.summaries == {"verified": 2}
    assert state.approved == 1 and state.public == 1
