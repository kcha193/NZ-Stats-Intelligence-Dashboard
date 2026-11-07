"""SYNTHETIC FIXTURE. Phase 4N regressions; only MockTransport reaches the HTTP boundary.

Envelope shapes mirror the metadata of the two Phase 4M responses. No report text is used.
"""

import json
import logging
from dataclasses import replace
from datetime import timedelta

import httpx
import pytest

from nzstats.research import providers as pv
from nzstats.research import summary_store as ss
from nzstats.research.contract import CONTRACT_VERSION, ProviderError, build_request, parse_draft
from nzstats.research.hosted import HostedConsent
from nzstats.research.openrouter import SECOND_PILOT
from nzstats.research.private import private_summaries, why_not_private
from nzstats.research.prompt import PROMPT_VERSION, input_sha256, render
from nzstats.research.summarise import load_sections, summarise_versions
from nzstats.research.verify import VERIFIER_VERSION

from .llm_support import NOW, draft, draft_json, seed_version
from .public_support import registry as display_registry
from .test_openrouter import ENV, envelope
from .test_private import previewable
from .test_providers import REQUEST
from .test_summarise import registry, rows

EXPERIMENT = "phase-4n-second-pilot"
ENV_4N = {
    **ENV,
    "NZSTATS_LLM_MAX_OUTPUT_TOKENS": "12000",
    "NZSTATS_LLM_TIMEOUT_SECONDS": "300",
    "NZSTATS_LLM_MAX_RUN_USD": "1",
}


def settings(**changes):
    return replace(
        pv.load_llm_settings(ENV_4N),
        openrouter_experiment=EXPERIMENT,
        **changes,
    )


def adapter(handler, **changes):
    return pv.build_provider(
        settings(**changes), client=httpx.Client(transport=httpx.MockTransport(handler))
    )


def billed(*, content, finish="length", native="max_tokens", out=12000, reasoning=None, **usage):
    details = {} if reasoning is None else {"reasoning_tokens": reasoning, "image_tokens": 0}
    return envelope(
        choices=[
            {
                "finish_reason": finish,
                "native_finish_reason": native,
                "message": {"role": "assistant", "content": content, "reasoning": "SYNTHETIC"},
            }
        ],
        usage={
            "prompt_tokens": 100,
            "completion_tokens": out,
            "total_tokens": 100 + out,
            "cost": (100 * 4.4 + out * 22) / 1e6,
            "completion_tokens_details": details,
            **usage,
        },
    )


def failure(body, capture=None):
    p = adapter(lambda r: httpx.Response(200, json=body))
    if capture is not None:
        p._capture = capture
    with pytest.raises(ProviderError) as exc:
        p.summarise(REQUEST)
    assert not exc.value.retryable
    return exc.value


# 1. All output consumed by reasoning.
def test_output_entirely_consumed_by_reasoning_is_classified_and_keeps_billing():
    error = failure(billed(content=None, reasoning=12000))
    assert error.error_class == "reasoning_budget_exhausted"
    assert (error.input_tokens, error.output_tokens, error.reasoning_tokens) == (100, 12000, 12000)
    assert error.cost_usd == pytest.approx(0.26444)
    assert error.finish_reason == "length"


# 2. Truncation despite final-response tokens.
def test_partial_json_after_some_reasoning_is_final_json_truncation():
    error = failure(billed(content='{"outlook": {"text": "SYNTHETIC', reasoning=1457))
    assert error.error_class == "final_json_truncated"
    assert error.reasoning_tokens == 1457


@pytest.mark.parametrize(
    ("finish", "native"), [("length", "max_tokens"), ("length", None), ("stop", "max_tokens")]
)
def test_a_length_finish_never_passes_and_complete_json_is_not_called_truncated(finish, native):
    body = billed(content=draft_json(1), finish=finish, native=native, reasoning=100)
    assert failure(body).error_class == "output_truncated"
    partial = billed(content='{"outlook":', finish=finish, native=native, reasoning=100)
    assert failure(partial).error_class == "final_json_truncated"


# 3. Complete JSON under the revised settings.
def test_revised_request_sends_low_effort_and_the_whole_output_budget():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(
            200,
            json=billed(content="{}", finish="stop", native="end_turn", out=9000, reasoning=1200),
        )

    response = adapter(handler).summarise(REQUEST)
    assert seen[0]["reasoning"] == {"effort": "low"}
    assert seen[0]["max_tokens"] == 12000
    assert "max_tokens" not in seen[0]["reasoning"]  # Opus 5.5 has no separate reasoning budget
    assert (response.output_tokens, response.reasoning_tokens) == (9000, 1200)


def pipeline(conn, p, grants, **kw):
    s = settings()
    return summarise_versions(
        conn,
        registry(llm="denied"),
        p,
        pricing=s.pricing,
        limits=s.limits,
        hosted_consents=grants,
        now_fn=lambda: NOW,
        **kw,
    )


def grant(conn, p, version_id, **changes):
    v = conn.execute("SELECT * FROM research_document_version WHERE id=?", (version_id,)).fetchone()
    sections = load_sections(conn, version_id)
    request = build_request(
        version_id,
        sections,
        prompt_version=SECOND_PILOT.prompt_version,
        limits=settings().limits,
        published_on="2026-08-13",
        institution="example",
        author="Example Research",
    )
    from nzstats.research.hosted import section_inventory_sha256

    fields = dict(
        version_id=version_id,
        institution="example",
        content_sha256=v["content_sha256"],
        text_sha256=v["text_sha256"],
        request_sha256=input_sha256(
            request, provider=p.name, model=p.model, parameters=p.parameters()
        ),
        model=p.model,
        provider_id="google-vertex/europe",
        approved_by="Synthetic Owner",
        approved_at=NOW,
        expires_at=NOW + timedelta(hours=1),
        rights_review="Synthetic rights review",
        provider_review="Synthetic provider review",
        budget_approved_usd=5,
        approved_section_ordinals=tuple(sections),
        sections_sha256=section_inventory_sha256(sections),
        experiment=EXPERIMENT,
    )
    return HostedConsent(**{**fields, **changes})


def test_complete_verified_output_is_stored_unreviewed_with_reasoning_metadata(conn):
    v = seed_version(conn)
    # Compact, single-line and with absent optional fields, as outlook-v4 asks.
    text = json.dumps(draft(v), separators=(",", ":"))
    p = adapter(
        lambda r: httpx.Response(
            200,
            json=billed(content=text, finish="stop", native="end_turn", out=7000, reasoning=900),
        )
    )
    result = pipeline(conn, p, [grant(conn, p, v)], version_ids=[v])
    assert result.items[0].outcome == "verified"
    row = rows(conn, "research_summary")[0]
    assert row["review_status"] == "unreviewed"
    params = json.loads(row["parameters"])
    assert params["reasoning_tokens"] == 900
    assert params["finish_reason"] == "stop"
    assert params["reasoning_effort"] == "low"
    assert params["experiment"] == EXPERIMENT


# 4. Invalid, incomplete or absent final JSON.
@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ('{"outlook": ', "invalid_json"),
        ("not JSON", "invalid_json"),
        ("[1, 2]", "invalid_json"),
        (None, "missing_final_content"),
        ("", "missing_final_content"),
        ("   \n", "missing_final_content"),
    ],
)
def test_stop_without_complete_json_is_named_precisely(content, expected):
    body = billed(content=content, finish="stop", native="end_turn", out=900, reasoning=100)
    assert failure(body).error_class == expected


def test_fenced_json_is_not_silently_repaired():
    body = billed(content='```json\n{"a":1}\n```', finish="stop", native="end_turn", out=900)
    assert failure(body).error_class == "invalid_json"


# 5. Unsupported reasoning parameters.
@pytest.mark.parametrize("effort", [None, "", "high", "xhigh", "max", "minimal", "none", "LOW"])
def test_unreviewed_reasoning_effort_is_refused_at_configuration(effort):
    env = {**ENV_4N, "NZSTATS_OPENROUTER_REASONING_EFFORT": effort}
    if effort is None:
        del env["NZSTATS_OPENROUTER_REASONING_EFFORT"]
    with pytest.raises(pv.LlmConfigError):
        pv.load_llm_settings(env)


def test_medium_effort_is_reviewable_but_is_not_the_authorised_experiment():
    env = {**ENV_4N, "NZSTATS_OPENROUTER_REASONING_EFFORT": "medium"}
    assert pv.load_llm_settings(env).openrouter_reasoning_effort == "medium"
    with pytest.raises(pv.LlmConfigError):
        adapter(lambda r: httpx.Response(500), openrouter_reasoning_effort="medium")


def test_provider_refusing_a_parameter_is_one_failed_attempt_never_a_downgraded_retry():
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(404, json={"error": {"message": "SYNTHETIC no endpoints"}})

    p = adapter(handler)
    with pytest.raises(ProviderError) as exc:
        p.summarise(REQUEST)
    assert exc.value.error_class == "bad_request" and not exc.value.retryable
    assert len(calls) == 1
    assert calls[0]["provider"]["require_parameters"] is True


def test_an_unregistered_experiment_is_refused():
    with pytest.raises(pv.LlmConfigError):
        pv.build_provider(replace(settings(), openrouter_experiment="another-experiment"))


@pytest.mark.parametrize(
    "limits",
    [{"max_output_tokens": 11999}, {"timeout_seconds": 250}, {"max_run_usd": 1.01}],
)
def test_an_experiment_pins_its_own_reviewed_settings(limits):
    s = settings()
    with pytest.raises(pv.LlmConfigError):
        pv.build_provider(replace(s, limits=replace(s.limits, **limits)))


# 6 and 7. Configuration and larger allowances.
@pytest.mark.parametrize(
    "change",
    [
        {"NZSTATS_LLM_MAX_OUTPUT_TOKENS": "12001"},
        {"NZSTATS_LLM_TIMEOUT_SECONDS": "199"},  # 12,000 tokens would not fit at 60 tokens/s
        {"NZSTATS_LLM_MAX_RETRIES": "1"},
        {"NZSTATS_LLM_OUTPUT_USD_PER_MTOK": "23"},
    ],
)
def test_larger_allowance_cannot_relax_the_other_limits(change):
    with pytest.raises(pv.LlmConfigError):
        pv.load_llm_settings({**ENV_4N, **change})


def test_full_allowance_at_the_reviewed_price_is_accepted_and_one_more_token_is_not():
    p = adapter(
        lambda r: httpx.Response(
            200, json=billed(content="{}", finish="stop", native="end_turn", reasoning=4000)
        )
    )
    assert p.summarise(REQUEST).cost_usd == pytest.approx(0.26444)
    over = billed(content="{}", finish="stop", native="end_turn", out=12001, reasoning=1)
    assert failure(over).error_class == "usage_exceeded"
    expensive = billed(content="{}", finish="stop", native="end_turn", cost=0.3)
    assert failure(expensive).error_class == "usage_exceeded"


def test_reservation_covers_the_entire_output_allowance_and_settles_on_reported_cost(conn):
    from nzstats.research.openrouter import input_token_bound

    v = seed_version(conn)
    body = billed(content="{}", finish="stop", native="end_turn", out=7000, reasoning=500)
    p = adapter(lambda r: httpx.Response(200, json=body))
    pipeline(conn, p, [grant(conn, p, v)], version_ids=[v])
    reservation = rows(conn, "research_llm_reservation")[0]
    request = build_request(
        v,
        load_sections(conn, v),
        prompt_version=SECOND_PILOT.prompt_version,
        limits=settings().limits,
        published_on="2026-08-13",
        institution="example",
        author="Example Research",
    )
    assert reservation["reserved_usd"] == pytest.approx(
        (input_token_bound(request) * 4.4 + 12000 * 22) / 1e6
    )
    assert reservation["actual_usd"] == pytest.approx(body["usage"]["cost"])
    assert reservation["settle_basis"] == "reported"


# 8. Historical attempts and spend are preserved.
def first_pilot_rows(conn, versions=(1, 2), costs=(0.20237976, 0.179898444)):
    """The Phase 4M ledger's shape: a run with no experiment tag and settled reservations."""
    rid = ss.start_run(
        conn,
        provider="openrouter",
        model="anthropic/claude-opus-5.5",
        hosted=True,
        prompt_version="outlook-v3",
        processing_version="3b-1",
        limits={"max_output_tokens": 6000},
        dry_run=False,
        now=NOW - timedelta(hours=1),
    )
    for version, cost in zip(versions, costs, strict=True):
        held = ss.reserve(
            conn,
            run_id=rid,
            version_id=version,
            call_no=1,
            provider="openrouter",
            model="anthropic/claude-opus-5.5",
            amount_usd=0.3,
            period_cap_usd=5,
            since=NOW - timedelta(days=30),
            now=NOW - timedelta(hours=1),
            expires_at=NOW,
        )
        assert held is not None
        ss.settle(conn, held, actual_usd=cost, basis="reported", now=NOW - timedelta(minutes=59))
    return rid


def snapshot(conn, table):
    return [dict(r) for r in rows(conn, table)]


def test_first_pilot_slots_stay_consumed_without_an_authorised_experiment(conn):
    a, b, c = (seed_version(conn, doc=d) for d in "abc")
    first_pilot_rows(conn, (a, b))
    old = ss.PilotScope()
    assert old.experiment == "phase-4m"
    assert ss.openrouter_refusal(conn, a, 0.01, scope=old) == "attempt_consumed"
    assert ss.openrouter_refusal(conn, c, 0.01, scope=old) == "lifetime_attempts_exhausted"
    assert ss.openrouter_refusal(conn, a, 0.01) == "attempt_consumed"  # the default is 4M
    env_provider = pv.build_provider(
        pv.load_llm_settings(ENV_4N),
        client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))),
    )
    assert "experiment" not in env_provider.parameters()  # the CLI path cannot select one


def test_second_experiment_appends_without_changing_any_historical_row(conn):
    a, b = seed_version(conn), seed_version(conn, doc="b")
    first_pilot_rows(conn, (a, b))
    tables = ("research_llm_run", "research_llm_reservation")
    before = {t: snapshot(conn, t) for t in tables}
    p = adapter(lambda r: httpx.Response(200, json=billed(content=None, reasoning=12000)))
    result = pipeline(conn, p, [grant(conn, p, a)], version_ids=[a])
    assert result.items[0].error_class == "reasoning_budget_exhausted"
    for table, old in before.items():
        assert snapshot(conn, table)[: len(old)] == old
    run_row = rows(conn, "research_llm_run")[-1]
    assert json.loads(run_row["limits"])["experiment"] == EXPERIMENT
    assert rows(conn, "research_llm_reservation")[-1]["version_id"] == a
    assert ss.lifetime_spent(conn) == pytest.approx(0.382278204 + 0.26444)


def test_a_failed_second_attempt_is_consumed_and_never_retried(conn):
    a = seed_version(conn)
    first_pilot_rows(conn, (a, seed_version(conn, doc="b")))
    calls = []
    p = adapter(lambda r: calls.append(r) or httpx.Response(500))
    assert pipeline(conn, p, [grant(conn, p, a)], version_ids=[a]).items[0].outcome == (
        "provider_error"
    )
    second = pipeline(conn, p, [grant(conn, p, a)], version_ids=[a])
    assert second.items[0].outcome == "attempt_consumed" and len(calls) == 1


def test_experiment_attempt_and_spend_limits_hold_under_the_unchanged_lifetime_cap(conn):
    versions = [seed_version(conn, doc=d) for d in "abcd"]
    scope = ss.PilotScope(EXPERIMENT, 2, 1.0)
    first_pilot_rows(conn, versions[:2])
    tagged = ss.start_run(
        conn,
        provider="openrouter",
        model="m",
        hosted=True,
        prompt_version=SECOND_PILOT.prompt_version,
        processing_version="3b-1",
        limits={"experiment": EXPERIMENT},
        dry_run=False,
        now=NOW,
    )

    def hold(version, amount, s=scope):
        return ss.reserve(
            conn,
            run_id=tagged,
            version_id=version,
            call_no=1,
            provider="openrouter",
            model="m",
            amount_usd=amount,
            period_cap_usd=5,
            since=NOW - timedelta(days=30),
            now=NOW,
            expires_at=NOW + timedelta(hours=1),
            scope=s,
        )

    assert hold(versions[0], 1.01) is None  # over the experiment's own US$1
    assert hold(versions[0], 0.6) is not None
    assert hold(versions[1], 0.41) is None  # 0.6 held + 0.41 exceeds US$1
    assert hold(versions[1], 0.3) is not None
    assert hold(versions[2], 0.001) is None  # two experiment attempts used
    # A lifetime cap keeps counting every experiment, including first-pilot spend.
    wide = ss.PilotScope("synthetic-other", 5, 5.0)
    assert hold(versions[2], 4.2, wide) is None
    assert ss.lifetime_spent(conn) == pytest.approx(0.382278204 + 0.9)


def tagged_hold(conn, version, scope, rid):
    return ss.reserve(
        conn,
        run_id=rid,
        version_id=version,
        call_no=1,
        provider="openrouter",
        model="m",
        amount_usd=0.01,
        period_cap_usd=5,
        since=NOW - timedelta(days=30),
        now=NOW,
        expires_at=NOW + timedelta(hours=1),
        scope=scope,
    )


def test_retagging_history_cannot_exceed_lifetime_attempts(conn):
    versions = [seed_version(conn, doc=d) for d in "abcde"]
    scope = ss.PilotScope("synthetic-unbounded", 99, 5.0)
    rid = first_pilot_rows(conn, versions[:2])
    conn.execute('UPDATE research_llm_run SET limits=\'{"experiment":"synthetic-other"}\'')
    for version in versions[2:4]:
        assert ss.openrouter_refusal(conn, version, 0.01, scope=scope) is None
        tagged_hold(conn, version, scope, rid)
    assert ss.openrouter_refusal(conn, versions[4], 0.01, scope=scope) == (
        "lifetime_attempts_exhausted"
    )


def test_retagging_a_run_cannot_restore_a_consumed_version_slot(conn):
    treasury, rbnz = seed_version(conn), seed_version(conn, doc="b")
    first_pilot_rows(conn, (treasury, rbnz))
    scope = ss.PilotScope(EXPERIMENT, 2, 1.0)
    second = ss.start_run(
        conn,
        provider="openrouter",
        model="m",
        hosted=True,
        prompt_version=SECOND_PILOT.prompt_version,
        processing_version="3b-1",
        limits={"experiment": EXPERIMENT},
        dry_run=False,
        now=NOW,
    )
    assert tagged_hold(conn, treasury, scope, second) is not None
    assert ss.openrouter_refusal(conn, treasury, 0.01, scope=scope) == "attempt_consumed"
    conn.execute("UPDATE research_llm_run SET limits='{}' WHERE id=?", (second,))
    assert ss.openrouter_refusal(conn, treasury, 0.01, scope=scope) == "attempt_consumed"
    with pytest.raises(ss.AttemptConsumed):
        tagged_hold(conn, treasury, scope, second)
    # The other version's own unused slot in this experiment is unaffected.
    assert ss.openrouter_refusal(conn, rbnz, 0.01, scope=scope) is None


# 9. Expired or mismatched approval.
@pytest.mark.parametrize(
    "change",
    [
        {"expires_at": NOW},
        {"approved_at": NOW + timedelta(seconds=1)},
        {"experiment": "phase-4m"},
        {"experiment": "another-experiment"},
        {"request_sha256": "0" * 64},
        {"budget_approved_usd": 6},
    ],
)
def test_expired_or_mismatched_consent_never_transmits(conn, change):
    v = seed_version(conn)
    calls = []
    p = adapter(lambda r: calls.append(r) or httpx.Response(500))
    result = pipeline(conn, p, [grant(conn, p, v, **change)], version_ids=[v])
    assert calls == [] and result.refusals
    assert rows(conn, "research_llm_reservation") == []


@pytest.mark.parametrize("error", [{}, "", 0, False, [], {"code": 502}])
@pytest.mark.parametrize("where", ["top", "choice"])
def test_a_present_error_field_fails_whatever_its_value(where, error):
    valid = billed(content="{}", finish="stop", native="end_turn", out=10)
    if where == "top":
        valid["error"] = error
    else:
        valid["choices"][0]["error"] = error
    assert failure(valid).error_class == "upstream_error"


def test_a_null_error_field_is_not_a_failure():
    valid = billed(content="{}", finish="stop", native="end_turn", out=10)
    valid["error"] = None
    valid["choices"][0]["error"] = None
    assert adapter(lambda r: httpx.Response(200, json=valid)).summarise(REQUEST).text == "{}"


def test_changed_timeout_invalidates_an_existing_consent_before_transmission(conn):
    v = seed_version(conn)
    p = adapter(lambda r: httpx.Response(500))
    original = grant(conn, p, v)
    base = pv.load_llm_settings(ENV_4N)
    longer = replace(base, limits=replace(base.limits, timeout_seconds=301))
    calls = []
    other = pv.build_provider(
        longer,
        client=httpx.Client(
            transport=httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(500))
        ),
    )
    assert grant(conn, other, v).request_sha256 != original.request_sha256
    result = summarise_versions(
        conn,
        registry(llm="denied"),
        other,
        pricing=longer.pricing,
        limits=longer.limits,
        hosted_consents=[replace(original, experiment="phase-4m")],
        version_ids=[v],
        now_fn=lambda: NOW,
    )
    assert calls == [] and result.refusals
    assert rows(conn, "research_llm_reservation") == []


@pytest.mark.parametrize(
    "change",
    [
        lambda b: b["choices"][0].update(native_finish_reason="refusal"),
        lambda b: b["choices"][0]["message"].update(refusal="SYNTHETIC decline"),
        lambda b: b["choices"][0]["message"].update(refusal=""),
    ],
)
def test_refusal_metadata_rejects_otherwise_valid_json(change):
    body = billed(content=draft_json(1), finish="stop", native="end_turn", out=10)
    change(body)
    error = failure(body)
    assert error.error_class == "refused" and "SYNTHETIC" not in str(error)


def test_a_null_message_refusal_is_not_a_failure():
    body = billed(content="{}", finish="stop", native="end_turn", out=10)
    body["choices"][0]["message"]["refusal"] = None
    assert adapter(lambda r: httpx.Response(200, json=body)).summarise(REQUEST).text == "{}"


def test_an_error_in_any_choice_is_an_upstream_failure():
    body = billed(content="{}", finish="stop", native="end_turn", out=10)
    body["choices"].append({"error": {"code": 502, "message": "SYNTHETIC"}})
    assert failure(body).error_class == "upstream_error"


def test_more_than_one_choice_is_never_accepted():
    body = billed(content="{}", finish="stop", native="end_turn", out=10)
    body["choices"].append(body["choices"][0])
    assert failure(body).error_class == "invalid_response"


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ('{"outlook":{"text":"SYNTHETIC', "final_json_truncated"),  # inside a string
        ('{"outlook":', "final_json_truncated"),  # value expected at the end
        ('{"a":1,', "final_json_truncated"),
        ('{"a":1', "final_json_truncated"),
        ('{"outlook":1} trailing text', "output_truncated"),  # closed object, then other text
        ('{"a":1 x}', "output_truncated"),  # invalid mid-document, not cut off
        ("not JSON", "output_truncated"),
    ],
)
def test_truncation_is_named_only_when_the_parser_ran_out_of_text(content, expected):
    assert failure(billed(content=content, reasoning=100)).error_class == expected


def test_prompt_effort_or_cap_change_invalidates_an_existing_request_hash(conn):
    v = seed_version(conn)
    p = adapter(lambda r: httpx.Response(500))
    original = grant(conn, p, v)
    other = pv.build_provider(
        replace(pv.load_llm_settings(ENV_4N), openrouter_reasoning_effort="medium"),
        client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))),
    )
    assert grant(conn, other, v, experiment="phase-4m").request_sha256 != original.request_sha256


# 10. Strict routing stays exact.
def test_revised_settings_keep_the_exact_private_route_and_no_fallback():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(
            200, json=billed(content="{}", finish="stop", native="end_turn", out=10)
        )

    adapter(handler).summarise(REQUEST)
    assert seen[0]["provider"] == {
        "only": ["google-vertex/europe"],
        "zdr": True,
        "data_collection": "deny",
        "allow_fallbacks": False,
        "require_parameters": True,
    }
    assert seen[0]["response_format"] == {"type": "json_object"}
    assert not {"models", "route", "tools", "plugins", "transforms", "temperature"} & seen[0].keys()


@pytest.mark.parametrize(
    "identity", [{"provider": "Anthropic"}, {"provider": None}, {"model": "another"}]
)
def test_unexpected_serving_identity_is_a_route_failure_even_when_truncated(identity):
    body = {**billed(content=None, reasoning=12000), **identity}
    assert failure(body).error_class == "route_unverified"


# 11. Missing or inconsistent usage.
@pytest.mark.parametrize(
    "usage",
    [
        {"completion_tokens_details": {"reasoning_tokens": 12001}},
        {"completion_tokens_details": {"reasoning_tokens": -1}},
        {"completion_tokens_details": {"reasoning_tokens": True}},
        {"completion_tokens_details": {"reasoning_tokens": "1"}},
        {"completion_tokens_details": "unexpected"},
        {"total_tokens": 7},
    ],
)
def test_inconsistent_usage_metadata_is_refused(usage):
    body = billed(content="{}", finish="stop", native="end_turn", **usage)
    assert failure(body).error_class == "usage_unverified"


@pytest.mark.parametrize(
    "body",
    [
        billed(content=None),  # no reasoning count: exhaustion is not established
        billed(content=None, reasoning=5000),  # some tokens unaccounted for
        billed(content=None, out=9000, reasoning=9000),  # below the cap: stopped for another reason
    ],
)
def test_truncation_without_supporting_metadata_is_not_given_a_specific_cause(body):
    assert failure(body).error_class == "output_truncated"


def test_missing_usage_outranks_any_cause_and_absent_reasoning_count_stays_unknown():
    body = billed(content=None, reasoning=12000)
    del body["usage"]
    assert failure(body).error_class == "usage_unverified"
    ok = billed(content="{}", finish="stop", native="end_turn", out=20)
    response = adapter(lambda r: httpx.Response(200, json=ok)).summarise(REQUEST)
    assert response.reasoning_tokens is None


# 12. Evidence-verifier rejection after successful parsing.
def test_verifier_rejection_after_valid_json_cannot_reach_review_or_display(conn):
    v = seed_version(conn)
    output = draft(v)
    output["forecasts"][0]["value"] = 9.9  # not in the evidence
    text = json.dumps(output, separators=(",", ":"))
    p = adapter(
        lambda r: httpx.Response(
            200, json=billed(content=text, finish="stop", native="end_turn", out=3000)
        )
    )
    result = pipeline(conn, p, [grant(conn, p, v)], version_ids=[v])
    assert result.items[0].outcome == "failed_verification"
    row = rows(conn, "research_summary")[0]
    assert rows(conn, "research_forecast_claim") == []
    reg = display_registry(previewable())
    assert private_summaries(conn, reg) == []
    assert why_not_private(conn, reg, row["id"]).startswith("not verified")
    with pytest.raises(ss.ReviewError):
        ss.review(conn, row["id"], decision="approved", reviewer="Synthetic", note=None, now=NOW)


@pytest.mark.parametrize(
    "body",
    [
        billed(content=None, reasoning=12000),
        billed(content=draft_json(1), reasoning=100),
        billed(content="{", finish="stop", native="end_turn", out=10),
        {"error": {"code": 502, "message": "SYNTHETIC upstream"}},
    ],
)
def test_failed_responses_store_no_text_and_cannot_reach_review_or_display(conn, body):
    v = seed_version(conn)
    p = adapter(lambda r: httpx.Response(200, json=body))
    result = pipeline(conn, p, [grant(conn, p, v)], version_ids=[v])
    assert result.items[0].outcome == "provider_error"
    row = rows(conn, "research_summary")[0]
    assert (row["raw_output"], row["output_json"]) == (None, None)
    assert rows(conn, "research_forecast_claim") == []
    reg = display_registry(previewable())
    assert private_summaries(conn, reg) == []
    assert why_not_private(conn, reg, row["id"]).startswith("not verified")
    with pytest.raises(ss.ReviewError):
        ss.review(conn, row["id"], decision="approved", reviewer="Synthetic", note=None, now=NOW)


# Failure taxonomy and diagnostics.
@pytest.mark.parametrize(
    "body",
    [
        {"error": {"code": 502, "message": "SYNTHETIC upstream"}},
        envelope(error={"code": 502, "message": "SYNTHETIC upstream"}),
        billed(content="", finish="error", native="error"),
        envelope(
            choices=[
                {
                    "finish_reason": "stop",
                    "error": {"code": 502, "message": "SYNTHETIC"},
                    "message": {"content": "{}"},
                }
            ]
        ),
    ],
)
def test_http_200_provider_errors_are_not_successful_inference(body):
    error = failure(body)
    assert error.error_class == "upstream_error"
    assert "SYNTHETIC" not in str(error)


def test_content_filter_is_a_refusal_not_truncation():
    body = billed(content="", finish="content_filter", native="refusal", out=10)
    assert failure(body).error_class == "refused"


def test_diagnostics_record_metadata_only_and_truncated_text_stays_in_the_raw_capture(caplog):
    captured = {}
    secret_text = "SYNTHETIC-PARTIAL-ECONOMIC-TEXT"
    body = billed(content='{"outlook":"' + secret_text, reasoning=1457)
    with caplog.at_level(logging.DEBUG):
        failure(body, capture=lambda name, data: captured.__setitem__(name, data))
    assert secret_text.encode() in captured["response.bin"]
    diagnostics = json.loads(captured["diagnostics.json"])
    assert secret_text not in captured["diagnostics.json"].decode()
    assert diagnostics == {
        "failure_class": "final_json_truncated",
        "finish_reason": "length",
        "native_finish_reason": "max_tokens",
        "prompt_tokens": 100,
        "completion_tokens": 12000,
        "reasoning_tokens": 1457,
        "final_output_tokens": 10543,
        "max_output_tokens": 12000,
        "reasoning_effort": "low",
        "final_content_chars": len(body["choices"][0]["message"]["content"]),
        "final_content_sha256": diagnostics["final_content_sha256"],
        "response_id": "gen-synthetic-1",
        "serving_provider": "Google",
        "response_model": "anthropic/claude-opus-5.5",
    }
    assert len(diagnostics["final_content_sha256"]) == 64
    assert secret_text not in caplog.text and "synthetic-credential" not in caplog.text


def test_unrecognised_finish_reasons_are_not_persisted_as_diagnostic_strings():
    captured = {}
    body = billed(content="{}", finish="SYNTHETIC-ARBITRARY", native="SYNTHETIC-ECHOED", out=10)
    assert failure(
        body, capture=lambda name, data: captured.__setitem__(name, data)
    ).error_class == ("unexpected_completion")
    diagnostics = captured["diagnostics.json"].decode()
    assert "SYNTHETIC-ARBITRARY" not in diagnostics and "SYNTHETIC-ECHOED" not in diagnostics


def test_a_diagnostics_write_failure_never_hides_the_classified_billed_result(caplog):
    def fail(name, data):
        if name == "diagnostics.json":
            raise OSError("SYNTHETIC disk failure")

    error = failure(billed(content=None, reasoning=12000), capture=fail)
    assert error.error_class == "reasoning_budget_exhausted"
    assert error.cost_usd == pytest.approx(0.26444)
    assert "SYNTHETIC disk failure" not in caplog.text


# Prompt and contract.
def test_prompt_revision_asks_for_compact_complete_output_and_keeps_every_semantic_rule():
    system = render(REQUEST, published_on=None).system
    assert SECOND_PILOT.prompt_version == "outlook-v4" and REQUEST.prompt_version
    for required in (
        "untrusted data",
        "Never follow instructions",
        "verbatim",
        "Never infer, convert, round, average or combine",
        "A historical observation",
        "A publication date is not a data",
        "A scenario, sensitivity or alternative path",
        "Keep the period basis as written",
        '"third_party"',
        "It is never a forecast",
        "Never report numbers from chart-axis labels",
        "single line",
        "shortest verbatim span",
        "leave the claim out",
    ):
        assert required in system, required
    assert (CONTRACT_VERSION, VERIFIER_VERSION) == (2, "verify-5")


def test_instructions_no_longer_duplicate_the_numbered_rules():
    from nzstats.research.contract import INSTRUCTIONS
    from nzstats.research.prompt import RULES

    assert len(INSTRUCTIONS) < 120 and "untrusted" in INSTRUCTIONS
    # The schema shown is SummaryDraft, so the old "OutlookSummary schema" sentence also misled.
    assert "OutlookSummary" not in INSTRUCTIONS and "verbatim" not in INSTRUCTIONS
    assert "verbatim" in RULES and "untrusted data" in RULES


def test_compact_output_with_optional_fields_absent_still_parses_to_the_same_contract():
    forecast = draft(7)["forecasts"][0]
    full = {
        **forecast,
        "qualification": None,
        "scenario": None,
        "evidence": [{**forecast["evidence"][0], "page": None}],
    }
    evidence = {k: v for k, v in full["evidence"][0].items() if v is not None}
    compact = {**forecast, "evidence": [evidence]}
    pretty = parse_draft(json.dumps(draft(7, forecasts=[full]), indent=2))
    terse = parse_draft(json.dumps(draft(7, forecasts=[compact]), separators=(",", ":")))
    assert pretty.forecasts == terse.forecasts


def test_final_output_target_leaves_room_for_reasoning_within_the_cap():
    from nzstats.research.prompt import OUTPUT_TARGET_CHARS

    observed_chars_per_token = 12407 / (6000 - 1457)  # the only Phase 4M final-output density
    expected = OUTPUT_TARGET_CHARS / observed_chars_per_token
    assert f"{OUTPUT_TARGET_CHARS:,} characters" in render(REQUEST, published_on=None).system
    assert SECOND_PILOT.max_output_tokens - expected >= 4000
    assert SECOND_PILOT.prompt_version == "outlook-v4" and PROMPT_VERSION == "outlook-v5"
