"""Phase 4T: an internal-draft authorisation runs the Treasury version 3 experiment without human gold.

Processing consent stays mandatory and exact: document scope, source rights, provider, privacy settings, request hash,
expiry and spend limit. Gold becomes an optional evaluation, and a run without it is recorded as not evaluated, never
as passed. Synthetic text and a mocked OpenRouter only.
"""

import hashlib
import json
from datetime import timedelta

import httpx
import pytest
from pydantic import ValidationError

from nzstats.research import pilot
from nzstats.research import summary_store as ss
from nzstats.research.drafts import DraftAllowlist, draft_summaries

from .llm_support import NOW
from .test_openrouter import envelope
from .test_pilot import remote
from .test_pilot_treasury_v3 import EXPERIMENT, attempt, lifetime_attempts, setup_v3, spend

SECRET = "synthetic-secret"


def internal(frozen, **changes):
    manifest = json.loads((frozen / "freeze.json").read_bytes())
    (doc,) = manifest["documents"]
    data = {
        "state": "authorised",
        "purpose": "internal_draft",
        "experiment": EXPERIMENT,
        "experiment_spend_limit_usd": 0.5,
        "approved_by": "Synthetic Owner",
        "approved_at": NOW.isoformat(),
        "expires_at": (NOW + timedelta(hours=1)).isoformat(),
        "frozen_sha256": pilot.file_sha256(frozen / "freeze.json"),
        "model": pilot.MODEL,
        "provider_id": pilot.ROUTE,
        "privacy": {"zdr": True, "data_collection": "deny", "allow_fallbacks": False,
                    "require_parameters": True},
        "provider_review": "Synthetic acceptance of the exact route",
        "account_controls_evidence": "Synthetic signed account review",
        "dedicated_key_confirmed": True,
        "documents": [{
            "version_id": 3,
            "request_sha256": doc["request_sha256"],
            "body_sha256": doc["body_sha256"],
            "sections": [{"ordinal": 1, "rights_basis": "Synthetic owner-authored text",
                          "third_party_rights": "None in this synthetic section",
                          "attribution": "Synthetic owner; AI interpretation labelled"}],
        }],
    }  # fmt: skip
    data.update(changes)
    return pilot.load_approval(json.dumps(data).encode())


def fixture(tmp_path, *, content=None, **kwargs):
    conn, reg, data, frozen, _legacy, posts, _ = setup_v3(tmp_path, **kwargs)

    def respond(req):
        if req.url.path == "/api/v1/key":
            used = ss.lifetime_spent(conn)
            return httpx.Response(200, json={"data": {
                "limit": 5, "limit_reset": None, "limit_remaining": 5 - used, "usage": used,
                "byok_usage": 0, "is_management_key": False}})  # fmt: skip
        if req.method == "POST" and content is not None:
            posts.append(req)
            choice = {"message": {"content": content}, "finish_reason": "stop"}
            return httpx.Response(200, json=envelope(choices=[choice]))
        return remote(req, posts)

    return conn, reg, data, frozen, posts, httpx.Client(transport=httpx.MockTransport(respond))


def test_missing_human_gold_does_not_block_an_authorised_internal_draft_run(tmp_path):
    conn, reg, data, frozen, posts, client = fixture(tmp_path)
    (data / "gold.json").unlink()  # no gold anywhere
    approval = internal(frozen)
    assert approval.evaluation is None
    attempt(conn, reg, data, frozen, approval, client)
    assert len(posts) == 1 and posts[0].content == (frozen / "v3-request.json").read_bytes()
    record = json.loads((data / "run" / "evaluation.json").read_bytes())
    assert record == {"human_evaluation": "not_evaluated", "gold_sha256": None}
    assert lifetime_attempts(conn) == 4


def test_an_optional_gold_file_is_still_bound_when_named(tmp_path):
    conn, reg, data, frozen, posts, client = fixture(tmp_path)
    gold = data / "gold.json"
    good = {
        "gold_path": str(gold),
        "gold_sha256": pilot.file_sha256(gold),
        "gold_review": "Synthetic",
    }
    with pytest.raises(pilot.PilotRefused):
        attempt(
            conn,
            reg,
            data,
            frozen,
            internal(frozen, evaluation={**good, "gold_sha256": "0" * 64}),
            client,
        )
    assert not posts
    attempt(conn, reg, data, frozen, internal(frozen, evaluation=good), client)
    record = json.loads((data / "run" / "evaluation.json").read_bytes())
    assert record == {
        "human_evaluation": "gold_bound_not_yet_scored",
        "gold_sha256": good["gold_sha256"],
    }


@pytest.mark.parametrize(
    "missing",
    ["documents", "provider_review", "account_controls_evidence", "dedicated_key_confirmed", "privacy",
     "frozen_sha256", "expires_at", "experiment_spend_limit_usd", "approved_by"],
)  # fmt: skip
def test_missing_source_processing_consent_still_blocks_inference(tmp_path, missing):
    conn, reg, data, frozen, posts, client = fixture(tmp_path)
    data_ = json.loads(internal(frozen).model_dump_json())
    del data_[missing]
    with pytest.raises(ValidationError):
        pilot.load_approval(json.dumps(data_).encode())
    assert not posts


@pytest.mark.parametrize(
    "change",
    [
        {"dedicated_key_confirmed": False},
        {
            "privacy": {
                "zdr": False,
                "data_collection": "deny",
                "allow_fallbacks": False,
                "require_parameters": True,
            }
        },
        {
            "privacy": {
                "zdr": True,
                "data_collection": "allow",
                "allow_fallbacks": False,
                "require_parameters": True,
            }
        },
        {
            "privacy": {
                "zdr": True,
                "data_collection": "deny",
                "allow_fallbacks": True,
                "require_parameters": True,
            }
        },
        {"model": "openai/gpt-5.6-sol"},
        {"provider_id": "azure/eu"},
        {"state": "approved"},
        {"purpose": "publication"},
        {"documents": []},
    ],
)
def test_an_authorisation_that_weakens_provider_or_privacy_terms_is_invalid(tmp_path, change):
    conn, reg, data, frozen, posts, client = fixture(tmp_path)
    with pytest.raises((ValidationError, pilot.PilotRefused)):
        attempt(conn, reg, data, frozen, internal(frozen, **change), client)
    assert not posts


def _doc(frozen, **changes):
    (doc,) = json.loads(internal(frozen).model_dump_json())["documents"]
    return [{**doc, **changes}]


@pytest.mark.parametrize(
    "change",
    [
        lambda f: {"documents": _doc(f, request_sha256="0" * 64)},
        lambda f: {"documents": _doc(f, body_sha256="0" * 64)},
        lambda f: {"documents": _doc(f, version_id=1)},
        lambda f: {
            "documents": _doc(
                f,
                sections=[
                    {
                        "ordinal": 0,
                        "rights_basis": "x",
                        "third_party_rights": "x",
                        "attribution": "x",
                    }
                ],
            )
        },
        lambda f: {"frozen_sha256": "0" * 64},
        lambda f: {"expires_at": (NOW + timedelta(days=2)).isoformat()},  # longer than a day
        lambda f: {"expires_at": (NOW - timedelta(minutes=1)).isoformat()},  # expired
        lambda f: {"approved_at": (NOW + timedelta(minutes=5)).isoformat()},  # not yet in force
        lambda f: {"experiment_spend_limit_usd": 1.0},
        lambda f: {"experiment": "phase-4n-second-pilot", "experiment_spend_limit_usd": 1.0},
    ],
)
def test_the_authorisation_binds_scope_request_hash_expiry_and_spend(tmp_path, change):
    conn, reg, data, frozen, posts, client = fixture(tmp_path)
    with pytest.raises(pilot.PilotRefused):
        attempt(conn, reg, data, frozen, internal(frozen, **change(frozen)), client)
    assert not posts


def test_revoked_source_rights_still_block_an_internal_run(tmp_path):
    from .support import institution

    conn, reg, data, frozen, posts, client = fixture(tmp_path)
    reg = {**reg, "treasury": institution("treasury", review_status="needs_review", approved_by=None,
                                         approved_on=None, approval_note=None)}  # fmt: skip
    with pytest.raises(pilot.PilotRefused):
        attempt(conn, reg, data, frozen, internal(frozen), client)
    assert not posts


def test_old_experiment_approvals_cannot_be_reused(tmp_path):
    conn, reg, data, frozen, posts, client = fixture(tmp_path)
    _, _, _, _, legacy, _, _ = setup_v3(tmp_path / "other")
    # A Phase 4N-style gold-bound approval document is not an internal authorisation, and cannot run this freeze.
    old = json.loads(
        legacy.model_copy(update={"experiment": "phase-4n-second-pilot"}).model_dump_json()
    )
    assert isinstance(pilot.load_approval(json.dumps(old).encode()), pilot.Approval)
    with pytest.raises(pilot.PilotRefused):
        attempt(conn, reg, data, frozen, pilot.load_approval(json.dumps(old).encode()), client)
    with pytest.raises(ValidationError):  # nor can it be dressed up as one by adding the purpose
        pilot.load_approval(json.dumps({**old, "purpose": "internal_draft"}).encode())
    # The Phase 4N plan accepts no internal authorisation at all.
    assert "internal_draft" not in pilot.SECOND_PLAN.approvals
    assert not posts


def test_the_gold_bound_approval_format_still_runs_the_experiment_unchanged(tmp_path):
    conn, reg, data, frozen, legacy, posts, client = setup_v3(tmp_path)
    attempt(conn, reg, data, frozen, legacy, client)
    assert len(posts) == 1
    record = json.loads((data / "run" / "evaluation.json").read_bytes())
    assert record["human_evaluation"] == "gold_bound_not_yet_scored"


def test_attempt_and_spending_limits_are_unchanged_for_internal_runs(tmp_path):
    conn, reg, data, frozen, posts, client = fixture(tmp_path)
    attempt(conn, reg, data, frozen, internal(frozen), client)
    before = [tuple(r) for r in conn.execute("SELECT * FROM research_llm_reservation ORDER BY id")]
    with pytest.raises(
        pilot.PilotRefused
    ):  # one attempt, no retry, even with a fresh authorisation
        attempt(conn, reg, data, frozen, internal(frozen), client, out="again")
    assert len(posts) == 1
    assert [
        tuple(r) for r in conn.execute("SELECT * FROM research_llm_reservation ORDER BY id")
    ] == before
    # Phase 4W: policy scopes alone see 8; every earlier scope, including this one, keeps the original ceiling of 4.
    assert (ss.LEGACY_LIFETIME_ATTEMPTS, ss.LIFETIME_USD, ss.LIFETIME_ATTEMPTS_PER_VERSION) == (
        4,
        5.0,
        2,
    )
    assert ss.LIFETIME_ATTEMPTS == 8


def test_a_fifth_lifetime_attempt_is_refused_for_an_internal_run_too(tmp_path):
    conn, reg, data, frozen, posts, client = fixture(tmp_path)
    spend(conn, 2, None)
    with pytest.raises(pilot.PilotRefused):
        attempt(conn, reg, data, frozen, internal(frozen), client)
    assert not posts


def test_a_malformed_response_is_recorded_but_can_never_display(tmp_path):
    conn, reg, data, frozen, posts, client = fixture(tmp_path)  # the mock answers "{}"
    attempt(conn, reg, data, frozen, internal(frozen), client)
    (status,) = conn.execute("SELECT status FROM research_summary").fetchone()
    assert status == "invalid_output"
    auto = DraftAllowlist.model_validate({"auto_display": {
        "enabled": True, "enabled_by": "x", "enabled_on": "2026-11-07", "note": "x"}})  # fmt: skip
    assert draft_summaries(conn, reg, auto) == []


def test_a_complete_internal_run_appears_as_a_draft_without_gold_or_a_list_entry(tmp_path):
    output = {
        "outlook": {"text": "Synthetic view.", "evidence": [
            {"version_id": 3, "section_ordinal": 1, "page": 2, "quote": "Permitted synthetic economic text."}]},
        "indicators": [], "forecasts": [],
    }  # fmt: skip
    conn, reg, data, frozen, posts, client = fixture(tmp_path, content=json.dumps(output))
    attempt(conn, reg, data, frozen, internal(frozen), client)
    (sid, status, review) = conn.execute(
        "SELECT id, status, review_status FROM research_summary"
    ).fetchone()
    assert status in ("verified", "failed_verification") and review == "unreviewed"
    auto = DraftAllowlist.model_validate({"auto_display": {
        "enabled": True, "enabled_by": "x", "enabled_on": "2026-11-07", "note": "x"}})  # fmt: skip
    (d,) = draft_summaries(conn, reg, auto)
    assert d.id == sid and d.row["review_status"] == "unreviewed"
    stored = (data / "run").rglob("*")
    assert not any(SECRET.encode() in p.read_bytes() for p in stored if p.is_file())


def test_the_phase_4n_plan_refuses_an_internal_authorisation_of_its_own_valid_freeze(tmp_path):
    # The 4N ledger keeps a free slot here, so only the plan's accepted approval formats can refuse.
    conn, reg, data, _frozen, posts, client = fixture(tmp_path, history=((1, None), (2, None)))
    raw = "\n".join(
        ("chrome", "old two")
    ).encode()  # version 2's stored original, as setup_v3 seeds it
    sha = hashlib.sha256(raw).hexdigest()
    (data / "raw" / sha[:2]).mkdir(parents=True, exist_ok=True)
    (data / "raw" / sha[:2] / sha).write_bytes(raw)
    control = data / "control"
    pilot.freeze(conn, reg, {2: (1,)}, control, plan=pilot.SECOND_PLAN)  # a valid Phase 4N freeze
    manifest = json.loads((control / "freeze.json").read_bytes())
    (doc,) = manifest["documents"]
    approval = internal(
        control, experiment="phase-4n-second-pilot", experiment_spend_limit_usd=1.0,
        documents=[{"version_id": 2, "request_sha256": doc["request_sha256"], "body_sha256": doc["body_sha256"],
                    "sections": [{"ordinal": 1, "rights_basis": "x", "third_party_rights": "x",
                                  "attribution": "x"}]}],
    )  # fmt: skip
    with pytest.raises(pilot.PilotRefused):
        attempt(conn, reg, data, control, approval, client)
    assert not posts
