"""SYNTHETIC FIXTURE: exact consent and the shared SQLite spending/attempt gate."""

import hashlib
import json
import multiprocessing
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from threading import Barrier

import httpx
import pytest

from nzstats.research import summary_store as ss
from nzstats.research.contract import build_request
from nzstats.research.prompt import PROMPT_VERSION, input_sha256
from nzstats.research.providers import load_llm_settings
from nzstats.research.summarise import load_sections, summarise_versions
from nzstats.store.db import connect, migrate

from .llm_support import NOW, draft_json, seed_version
from .test_openrouter import ENV, envelope, provider
from .test_summarise import registry, rows


def consent(conn, p, version_id):
    from nzstats.research.hosted import HostedConsent

    v = conn.execute("SELECT * FROM research_document_version WHERE id=?", (version_id,)).fetchone()
    request = build_request(
        version_id,
        load_sections(conn, version_id),
        prompt_version=PROMPT_VERSION,
        limits=load_llm_settings(ENV).limits,
        published_on="2026-08-13",
        institution="example",
        author="Example Research",
    )
    return HostedConsent(
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
        expires_at=NOW + timedelta(days=1),
        rights_review="Synthetic licence and all third-party rights reviewed for hosted processing",
        provider_review="Synthetic owner accepts this exact provider and privacy/legal exceptions",
        budget_approved_usd=5,
        approved_section_ordinals=tuple(load_sections(conn, version_id)),
        sections_sha256=inventory_hash(load_sections(conn, version_id)),
    )


def inventory_hash(sections):
    rows = [[n, s.text, s.page_start, s.page_end, s.heading] for n, s in sorted(sections.items())]
    return hashlib.sha256(
        json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def scoped_consent(conn, p, version_id, ordinals):
    grant = consent(conn, p, version_id)
    sections = load_sections(conn, version_id)
    request = build_request(
        version_id,
        {n: sections[n] for n in ordinals},
        prompt_version=PROMPT_VERSION,
        limits=load_llm_settings(ENV).limits,
        published_on="2026-08-13",
        institution="example",
        author="Example Research",
    )
    return replace(
        grant,
        approved_section_ordinals=ordinals,
        request_sha256=input_sha256(
            request, provider=p.name, model=p.model, parameters=p.parameters()
        ),
    )


def test_approved_subset_excludes_unlicensed_text_from_the_actual_request(tmp_path):
    conn = connect(tmp_path / "scope.db")
    migrate(conn)
    version = seed_version(
        conn, sections=("UNLICENSED SYNTHETIC CONTENT", "Permitted synthetic text.")
    )
    sent = []
    p = provider(
        lambda req: (sent.append(json.loads(req.content)), httpx.Response(200, json=envelope()))[1]
    )
    grant = scoped_consent(conn, p, version, (1,))
    result = run(conn, p, (grant,), version_ids=[version])
    assert len(sent) == 1
    user = sent[0]["messages"][1]["content"]
    assert "Permitted synthetic text." in user
    assert "UNLICENSED" not in user
    assert "ordinal=1" in user and "ordinal=0" not in user
    assert result.items[0].outcome == "invalid_output"


@pytest.mark.parametrize(
    "mutation", ["selected_text", "unselected_text", "heading", "page", "extra", "missing"]
)
def test_inventory_drift_refuses_before_network_even_outside_approved_subset(tmp_path, mutation):
    conn = connect(tmp_path / "drift.db")
    migrate(conn)
    version = seed_version(conn)
    sent = []
    p = provider(lambda req: (sent.append(req), httpx.Response(200, json=envelope()))[1])
    grant = scoped_consent(conn, p, version, (1,))
    if mutation == "extra":
        conn.execute(
            "INSERT INTO research_section(version_id,ordinal,text,char_start,char_end) VALUES(?,2,'Extra synthetic text',0,20)",
            (version,),
        )
    elif mutation == "missing":
        conn.execute("DELETE FROM research_section WHERE version_id=? AND ordinal=0", (version,))
    else:
        col, ordinal, value = {
            "selected_text": ("text", 1, "Changed"),
            "unselected_text": ("text", 0, "Changed"),
            "heading": ("heading", 0, "Changed"),
            "page": ("page_start", 0, 99),
        }[mutation]
        conn.execute(
            f"UPDATE research_section SET {col}=? WHERE version_id=? AND ordinal=?",
            (value, version, ordinal),
        )
    result = run(conn, p, (grant,), version_ids=[version], dry_run=True)
    assert result.refusals and not result.items
    assert not sent
    assert conn.execute("SELECT count(*) FROM research_llm_reservation").fetchone()[0] == 0


@pytest.mark.parametrize("ordinals", [(), (1, 1), (1, 0), (True,), (99,)])
def test_invalid_approved_ordinal_lists_fail_closed(tmp_path, ordinals):
    conn = connect(tmp_path / "invalid-scope.db")
    migrate(conn)
    version = seed_version(conn)
    p = provider(lambda req: pytest.fail("invalid scope reached network"))
    grant = replace(consent(conn, p, version), approved_section_ordinals=ordinals)
    result = run(conn, p, (grant,), version_ids=[version], dry_run=True)
    assert result.refusals and not result.items


def run(conn, p, grants=(), **kw):
    settings = load_llm_settings(ENV)
    return summarise_versions(
        conn,
        registry(llm="denied"),
        p,
        pricing=settings.pricing,
        limits=settings.limits,
        hosted_consents=grants,
        now_fn=lambda: NOW,
        **kw,
    )


def test_institution_wide_hosted_permission_does_not_authorise_a_version(conn):
    seed_version(conn)
    calls = []
    p = provider(lambda r: calls.append(r) or httpx.Response(200, json=envelope()))
    settings = load_llm_settings(ENV)
    result = summarise_versions(
        conn, registry(), p, pricing=settings.pricing, limits=settings.limits, now_fn=lambda: NOW
    )
    assert calls == []
    assert result.refusals and "consent" in result.refusals[0][1]
    assert rows(conn, "research_llm_reservation") == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("version_id", 99),
        ("institution", "other"),
        ("content_sha256", "a" * 64),
        ("text_sha256", "b" * 64),
        ("request_sha256", "c" * 64),
        ("model", "other-model"),
        ("provider_id", "anthropic"),
        ("expires_at", NOW - timedelta(seconds=1)),
        ("approved_at", NOW + timedelta(hours=1)),
    ],
)
def test_changed_or_expired_consent_never_transmits(conn, field, value):
    v = seed_version(conn)
    calls = []
    p = provider(lambda r: calls.append(r) or httpx.Response(200, json=envelope()))
    grant = replace(consent(conn, p, v), **{field: value})
    result = run(conn, p, [grant])
    assert calls == [] and result.refusals
    assert rows(conn, "research_llm_reservation") == []


def test_exact_version_grant_does_not_enable_another_document_or_source_permission(conn):
    v = seed_version(conn)
    seed_version(conn, doc="unapproved")
    calls = []
    p = provider(lambda r: calls.append(r) or httpx.Response(200, json=envelope()))
    result = run(conn, p, [consent(conn, p, v)], dry_run=True)
    assert [i.version_id for i in result.items] == [v]
    assert [i.outcome for i in result.items] == ["would_summarise"]
    assert result.refusals and calls == []
    assert rows(conn, "research_llm_run") == []
    assert registry(llm="denied")["example"].llm_processing == "denied"


def test_failed_attempt_is_durable_across_runs_models_and_prompt_changes(conn):
    v = seed_version(conn)
    calls = []
    p = provider(lambda r: calls.append(r) or httpx.Response(500, text="synthetic failure"))
    grants = [consent(conn, p, v)]
    first = run(conn, p, grants)
    second = run(conn, p, grants)
    assert first.items[0].outcome == "provider_error"
    assert second.items[0].outcome == "attempt_consumed"
    assert len(calls) == 1 and len(rows(conn, "research_llm_reservation")) == 1


def test_actual_excess_cost_is_audited_and_refused(conn):
    v = seed_version(conn)
    p = provider(
        lambda r: httpx.Response(
            200,
            json=envelope(
                usage={
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "cost": 9,
                }
            ),
        )
    )
    result = run(conn, p, [consent(conn, p, v)])
    assert result.items[0].outcome == "provider_error"
    assert result.spent_usd == 9
    assert rows(conn, "research_llm_usage")[0]["cost_usd"] == 9
    assert rows(conn, "research_llm_reservation")[0]["actual_usd"] == 9


def test_reported_metadata_and_cost_are_preserved_with_invalid_contract(conn):
    v = seed_version(conn)
    p = provider(lambda r: httpx.Response(200, json=envelope()))
    result = run(conn, p, [consent(conn, p, v)])
    assert result.items[0].outcome == "invalid_output"
    assert result.spent_usd == pytest.approx(0.00088)
    params = json.loads(rows(conn, "research_summary")[0]["parameters"])
    assert params["serving_provider"] == "Google"
    assert params["response_id"] == "gen-synthetic-1"


def test_request_cost_must_fit_before_a_dry_run_can_be_eligible(conn):
    v = seed_version(conn)
    calls = []
    p = provider(lambda r: calls.append(r) or httpx.Response(200, json=envelope()))
    settings = load_llm_settings(ENV)
    result = summarise_versions(
        conn,
        registry(llm="denied"),
        p,
        pricing=settings.pricing,
        limits=replace(settings.limits, max_run_usd=0.0001),
        hosted_consents=[consent(conn, p, v)],
        dry_run=True,
        now_fn=lambda: NOW,
    )
    assert result.items[0].outcome == "budget_exhausted" and calls == []


def test_openrouter_reservations_enforce_lifetime_cap_and_two_total_attempts(conn):
    versions = [seed_version(conn, doc=f"doc-{n}") for n in range(3)]

    def reserve(v, amount):
        return ss.reserve(
            conn,
            run_id=1,
            version_id=v,
            call_no=1,
            provider="openrouter",
            model="synthetic",
            amount_usd=amount,
            period_cap_usd=5,
            since=NOW,
            now=NOW,
            expires_at=NOW + timedelta(minutes=1),
        )

    # A real run row supplies the foreign key.
    p = provider(lambda r: httpx.Response(500))
    run(conn, p, [consent(conn, p, versions[0])])
    assert reserve(versions[1], 5) is None
    assert reserve(versions[1], 1) is not None
    assert reserve(versions[2], 0.001) is None


def test_concurrent_same_version_reservations_allow_one_attempt(tmp_path):
    path = tmp_path / "shared.db"
    conn = connect(path)
    migrate(conn)
    v = seed_version(conn)
    # Create audit row without using the provider.
    rid = ss.start_run(
        conn,
        provider="openrouter",
        model="synthetic",
        hosted=True,
        prompt_version="synthetic",
        processing_version="synthetic",
        limits={},
        dry_run=False,
        now=NOW,
    )
    conn.close()
    barrier = Barrier(2)

    def reserve():
        c = connect(path)
        barrier.wait()
        try:
            return ss.reserve(
                c,
                run_id=rid,
                version_id=v,
                call_no=1,
                provider="openrouter",
                model="synthetic",
                amount_usd=1,
                period_cap_usd=5,
                since=NOW,
                now=NOW,
                expires_at=NOW + timedelta(minutes=1),
            )
        except ss.AttemptConsumed:
            return "attempt_consumed"
        finally:
            c.close()

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: reserve(), range(2)))
    assert results.count("attempt_consumed") == 1
    assert sum(isinstance(r, int) for r in results) == 1
    check = connect(path)
    try:
        assert len(rows(check, "research_llm_reservation")) == 1
    finally:
        check.close()


@pytest.mark.parametrize(
    "overrides",
    [
        {"max_retries": 1},
        {"max_output_tokens": 1},
        {"max_run_usd": 6},
        {"max_period_usd": 6},
        {"max_documents_per_run": 3},
        {"timeout_seconds": 1},
    ],
)
def test_pipeline_cannot_reserve_less_than_adapter_sends_or_relax_pilot_limits(conn, overrides):
    from nzstats.research.providers import LlmConfigError

    v = seed_version(conn)
    calls = []
    p = provider(lambda r: calls.append(r) or httpx.Response(200, json=envelope()))
    settings = load_llm_settings(ENV)
    with pytest.raises(LlmConfigError):
        summarise_versions(
            conn,
            registry(),
            p,
            pricing=settings.pricing,
            limits=replace(settings.limits, **overrides),
            hosted_consents=[consent(conn, p, v)],
            now_fn=lambda: NOW,
        )
    assert calls == [] and rows(conn, "research_llm_run") == []


def test_missing_usage_cost_does_not_undercount_an_excessive_token_claim(conn):
    v = seed_version(conn)
    p = provider(
        lambda r: httpx.Response(
            200,
            json=envelope(
                usage={
                    "prompt_tokens": 1_000_000,
                    "completion_tokens": 20,
                }
            ),
        )
    )
    result = run(conn, p, [consent(conn, p, v)])
    assert result.items[0].outcome == "provider_error"
    assert result.spent_usd == pytest.approx(4.40044)


@pytest.mark.parametrize("status", [400, 429, 500])
def test_billed_http_error_keeps_actual_cost_and_blocks_further_spend(conn, status):
    v = seed_version(conn)
    other = seed_version(conn, doc="other")
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status,
            json={
                "error": {"message": "synthetic-credential"},
                "usage": {"prompt_tokens": 100, "completion_tokens": 20, "cost": 9},
            },
        )

    p = provider(handler)
    grants = [consent(conn, p, v), consent(conn, p, other)]
    result = run(conn, p, grants)
    assert result.spent_usd == 9
    assert len(calls) == 1
    assert rows(conn, "research_llm_reservation")[0]["actual_usd"] == 9
    assert rows(conn, "research_llm_usage")[0]["cost_usd"] == 9


@pytest.mark.parametrize("mutation", ["expired", "purged"])
def test_consent_is_rechecked_after_blocking_reservation_before_dispatch(
    conn, monkeypatch, mutation, tmp_path
):
    v = seed_version(conn)
    calls = []
    p = provider(lambda r: calls.append(r) or httpx.Response(200, json=envelope()))
    grants = [consent(conn, p, v)]
    current = [NOW]
    original = ss.reserve

    def reserve(*args, **kw):
        rid = original(*args, **kw)
        if mutation == "expired":
            current[0] = NOW + timedelta(days=2)
        else:
            from nzstats.research import purge
            from nzstats.sources.artifacts import ArtifactStore

            purge.apply_purge(
                conn,
                purge.plan_purge(conn, "example", version_ids=(v,)),
                ArtifactStore(tmp_path / "raw"),
                reason="takedown",
                purged_by="Synthetic Owner",
                note="Synthetic concurrent purge",
                now=NOW,
            )
        return rid

    monkeypatch.setattr(ss, "reserve", reserve)
    settings = load_llm_settings(ENV)
    result = summarise_versions(
        conn,
        registry(),
        p,
        pricing=settings.pricing,
        limits=settings.limits,
        hosted_consents=grants,
        now_fn=lambda: current[0],
    )
    assert calls == [] and result.spent_usd == 0
    assert rows(conn, "research_llm_reservation")[0]["actual_usd"] == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"choices": [{"message": {"content": "{}"}, "finish_reason": "length"}]},
        {"choices": [{"message": {"content": "invalid"}, "finish_reason": "stop"}]},
        {"model": "openai/gpt-5.6-sol", "provider": "Azure"},
    ],
)
def test_billed_failed_completion_retains_safe_response_identity(conn, changes):
    v = seed_version(conn)
    p = provider(lambda r: httpx.Response(200, json=envelope(**changes)))
    run(conn, p, [consent(conn, p, v)])
    params = json.loads(rows(conn, "research_summary")[0]["parameters"])
    assert params["response_id"] == "gen-synthetic-1"
    assert params["serving_provider"] == changes.get("provider", "Google")
    assert params["response_model"] == changes.get("model", "anthropic/claude-opus-5.5")


def test_dry_run_never_promises_a_second_attempt(conn):
    v = seed_version(conn)
    p = provider(lambda r: httpx.Response(500))
    grants = [consent(conn, p, v)]
    run(conn, p, grants)
    result = run(conn, p, grants, dry_run=True)
    assert result.items[0].outcome == "attempt_consumed"


@pytest.mark.parametrize("status", [200, 400, 500])
def test_malformed_identity_never_discards_valid_billing(conn, status):
    v = seed_version(conn)
    p = provider(
        lambda r: httpx.Response(
            status,
            json=envelope(
                model=[], usage={"prompt_tokens": 100, "completion_tokens": 20, "cost": 9}
            ),
        )
    )
    result = run(conn, p, [consent(conn, p, v)])
    assert result.spent_usd == 9
    assert rows(conn, "research_llm_reservation")[0]["actual_usd"] == 9


@pytest.mark.parametrize("existing_attempt", [False, True])
def test_dry_run_simulates_cumulative_spend_and_attempt_capacity(conn, existing_attempt):
    old = seed_version(conn, doc="old")
    p = provider(lambda r: httpx.Response(500))
    if existing_attempt:
        run(conn, p, [consent(conn, p, old)])
    a = seed_version(conn, doc="a")
    b = seed_version(conn, doc="b")
    settings = load_llm_settings(ENV)
    result = summarise_versions(
        conn,
        registry(),
        p,
        pricing=settings.pricing,
        limits=replace(settings.limits, max_run_usd=5 if existing_attempt else 0.25),
        hosted_consents=[consent(conn, p, a), consent(conn, p, b)],
        dry_run=True,
        now_fn=lambda: NOW,
    )
    assert [i.outcome for i in result.items] == ["would_summarise", "budget_exhausted"]
    assert len(rows(conn, "research_llm_reservation")) == int(existing_attempt)


@pytest.mark.parametrize("dry_run", [False, True])
def test_rendered_context_limit_refuses_before_consuming_or_simulating_an_attempt(conn, dry_run):
    v = seed_version(conn, ["x"] * 4000)
    calls = []
    p = provider(lambda r: calls.append(r) or httpx.Response(200, json=envelope()))
    result = run(conn, p, [consent(conn, p, v)], dry_run=dry_run)
    assert result.items[0].outcome == "input_too_long"
    assert result.spent_usd == 0 and calls == []
    assert rows(conn, "research_llm_reservation") == []


@pytest.mark.parametrize("dry_run", [False, True])
@pytest.mark.parametrize("prior", ["failed", "interrupted", "completed", "model", "prompt", "held"])
def test_consumed_version_does_not_block_next_eligible_version(conn, dry_run, prior):
    a = seed_version(conn)

    def first_response(request):
        if prior == "interrupted":
            raise KeyboardInterrupt
        if prior == "completed":
            return httpx.Response(
                200,
                json=envelope(
                    choices=[
                        {
                            "message": {"content": draft_json(a)},
                            "finish_reason": "stop",
                        }
                    ]
                ),
            )
        return httpx.Response(500)

    first = provider(first_response)
    if prior in {"model", "prompt", "held"}:
        reserve_pilot(
            conn,
            a,
            model="different-model" if prior == "model" else first.model,
            prompt="different-prompt" if prior == "prompt" else PROMPT_VERSION,
        )
    elif prior == "interrupted":
        with pytest.raises(KeyboardInterrupt):
            run(conn, first, [consent(conn, first, a)])
    else:
        run(conn, first, [consent(conn, first, a)])
    if prior == "completed":
        assert rows(conn, "research_summary")[0]["status"] == "verified"
    old = dict(rows(conn, "research_llm_reservation")[0])
    b = seed_version(conn, doc="b")
    calls = []
    p = provider(lambda r: calls.append(r) or httpx.Response(200, json=envelope()))
    grants = [consent(conn, p, v) for v in (a, b)]
    changes = conn.total_changes
    result = run(conn, p, grants, dry_run=dry_run, limit=1)
    assert [(i.version_id, i.outcome) for i in result.items] == [
        (a, "exists" if prior == "completed" else "attempt_consumed"),
        (b, "would_summarise" if dry_run else "invalid_output"),
    ]
    assert result.outcome == "ok"
    assert len(calls) == (0 if dry_run else 1)
    saved = rows(conn, "research_llm_reservation")
    assert dict(saved[0]) == old
    assert len(saved) == (1 if dry_run else 2)
    if prior in {"interrupted", "held"}:
        assert saved[0]["actual_usd"] is None and saved[0]["reserved_usd"] > 0
    if dry_run:
        assert conn.total_changes == changes


def reserve_pilot(
    conn,
    version,
    *,
    amount=0.2,
    model="synthetic",
    prompt="synthetic",
    now=NOW,
    provider_name="openrouter",
):
    rid = ss.start_run(
        conn,
        provider=provider_name,
        model=model,
        hosted=True,
        prompt_version=prompt,
        processing_version="synthetic",
        limits={},
        dry_run=False,
        now=now,
    )
    return ss.reserve(
        conn,
        run_id=rid,
        version_id=version,
        call_no=1,
        provider=provider_name,
        model=model,
        amount_usd=amount,
        period_cap_usd=5,
        since=now,
        now=now,
        expires_at=now + timedelta(hours=1),
    )


@pytest.mark.parametrize("dry_run", [False, True])
@pytest.mark.parametrize("budget", ["attempts", "lifetime", "run", "rolling"])
def test_global_exhaustion_still_blocks_all_new_versions(conn, dry_run, budget):
    old_time = NOW - timedelta(days=60)
    if budget in {"attempts", "lifetime", "rolling"}:
        old = seed_version(conn, doc="old")
        reserve_pilot(
            conn,
            old,
            amount=5 if budget in {"lifetime", "rolling"} else 0.2,
            now=NOW if budget == "rolling" else old_time,
            provider_name="fake" if budget == "rolling" else "openrouter",
        )
        if budget == "attempts":
            reserve_pilot(conn, seed_version(conn, doc="old-2"), now=old_time)
    versions = [seed_version(conn, doc=f"new-{n}") for n in range(2)]
    calls = []
    p = provider(lambda r: calls.append(r) or httpx.Response(200, json=envelope()))
    settings = load_llm_settings(ENV)
    limits = replace(settings.limits, max_run_usd=0.0001) if budget == "run" else settings.limits
    before = len(rows(conn, "research_llm_reservation"))
    changes = conn.total_changes
    result = summarise_versions(
        conn,
        registry(llm="denied"),
        p,
        pricing=settings.pricing,
        limits=limits,
        hosted_consents=[consent(conn, p, v) for v in versions],
        version_ids=versions,
        dry_run=dry_run,
        now_fn=lambda: NOW,
    )
    assert [i.outcome for i in result.items] == ["budget_exhausted", "budget_exhausted"]
    assert result.outcome == "budget_exhausted" and calls == []
    assert len(rows(conn, "research_llm_reservation")) == before
    if dry_run:
        assert conn.total_changes == changes


def test_reservation_race_skips_consumed_version_and_preserves_work_slot(conn, monkeypatch):
    a, b = seed_version(conn), seed_version(conn, doc="b")
    calls = []
    p = provider(lambda r: calls.append(r) or httpx.Response(200, json=envelope()))
    original = ss.reserve

    def racing_reserve(*args, **kw):
        if kw["version_id"] == a:
            original(*args, **kw)
        return original(*args, **kw)

    monkeypatch.setattr(ss, "reserve", racing_reserve)
    result = run(conn, p, [consent(conn, p, v) for v in (a, b)], limit=1)
    assert [(i.version_id, i.outcome) for i in result.items] == [
        (a, "attempt_consumed"),
        (b, "invalid_output"),
    ]
    assert len(calls) == 1
    assert [r["version_id"] for r in rows(conn, "research_llm_reservation")] == [a, b]


def reserve_in_process(path, rid, version, budget, barrier, results):
    c = connect(path)
    try:
        barrier.wait(timeout=20)
        results.put(
            ss.reserve(
                c,
                run_id=rid,
                version_id=version,
                call_no=1,
                provider="openrouter",
                model="synthetic",
                amount_usd=3 if budget == "lifetime" else 0.2,
                period_cap_usd=0.3 if budget == "rolling" else 10,
                since=NOW,
                now=NOW,
                expires_at=NOW + timedelta(hours=1),
            )
        )
    finally:
        c.close()


@pytest.mark.parametrize("budget", ["attempts", "lifetime", "rolling"])
def test_concurrent_distinct_versions_cannot_exceed_global_limits(tmp_path, budget):
    path = tmp_path / "global.db"
    conn = connect(path)
    migrate(conn)
    versions = [seed_version(conn, doc=f"doc-{n}") for n in range(3)]
    rid = ss.start_run(
        conn,
        provider="openrouter",
        model="synthetic",
        hosted=True,
        prompt_version="synthetic",
        processing_version="synthetic",
        limits={},
        dry_run=False,
        now=NOW,
    )
    ctx = multiprocessing.get_context("spawn")
    barrier, outcomes = ctx.Barrier(3), ctx.Queue()
    processes = [
        ctx.Process(target=reserve_in_process, args=(path, rid, v, budget, barrier, outcomes))
        for v in versions
    ]
    try:
        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=30)
            assert process.exitcode == 0
        results = [outcomes.get(timeout=5) for _ in processes]
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
        outcomes.close()
    expected = 2 if budget == "attempts" else 1
    assert sum(r is not None for r in results) == expected
    saved = rows(conn, "research_llm_reservation")
    assert len(saved) == expected
    assert sum(r["reserved_usd"] for r in saved) == pytest.approx(
        3 if budget == "lifetime" else expected * 0.2
    )
    conn.close()
