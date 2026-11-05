"""The read-only key reading (Phase 4R). SYNTHETIC FIXTURE: a mock transport, an invented key and invented spend."""

import httpx
import pytest

from nzstats.research.key_reading import read_key
from nzstats.research.pilot import PilotRefused
from nzstats.research.summary_store import LIFETIME_ATTEMPTS
from nzstats.store.db import transaction

from .llm_support import seed_version

KEY = "sk-or-SYNTHETIC-not-a-real-key"


def _client(payload, status=200, seen=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append((request.method, request.url.path, request.headers.get("authorization")))
        return httpx.Response(status, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _spend(conn, version, usd):
    with transaction(conn):
        run = conn.execute(
            "INSERT INTO research_llm_run(provider, model, hosted, prompt_version, processing_version, limits, dry_run,"
            " started_at, outcome, counts, spent_usd) VALUES ('openrouter','m',1,'p','x','{}',0,'2026-11-01T00:00:00Z','ok','{}',?)",
            (usd,),
        ).lastrowid
        conn.execute(
            "INSERT INTO research_llm_reservation(run_id, version_id, call_no, provider, model, reserved_usd, state, actual_usd,"
            " settle_basis, created_at, expires_at, closed_at) VALUES (?,?,1,'openrouter','m',?, 'settled', ?, 'reported',"
            " '2026-11-01T00:00:00Z','2026-11-02T00:00:00Z','2026-11-01T00:00:00Z')",
            (run, version, usd, usd),
        )


def _meta(usage, limit=5, byok=0):
    return {"data": {"usage": usage, "limit": limit, "limit_remaining": limit - usage, "byok_usage": byok,
                     "limit_reset": None, "is_management_key": False}}  # fmt: skip


@pytest.fixture()
def spent(conn):
    version = seed_version(conn)
    _spend(conn, version, 0.5)
    return conn


def test_a_matching_key_reports_consistent_numbers_and_one_read_only_get(spent):
    seen = []
    reading = read_key(_client(_meta(0.5), seen=seen), KEY, spent)
    assert seen == [("GET", "/api/v1/key", f"Bearer {KEY}")]
    assert (
        reading["usage_matches_ledger"]
        and reading["byok_is_zero"]
        and reading["remaining_is_consistent"]
    )
    assert reading["limit_is_lifetime_cap"] and reading["attempts_left"] == LIFETIME_ATTEMPTS - 1


def test_the_key_never_appears_in_the_reading(spent):
    assert KEY not in repr(read_key(_client(_meta(0.5)), KEY, spent))


def test_spend_the_ledger_never_recorded_is_flagged(spent):
    reading = read_key(_client(_meta(0.9)), KEY, spent)
    assert reading["usage_matches_ledger"] is False


def test_bring_your_own_key_spend_is_flagged(spent):
    assert read_key(_client(_meta(0.5, byok=0.2)), KEY, spent)["byok_is_zero"] is False


@pytest.mark.parametrize(
    "payload", [{}, {"data": []}, {"data": {"usage": "x"}}, {"data": {"usage": float("nan")}}]
)
def test_a_malformed_answer_is_refused_without_repeating_it(spent, payload):
    with pytest.raises(PilotRefused) as exc:
        read_key(_client(payload), KEY, spent)
    assert KEY not in str(exc.value)


def test_a_refused_request_and_a_missing_key_are_refused(spent):
    with pytest.raises(PilotRefused):
        read_key(_client({"error": "SECRET-SERVER-TEXT"}, status=401), KEY, spent)
    with pytest.raises(PilotRefused):
        read_key(_client(_meta(0.5)), "", spent)
