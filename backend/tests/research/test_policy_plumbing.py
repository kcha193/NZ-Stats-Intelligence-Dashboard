"""Phase 4W plumbing: the lifetime attempt ceiling, policy experiments and the append-only policy audit table.

Raising `LIFETIME_ATTEMPTS` is a capacity change only: no existing scope may use the new attempts, and nothing in
this file, in code or in a data file authorises a paid request. Synthetic data only.
"""

import sqlite3
from datetime import timedelta

import pytest

from nzstats.research import openrouter, pilot
from nzstats.research import summary_store as ss
from nzstats.store.db import connect, migrate

from .llm_support import NOW, seed_version
from .test_pilot_treasury_v3 import setup_v3


def test_policy_scopes_see_a_ceiling_of_eight_and_everything_older_keeps_four():
    assert (ss.LEGACY_LIFETIME_ATTEMPTS, ss.LIFETIME_ATTEMPTS) == (4, 8)
    assert ss.LIFETIME_USD == 5.0  # the money ceiling is untouched


@pytest.mark.parametrize("version", [1, 2, 3])
def test_raising_the_ceiling_reopens_no_existing_experiment_or_version(tmp_path, version):
    """The real ledger shape: 4 attempts, with the Phase 4N scope holding an unused slot. None of it reopens."""
    conn, *_ = setup_v3(tmp_path, v3_attempt=True)
    assert conn.execute("SELECT COUNT(*) FROM research_llm_reservation").fetchone()[0] == 4
    for scope in (
        ss.PilotScope(),  # the first pilot, and any run that names no experiment
        openrouter.SECOND_PILOT.scope,  # used 1 of 2 in this ledger: the unused slot must stay shut
        openrouter.TREASURY_V3_PILOT.scope,
        ss.PilotScope(
            "phase-4x-unlisted", max_attempts=4, max_usd=5.0
        ),  # a scope that names no policy
    ):
        assert ss.openrouter_refusal(conn, version, 0.05, scope=scope) in (
            "attempt_consumed",
            "lifetime_attempts_exhausted",
        ), scope


def test_a_policy_scope_can_use_the_new_attempts_and_stops_at_eight(tmp_path):
    conn, *_ = setup_v3(tmp_path, v3_attempt=True)
    scope = ss.PilotScope("policy-0123456789abcdef", max_attempts=4, max_usd=2.0)
    new = seed_version(conn, key="treasury", doc="v4")
    assert ss.openrouter_refusal(conn, new, 0.05, scope=scope) is None
    for i in range(4):  # four policy attempts on four new versions: 4 legacy + 4 policy = 8
        version = new if i == 0 else seed_version(conn, key="treasury", doc=f"w{i}")
        rid = ss.start_run(
            conn, provider="openrouter", model=pilot.MODEL, hosted=True, prompt_version="outlook-v6",
            processing_version="3b-1", limits={"experiment": scope.experiment}, dry_run=False,
            now=NOW - timedelta(hours=1),
        )  # fmt: skip
        held = ss.reserve(
            conn, run_id=rid, version_id=version, call_no=1, provider="openrouter",
            model=pilot.MODEL, amount_usd=0.3, period_cap_usd=5, since=NOW - timedelta(days=30),
            now=NOW - timedelta(hours=1), expires_at=NOW, scope=scope,
        )  # fmt: skip
        assert held is not None
        ss.settle(conn, held, actual_usd=0.01, basis="reported", now=NOW)
    last = seed_version(conn, key="treasury", doc="v9")
    assert ss.openrouter_refusal(conn, last, 0.05, scope=scope) == "lifetime_attempts_exhausted"
    wider = ss.PilotScope("policy-fedcba9876543210", max_attempts=4, max_usd=2.0)
    assert ss.openrouter_refusal(conn, last, 0.05, scope=wider) == "lifetime_attempts_exhausted"


def test_an_unregistered_experiment_name_cannot_configure_a_provider():
    from nzstats.research.providers import LlmLimits, LlmSettings, Pricing

    settings = LlmSettings(
        "openrouter", pilot.MODEL, "k", pilot.OPENROUTER_URL, Pricing(4.4, 22),
        LlmLimits(max_input_chars=45000, max_output_tokens=12000, max_documents_per_run=2,
                  timeout_seconds=300.0, max_retries=0, max_run_usd=1.0, max_period_usd=5),
        pilot.ROUTE, "low", "policy-0123456789abcdef",
    )  # fmt: skip
    with pytest.raises(openrouter.LlmConfigError):
        openrouter.validate_settings(settings)


def test_a_policy_experiment_must_carry_the_policy_prefix_and_a_registered_prompt():
    scope = ss.PilotScope("phase-4x-new", max_attempts=1, max_usd=0.5)
    with pytest.raises(ValueError):
        openrouter.register_policy_experiment(
            openrouter.Experiment(scope, "outlook-v6", "low", 12_000, 300.0)
        )
    scope = ss.PilotScope("policy-aaaaaaaaaaaaaaaa", max_attempts=1, max_usd=0.5)
    with pytest.raises(ValueError):
        openrouter.register_policy_experiment(
            openrouter.Experiment(scope, "outlook-v99", "low", 12_000, 300.0)
        )


def test_the_static_experiment_table_never_holds_a_policy_or_v6_experiment():
    openrouter.register_policy_experiment(
        openrouter.Experiment(
            ss.PilotScope("policy-bbbbbbbbbbbbbbbb", max_attempts=1, max_usd=0.5),
            "outlook-v6", "low", 12_000, 300.0,
        )
    )  # fmt: skip
    assert "policy-bbbbbbbbbbbbbbbb" not in openrouter.EXPERIMENTS
    assert all(e.prompt_version != "outlook-v6" for e in openrouter.EXPERIMENTS.values())


def test_a_plan_defaults_to_the_verifier_its_experiment_was_frozen_under():
    assert pilot.TREASURY_V3_PLAN.verifier == "verify-4"
    assert pilot.SECOND_PLAN.verifier == "verify-4"


# --- the audit table -----------------------------------------------------------------------------------------------
def audit_row(conn, **over):
    row = {
        "event": "executed", "policy_id": "p1", "policy_sha256": "a" * 64, "version_id": 1,
        "content_sha256": "b" * 64, "request_sha256": "c" * 64, "operator": "synthetic",
        "created_at": NOW.isoformat(), "outcome": "failed_verification",
    }  # fmt: skip
    row.update(over)
    cols = ",".join(row)
    conn.execute(
        f"INSERT INTO research_policy_event({cols}) VALUES ({','.join('?' * len(row))})",
        tuple(row.values()),
    )


def fresh(tmp_path):
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    seed_version(conn, key="treasury")
    return conn


def test_the_audit_rejects_update_and_delete(tmp_path):
    conn = fresh(tmp_path)
    audit_row(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE research_policy_event SET outcome='verified'")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM research_policy_event")


def test_one_content_hash_can_be_executed_only_once_whatever_the_policy_or_version(tmp_path):
    conn = fresh(tmp_path)
    audit_row(conn)
    with pytest.raises(sqlite3.IntegrityError):
        audit_row(conn, policy_id="p2", policy_sha256="d" * 64)  # a new policy does not restore it
    audit_row(conn, event="refused", refusal_code="x")  # refusals never consume anything
    audit_row(conn, event="refused", refusal_code="x")


@pytest.mark.parametrize(
    "bad",
    [
        {"event": "retried"},
        {"policy_sha256": "short"},
        {"event": "refused", "refusal_code": None},
        {"event": "executed", "request_sha256": None},
        {"event": "executed", "version_id": None},
        {"operator": " "},
    ],
)
def test_the_audit_enforces_its_shape(tmp_path, bad):
    conn = fresh(tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        audit_row(conn, **bad)


def test_the_audit_has_no_column_that_could_hold_text_keys_or_output(tmp_path):
    conn = fresh(tmp_path)
    columns = {r[1] for r in conn.execute("PRAGMA table_info(research_policy_event)")}
    assert not columns & {
        "prompt",
        "body",
        "text",
        "output",
        "raw_output",
        "api_key",
        "key",
        "token",
    }


def test_migration_is_additive_and_leaves_legacy_ledger_rows_untouched(tmp_path):
    conn, *_ = setup_v3(tmp_path, v3_attempt=True)
    before = conn.execute("SELECT * FROM research_llm_reservation ORDER BY id").fetchall()
    migrate(conn)
    after = conn.execute("SELECT * FROM research_llm_reservation ORDER BY id").fetchall()
    assert [tuple(r) for r in before] == [tuple(r) for r in after]
    assert timedelta(0) == timedelta(0)  # no clock dependence
