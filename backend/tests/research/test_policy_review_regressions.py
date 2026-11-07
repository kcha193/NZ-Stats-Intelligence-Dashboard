"""PR #51 adversarial regressions. Synthetic documents and mocked providers only."""

import json
import multiprocessing
from datetime import timedelta
from types import SimpleNamespace

import httpx
import pytest

from nzstats.research import pilot, policy_cli, purge
from nzstats.research import policy as pol
from nzstats.research import policy_run as run
from nzstats.research import summary_store as ss
from nzstats.sources.artifacts import ArtifactStore
from nzstats.store.db import connect

from .llm_support import NOW, seed_version
from .policy_support import policy_dict, registry, world, write_policy
from .test_pilot_treasury_v3 import spend
from .test_policy_run import KEY, Env, good_output


def execute(env, **kwargs):
    code = env.pre().confirm_code
    return run.execute_policy(
        env.conn, env.reg, env.data, env.path, env.version, confirm=code,
        interactive=True, ask=lambda _: code, api_key=KEY, client=env.client,
        operator="synthetic-operator", **kwargs,
    )  # fmt: skip


def race_worker(data, path, version, barrier, queue):
    """Each process confirms independently, then waits immediately before reservation."""
    env = Env.__new__(Env)
    env.conn, env.reg, env.data = connect(data / "nzstats.db"), registry(), data
    env.path, env.version = path, version
    env.policy, env.sha = pol.load_policy(path, data)
    env.posts, env.gets, env.content, env.status = [], [], json.dumps(good_output(version)), 200
    env.client = httpx.Client(transport=httpx.MockTransport(env.respond))

    def backup(conn, data_dir, output, now):
        pilot.verified_backup(conn, data_dir, output, now)
        barrier.wait(timeout=30)

    try:
        result = execute(env, now_fn=lambda: NOW, backup_check=backup)
        queue.put(("executed", len(env.posts), result.outcome))
    except pol.PolicyRefused as exc:
        queue.put(("refused", len(env.posts), exc.code))
    except BaseException as exc:
        queue.put(("error", len(env.posts), type(exc).__name__))
        raise
    finally:
        env.client.close()
        env.conn.close()


@pytest.mark.parametrize("same_content_version", [False, True])
@pytest.mark.parametrize("different_policy", [False, True])
def test_simultaneous_confirmations_transmit_once_across_policies_and_content(
    tmp_path, same_content_version, different_policy
):
    env = Env(tmp_path)
    other_version = env.version
    if same_content_version:
        # Independent publication, identical source bytes; both must be eligible before either reserves.
        original = env.conn.execute(
            "SELECT content_sha256 FROM research_document_version WHERE id=?", (env.version,)
        ).fetchone()[0]
        raw = (env.data / "raw" / original[:2] / original).read_bytes()
        other_conn, _, _, other_version = world(tmp_path, doc="equivalent", raw_bytes=raw)
        other_conn.close()
    other_path = env.path
    if different_policy:
        other_path = write_policy(
            env.data, policy_dict(env.reg, policy_id="independent-policy"), name="other.json"
        )
    ctx = multiprocessing.get_context("spawn")
    barrier, queue = ctx.Barrier(2), ctx.Queue()
    children = [
        ctx.Process(target=race_worker, args=(env.data, path, version, barrier, queue))
        for path, version in ((env.path, env.version), (other_path, other_version))
    ]
    try:
        for child in children:
            child.start()
        for child in children:
            child.join(timeout=45)
            assert child.exitcode == 0
        results = [queue.get(timeout=5) for _ in children]
    finally:
        for child in children:
            if child.is_alive():
                child.terminate()
                child.join(timeout=5)
    assert sorted(r[0] for r in results) == ["executed", "refused"], results
    assert sum(r[1] for r in results) == 1, results
    assert env.conn.execute("SELECT COUNT(*) FROM research_llm_reservation").fetchone()[0] == 1
    assert [e["event"] for e in env.events()].count("executed") == 1
    assert [e["refusal_code"] for e in env.events() if e["event"] == "refused"] == [
        "attempt_consumed"
    ]


@pytest.mark.parametrize("prior_scope", [None, "phase-4n-second-pilot", "policy-0123456789abcdef"])
@pytest.mark.parametrize("state", ["held", "settled", "abandoned"])
def test_atomic_policy_guard_counts_equivalent_content_in_every_scope_and_state(
    tmp_path, prior_scope, state
):
    env = Env(tmp_path)
    original = seed_version(env.conn, key="treasury", doc="original")
    equivalent = seed_version(env.conn, key="treasury", doc="reimport")
    spend(env.conn, original, prior_scope)
    # Use a separate held row for held/abandoned cases: settlement is irreversible.
    if state != "settled":
        fresh = seed_version(
            env.conn, sections=("other content",), key="treasury", doc="outstanding"
        )
        equivalent = seed_version(
            env.conn, sections=("other content",), key="treasury", doc="outstanding-copy"
        )
        rid = ss.start_run(
            env.conn,
            provider="openrouter",
            model=pilot.MODEL,
            hosted=True,
            prompt_version="outlook-v6",
            processing_version="3b-1",
            limits={"experiment": prior_scope} if prior_scope else {},
            dry_run=False,
            now=NOW,
        )
        scope = ss.PilotScope(prior_scope) if prior_scope else None
        assert ss.reserve(
            env.conn,
            run_id=rid,
            version_id=fresh,
            call_no=1,
            provider="openrouter",
            model=pilot.MODEL,
            amount_usd=0.1,
            period_cap_usd=5,
            since=NOW - timedelta(days=30),
            now=NOW,
            expires_at=NOW,
            scope=scope,
        )
        if state == "abandoned":
            ss.abandon_run(env.conn, rid, now=NOW)
    scope = ss.PilotScope("policy-fedcba9876543210", max_attempts=4, max_usd=2)
    rid = ss.start_run(
        env.conn,
        provider="openrouter",
        model=pilot.MODEL,
        hosted=True,
        prompt_version="outlook-v6",
        processing_version="3b-1",
        limits={"experiment": scope.experiment},
        dry_run=False,
        now=NOW,
    )
    with pytest.raises(ss.AttemptConsumed):
        ss.reserve(
            env.conn,
            run_id=rid,
            version_id=equivalent,
            call_no=1,
            provider="openrouter",
            model=pilot.MODEL,
            amount_usd=0.1,
            period_cap_usd=5,
            since=NOW - timedelta(days=30),
            now=NOW,
            expires_at=NOW,
            scope=scope,
        )


@pytest.mark.parametrize("stage", ["provider_validation", "backup"])
@pytest.mark.parametrize("change", ["expired", "revoked"])
def test_policy_authority_is_rechecked_after_live_validation_and_backup(tmp_path, stage, change):
    env = Env(tmp_path)
    env.path = write_policy(
        env.data, policy_dict(env.reg, expires_at=(NOW + timedelta(seconds=1)).isoformat())
    )
    env.policy, env.sha = pol.load_policy(env.path, env.data)
    clock = [NOW]

    def withdraw():
        if change == "expired":
            clock[0] = env.policy.expires_at
        else:
            pol.record_event(env.conn, "revoked", env.policy, env.sha, operator="owner", now=NOW)

    original = env.respond

    def respond(req):
        response = original(req)
        if stage == "provider_validation" and req.url.path.endswith("zdr"):
            withdraw()
        return response

    def backup(conn, data_dir, output, now):
        pilot.verified_backup(conn, data_dir, output, now)
        if stage == "backup":
            withdraw()

    env.client = httpx.Client(transport=httpx.MockTransport(respond))
    with pytest.raises(pol.PolicyRefused):
        execute(env, now_fn=lambda: clock[0], backup_check=backup)
    assert env.posts == [] and env.attempts() == 0
    assert not [e for e in env.events() if e["event"] == "executed"]


def purge_in_flight(env):
    original = env.respond

    def respond(req):
        if req.method == "POST":
            artifacts = ArtifactStore(env.data / "raw")
            plan = purge.plan_purge(env.conn, "treasury", version_ids=(env.version,))
            purge.apply_purge(
                env.conn,
                plan,
                artifacts,
                reason="takedown",
                note="synthetic",
                purged_by="owner",
                now=NOW,
            )
        return original(req)

    env.client = httpx.Client(transport=httpx.MockTransport(respond))


def test_a_purged_in_flight_response_keeps_its_own_audit_and_settled_cost(tmp_path):
    env = Env(tmp_path, content=json.dumps(good_output(1)))
    purge_in_flight(env)
    outcome = env.go()
    assert outcome.outcome == "purged" and outcome.summary_id is None
    (reservation,) = env.conn.execute("SELECT * FROM research_llm_reservation").fetchall()
    (event,) = env.events()
    assert len(env.posts) == 1 and reservation["state"] == "settled"
    assert event["event"] == "executed" and event["outcome"] == "purged"
    assert event["run_id"] == reservation["run_id"]
    assert event["cost_usd"] == outcome.cost_usd == reservation["actual_usd"] > 0
    assert event["reserved_usd"] == reservation["reserved_usd"]
    assert env.conn.execute("SELECT COUNT(*) FROM research_summary").fetchone()[0] == 0
    assert pol.policy_usage(env.conn, env.sha) == (1, outcome.cost_usd)


def test_purge_cli_reports_consumed_request_and_no_retained_output(tmp_path, monkeypatch, capsys):
    env = Env(tmp_path)
    purge_in_flight(env)
    real = run.execute_policy

    def mocked_execute(*args, **kwargs):
        kwargs.update(
            client=env.client,
            now_fn=lambda: NOW,
            interactive=True,
            ask=lambda _: env.pre().confirm_code,
        )
        return real(*args, **kwargs)

    monkeypatch.setattr(run, "execute_policy", mocked_execute)
    monkeypatch.setenv("NZSTATS_LLM_API_KEY", KEY)
    settings = SimpleNamespace(data_dir=env.data, db_path=env.data / "nzstats.db")
    args = SimpleNamespace(
        policy=str(env.path),
        version=env.version,
        sections=None,
        dry_run=False,
        confirm=env.pre().confirm_code,
    )
    assert policy_cli.run_policy(args, settings, env.reg) == 0
    text = capsys.readouterr().out
    assert "purged" in text and "One request" in text
    assert "Nothing was requested" not in text
    assert "No output was retained" in text


def test_exception_before_own_run_never_audits_a_rivals_reservation(tmp_path):
    env = Env(tmp_path)
    rival = []

    def backup(conn, data_dir, output, now):
        rival.append(env.go())
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        execute(env, now_fn=lambda: NOW, backup_check=backup)
    assert len(env.posts) == 1 and len(rival) == 1
    assert [e["event"] for e in env.events()] == ["executed", "refused"]
    assert env.events()[-1]["refusal_code"] == "execution_failed"


@pytest.mark.parametrize("remaining", [timedelta(seconds=1), timedelta(hours=2)])
def test_generated_approval_never_outlives_policy_or_one_hour(tmp_path, remaining):
    env = Env(tmp_path)
    policy = env.policy.model_copy(update={"expires_at": NOW + remaining})
    plan = run.plan_for(policy, env.sha, env.version)
    manifest = pilot.freeze(
        env.conn, env.reg, {env.version: env.pre().ordinals}, env.data / "freeze", plan
    )
    approval = run._approval(
        policy, env.sha, plan, env.pre(), manifest["documents"][0], env.data / "freeze", NOW
    )
    assert approval.expires_at == min(NOW + timedelta(hours=1), policy.expires_at)


@pytest.mark.parametrize("change", ["expired", "revoked"])
def test_authority_lost_after_reservation_prevents_transmission_and_audits_zero_cost(
    tmp_path, monkeypatch, change
):
    env = Env(tmp_path)
    clock = [NOW]
    original = ss.reserve

    def reserve(*args, **kwargs):
        held = original(*args, **kwargs)
        assert held is not None
        if change == "expired":
            clock[0] = env.policy.expires_at
        else:
            pol.record_event(env.conn, "revoked", env.policy, env.sha, operator="owner", now=NOW)
        return held

    monkeypatch.setattr(ss, "reserve", reserve)
    result = execute(env, now_fn=lambda: clock[0])
    assert not env.posts and env.attempts() == 1
    event = next(e for e in env.events() if e["event"] == "executed")
    assert result.outcome == "provider_error" and event["cost_usd"] == result.cost_usd == 0


def test_failure_writing_result_still_audits_own_completed_request(tmp_path, monkeypatch):
    env = Env(tmp_path)
    original = pilot._write

    def write(path, body):
        if path.name == "result.json":
            raise OSError("synthetic result write failure")
        original(path, body)

    monkeypatch.setattr(pilot, "_write", write)
    with pytest.raises(OSError):
        env.go()
    (event,) = env.events()
    assert len(env.posts) == env.attempts() == 1 and event["event"] == "executed"
    assert event["cost_usd"] == ss.lifetime_spent(env.conn) > 0


def test_historical_expenditure_and_legacy_second_attempt_remain_authoritative(tmp_path):
    env = Env(tmp_path)
    versions = [
        seed_version(env.conn, sections=(f"history {i}",), key="treasury", doc=f"history{i}")
        for i in range(3)
    ]
    for version, scope, cost in (
        (versions[0], None, 0.2),
        (versions[0], "phase-4n-second-pilot", 0.182278204),
        (versions[1], "phase-4n-second-pilot", 0.126184608),
        (versions[2], "phase-4s-treasury-v3", 0.118247976),
    ):
        spend(env.conn, version, scope, cost=cost)
    before = [
        tuple(r) for r in env.conn.execute("SELECT * FROM research_llm_reservation ORDER BY id")
    ]
    assert ss.lifetime_spent(env.conn) == pytest.approx(0.6267107880)
    assert ss.openrouter_refusal(env.conn, env.version, 0.1) == "lifetime_attempts_exhausted"
    result = env.go()
    after = [
        tuple(r) for r in env.conn.execute("SELECT * FROM research_llm_reservation ORDER BY id")
    ]
    assert after[:4] == before and len(after) == 5
    assert ss.lifetime_spent(env.conn) == pytest.approx(0.6267107880 + result.cost_usd)


@pytest.mark.parametrize("change", ["expired", "revoked"])
def test_authority_is_checked_inside_reservation_transaction(tmp_path, monkeypatch, change):
    env = Env(tmp_path)
    clock = [NOW]
    original = ss.reserve

    def reserve(*args, **kwargs):
        # All earlier checks passed. Simulate authority lost while waiting to acquire the write lock.
        if change == "expired":
            clock[0] = env.policy.expires_at
        else:
            pol.record_event(env.conn, "revoked", env.policy, env.sha, operator="owner", now=NOW)
        return original(*args, **kwargs)

    monkeypatch.setattr(ss, "reserve", reserve)
    with pytest.raises(pol.PolicyRefused):
        execute(env, now_fn=lambda: clock[0])
    assert not env.posts and env.attempts() == 0
    assert env.events()[-1]["event"] == "refused"
    assert env.events()[-1]["refusal_code"] == "consent_refused"


@pytest.mark.parametrize("delta", [timedelta(microseconds=-1), timedelta(microseconds=1)])
def test_execution_at_policy_expiry_boundary(tmp_path, delta):
    env = Env(tmp_path)
    env.path = write_policy(
        env.data, policy_dict(env.reg, expires_at=(NOW + timedelta(seconds=1)).isoformat())
    )
    env.policy, env.sha = pol.load_policy(env.path, env.data)
    clock = [NOW]

    def backup(conn, data_dir, output, now):
        pilot.verified_backup(conn, data_dir, output, now)
        clock[0] = env.policy.expires_at + delta

    if delta < timedelta(0):
        execute(env, now_fn=lambda: clock[0], backup_check=backup)
        assert len(env.posts) == env.attempts() == 1
    else:
        with pytest.raises(pol.PolicyRefused):
            execute(env, now_fn=lambda: clock[0], backup_check=backup)
        assert not env.posts and env.attempts() == 0
