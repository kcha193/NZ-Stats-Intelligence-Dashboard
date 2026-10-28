"""Concurrency-safe model spending (Phase 3F): reservations, interrupted calls and failure injection.

Every call reserves its worst-case cost in the shared database before the provider is contacted, so two
processes cannot both spend the same remainder of the rolling cap. A reservation is settled to the actual
cost as soon as the call returns; one that never settles (the process died, the call was interrupted) keeps
counting at its worst case: an unrecorded outcome is treated as spent, never as free.
"""

import sqlite3
import subprocess
import sys
import textwrap
import threading
from datetime import timedelta
from pathlib import Path

import pytest

from nzstats.research import summary_store as ss
from nzstats.research.contract import LlmLimits, ProviderError
from nzstats.research.providers import FakeProvider, Pricing
from nzstats.research.summarise import summarise_versions
from nzstats.store.db import connect

from .llm_support import NOW, draft_json, seed_version
from .support import institution

PRICING = Pricing(4.0, 20.0)
USAGE = (10_000, 4_000)
ONE_CALL = PRICING.cost(*USAGE)


def registry():
    return {
        "example": institution("example", llm_processing="hosted", llm_processing_note="synthetic")
    }


def run(conn, provider, *, now=NOW, **kw):
    kw.setdefault("limits", LlmLimits(max_run_usd=5.0, max_period_usd=10.0))
    return summarise_versions(conn, registry(), provider, pricing=PRICING, sleep=lambda s: None,
                              now_fn=lambda: now, **kw)  # fmt: skip


def fake(**kw):
    return FakeProvider(lambda req: draft_json(req.version_id), usage=USAGE, **kw)


def reservations(conn):
    return conn.execute("SELECT * FROM research_llm_reservation ORDER BY id").fetchall()


def window(conn, now=NOW):
    return ss.spent_since(conn, now - timedelta(days=30))


def test_each_call_is_reserved_then_settled_to_its_actual_cost(conn):
    seed_version(conn)
    result = run(conn, fake())
    (r,) = reservations(conn)
    assert (r["state"], r["settle_basis"], r["call_no"]) == ("settled", "reported", 1)
    assert r["actual_usd"] == pytest.approx(ONE_CALL) and r["reserved_usd"] > 0
    assert r["run_id"] == result.run_id and r["closed_at"]
    # The window counts the settled cost once, not the reservation and the usage rows both.
    assert window(conn) == pytest.approx(ONE_CALL)


def test_a_failure_the_provider_did_not_bill_settles_at_zero(conn):
    seed_version(conn)
    run(conn, fake(fail_first=[ProviderError("auth_error", retryable=False)]))
    (r,) = reservations(conn)
    assert (r["state"], r["settle_basis"], r["actual_usd"]) == ("settled", "not_billed", 0)
    assert window(conn) == 0


def test_a_failure_without_reported_usage_settles_at_the_worst_case(conn):
    seed_version(conn)
    run(conn, fake(fail_first=[ProviderError("timeout", retryable=False)]))
    (r,) = reservations(conn)
    assert (r["settle_basis"], r["actual_usd"]) == ("worst_case", r["reserved_usd"])
    assert window(conn) == pytest.approx(r["reserved_usd"])


def test_a_run_over_the_cap_makes_no_call_and_leaves_no_reservation(conn):
    seed_version(conn)
    provider = fake()
    result = run(conn, provider, limits=LlmLimits(max_run_usd=5.0, max_period_usd=0.0001))
    assert [i.outcome for i in result.items] == ["budget_exhausted"] and provider.calls == []
    assert reservations(conn) == []


def test_a_concurrent_run_sees_the_reservation_another_process_holds(tmp_path):
    """Two runs start together with room for one call: only one may spend it (the Phase 3E residual risk)."""
    path = tmp_path / "shared.db"
    first = connect(path)
    from nzstats.store.db import migrate

    migrate(first)
    seed_version(first, doc="a")
    seed_version(first, doc="b")
    second = connect(path)
    worst = run(first, fake(), dry_run=True).items[0].estimated_usd
    limits = LlmLimits(
        max_run_usd=5.0, max_period_usd=worst * 1.5
    )  # room for one reservation, not two
    entered, release = threading.Event(), threading.Event()

    def slow(req):
        entered.set()
        assert release.wait(10)
        return draft_json(req.version_id)

    slow_provider = FakeProvider(slow, usage=USAGE)
    outcome: dict = {}
    worker = threading.Thread(
        target=lambda: outcome.update(first=run(first, slow_provider, limits=limits, limit=1))
    )
    worker.start()
    assert entered.wait(10)  # the first run is inside its call, holding its reservation
    other = fake()
    refused = run(second, other, limits=limits)
    release.set()
    worker.join(10)
    assert other.calls == [], "the second run spent budget the first run had already reserved"
    assert "budget_exhausted" in [i.outcome for i in refused.items]
    assert [i.outcome for i in outcome["first"].items] == ["verified"]
    assert window(first) == pytest.approx(ONE_CALL)  # one call's cost, never two


def test_an_interrupted_call_is_abandoned_at_its_worst_case_and_keeps_counting(conn):
    seed_version(conn)

    def interrupted(req):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run(conn, FakeProvider(interrupted, usage=USAGE))
    (r,) = reservations(conn)
    assert (r["state"], r["settle_basis"], r["actual_usd"]) == ("abandoned", "interrupted", None)
    assert r["reserved_usd"] > 0 and r["closed_at"]
    assert window(conn) == pytest.approx(r["reserved_usd"])
    run_row = conn.execute("SELECT outcome, spent_usd FROM research_llm_run").fetchone()
    assert run_row["outcome"] == "aborted"
    assert run_row["spent_usd"] == pytest.approx(r["reserved_usd"])
    # The next run cannot spend what the interrupted call may already have cost.
    provider = fake()
    result = run(
        conn, provider, limits=LlmLimits(max_run_usd=5.0, max_period_usd=r["reserved_usd"])
    )
    assert provider.calls == [] and [i.outcome for i in result.items] == ["budget_exhausted"]


def test_a_failure_storing_the_result_keeps_the_actual_spend(conn, monkeypatch):
    seed_version(conn)

    def broken(*a, **kw):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(ss, "insert_summary", broken)
    with pytest.raises(sqlite3.OperationalError):
        run(conn, fake())
    (r,) = reservations(conn)
    # The response arrived, so the cost is known and settled before anything was stored.
    assert (r["state"], r["settle_basis"]) == ("settled", "reported")
    assert r["actual_usd"] == pytest.approx(ONE_CALL)
    assert conn.execute("SELECT COUNT(*) FROM research_summary").fetchone()[0] == 0
    assert window(conn) == pytest.approx(ONE_CALL)


def test_a_process_killed_mid_call_leaves_a_held_reservation_that_counts(tmp_path):
    db = tmp_path / "killed.db"
    conn = connect(db)
    from nzstats.store.db import migrate

    migrate(conn)
    seed_version(conn)
    child = textwrap.dedent(
        """
        import os, sys
        from datetime import UTC, datetime
        from nzstats.research.contract import LlmLimits
        from nzstats.research.providers import FakeProvider, Pricing
        from nzstats.research.summarise import summarise_versions
        from nzstats.store.db import connect
        sys.path.insert(0, sys.argv[2])
        from tests.research.support import institution

        def die(req):
            os._exit(9)  # no cleanup, no exception handler, no finally

        reg = {"example": institution("example", llm_processing="hosted", llm_processing_note="x")}
        summarise_versions(connect(sys.argv[1]), reg, FakeProvider(die, usage=(10000, 4000)),
                           pricing=Pricing(4.0, 20.0), limits=LlmLimits(max_run_usd=5.0, max_period_usd=10.0),
                           now_fn=lambda: datetime(2026, 10, 26, 1, 0, tzinfo=UTC))
        """
    )
    backend = str(Path(__file__).resolve().parents[2])
    proc = subprocess.run(
        [sys.executable, "-c", child, str(db), backend], capture_output=True, timeout=60
    )
    assert proc.returncode == 9, proc.stderr.decode()[-500:]
    (r,) = reservations(conn)
    assert (r["state"], r["actual_usd"], r["closed_at"]) == ("held", None, None)
    assert window(conn) == pytest.approx(r["reserved_usd"]) and r["reserved_usd"] > 0
    # A later run that finds it older than any live call could be abandons it, still at the worst case.
    later = NOW + timedelta(hours=1)
    provider = fake()
    run(
        conn,
        provider,
        now=later,
        limits=LlmLimits(max_run_usd=5.0, max_period_usd=r["reserved_usd"]),
    )
    (r2, *_) = reservations(conn)
    assert (r2["state"], r2["settle_basis"]) == ("abandoned", "interrupted")
    assert provider.calls == []


def test_a_young_held_reservation_is_not_abandoned_under_a_live_call(conn):
    seed_version(conn)
    conn.execute("INSERT INTO research_llm_run(provider, model, hosted, prompt_version, processing_version,"
                 " started_at) VALUES ('fake','m',0,'p','v',?)", ("2026-10-26T00:59:30Z",))  # fmt: skip
    conn.execute(
        "INSERT INTO research_llm_reservation(run_id, version_id, call_no, provider, model,"
        " reserved_usd, created_at, expires_at) VALUES (1,1,1,'fake','m',0.5,'2026-10-26T00:59:30Z','2026-10-26T01:07:30Z')"
    )
    run(conn, fake(), limits=LlmLimits(max_run_usd=5.0, max_period_usd=10.0))
    assert reservations(conn)[0]["state"] == "held"


def test_reservations_are_append_only_and_only_move_forward(conn):
    seed_version(conn)
    run(conn, fake())
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("DELETE FROM research_llm_reservation")
    with pytest.raises(sqlite3.DatabaseError, match="immutable|closed"):
        conn.execute("UPDATE research_llm_reservation SET reserved_usd = 0")
    with pytest.raises(sqlite3.DatabaseError, match="closed"):
        conn.execute("UPDATE research_llm_reservation SET state = 'abandoned', actual_usd = NULL")
    with pytest.raises(sqlite3.DatabaseError, match="closed"):
        conn.execute("UPDATE research_llm_reservation SET actual_usd = 0")


def test_runs_before_reservations_existed_still_count_as_before(conn):
    seed_version(conn)
    run_id = ss.start_run(conn, provider="fake", model="m", hosted=False, prompt_version="p",
                          processing_version="3b-1", limits={}, dry_run=False, now=NOW - timedelta(days=1))  # fmt: skip
    ss.finish_run(conn, run_id, outcome="ok", counts={}, spent_usd=2.5, now=NOW - timedelta(days=1))
    assert window(conn) == pytest.approx(2.5)
    run(conn, fake())
    assert window(conn) == pytest.approx(2.5 + ONE_CALL)


def test_a_run_with_a_shorter_timeout_does_not_abandon_another_runs_live_call(conn):
    """Each reservation carries the deadline its own process set; another process's settings never shorten it."""
    seed_version(conn)
    ss.start_run(conn, provider="fake", model="m", hosted=False, prompt_version="p", processing_version="v",
                 limits={}, dry_run=False, now=NOW)  # fmt: skip
    rid = ss.reserve(conn, run_id=1, version_id=1, call_no=1, provider="fake", model="m", amount_usd=0.1,
                     period_cap_usd=10, since=NOW - timedelta(days=30), now=NOW,
                     expires_at=NOW + timedelta(hours=1))  # fmt: skip
    short = LlmLimits(max_run_usd=5.0, max_period_usd=10.0, timeout_seconds=1.0, max_retries=0)
    run(conn, fake(), now=NOW + timedelta(minutes=30), limits=short)
    assert reservations(conn)[0]["state"] == "held"  # its own process allowed an hour
    ss.settle(conn, rid, actual_usd=0.05, basis="reported", now=NOW + timedelta(minutes=31))
    assert reservations(conn)[0]["state"] == "settled"
    run(conn, fake(), now=NOW + timedelta(hours=3), limits=short)


def test_settling_a_reservation_already_abandoned_is_a_no_op_not_an_error(conn):
    seed_version(conn)
    ss.start_run(conn, provider="fake", model="m", hosted=False, prompt_version="p", processing_version="v",
                 limits={}, dry_run=False, now=NOW)  # fmt: skip
    rid = ss.reserve(conn, run_id=1, version_id=1, call_no=1, provider="fake", model="m", amount_usd=0.1,
                     period_cap_usd=10, since=NOW - timedelta(days=30), now=NOW, expires_at=NOW + timedelta(seconds=5))  # fmt: skip
    ss.abandon_stale(conn, now=NOW + timedelta(minutes=5))
    ss.settle(conn, rid, actual_usd=0.01, basis="reported", now=NOW + timedelta(minutes=6))
    row = reservations(conn)[0]
    assert (row["state"], row["actual_usd"]) == ("abandoned", None) and window(
        conn, NOW
    ) == pytest.approx(0.1)
