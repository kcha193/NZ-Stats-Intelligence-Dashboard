"""Phase 4S: the Treasury version 3 experiment is its own reviewed plan; synthetic text only."""

import hashlib
import json
import runpy
from datetime import timedelta
from pathlib import Path

import httpx
import pytest

from nzstats.research import openrouter, pilot
from nzstats.research import summary_store as ss
from nzstats.store.db import connect, migrate

from .llm_support import NOW, seed_version
from .support import institution
from .test_pilot import remote

EXPERIMENT = "phase-4s-treasury-v3"


def run(*args, **kwargs):
    launcher = runpy.run_path(str(Path(__file__).parents[3] / "scripts/run_hosted_pilot.py"))
    return pilot.execute(*args, backup_check=launcher["verified_backup"], **kwargs)


def spend(conn, version_id, experiment, cost=0.1):
    limits = {"experiment": experiment} if experiment else {}
    rid = ss.start_run(
        conn, provider="openrouter", model=pilot.MODEL, hosted=True, prompt_version="outlook-v4",
        processing_version="3b-1", limits=limits, dry_run=False, now=NOW - timedelta(hours=1),
    )  # fmt: skip
    held = ss.reserve(
        conn, run_id=rid, version_id=version_id, call_no=1, provider="openrouter",
        model=pilot.MODEL, amount_usd=0.3, period_cap_usd=5, since=NOW - timedelta(days=30),
        now=NOW - timedelta(hours=1), expires_at=NOW,
        scope=ss.PilotScope(experiment) if experiment else None,
    )  # fmt: skip
    assert held is not None, "the synthetic ledger row must exist"
    ss.settle(conn, held, actual_usd=cost, basis="reported", now=NOW - timedelta(minutes=59))


def setup_v3(
    tmp_path,
    *,
    history=((1, None), (1, "phase-4n-second-pilot"), (2, "phase-4n-second-pilot")),
    v3_attempt=False,
):
    """Versions 1 and 2 carry the three consumed attempts; version 3 carries none."""
    data = tmp_path / "data"
    conn = connect(data / "nzstats.db")
    migrate(conn)
    old1 = seed_version(conn, sections=("old one",), key="treasury", doc="v1")
    old2 = seed_version(conn, sections=("chrome", "old two"), key="rbnz", doc="v2")
    sections = ("UNLICENSED SYNTHETIC TEXT", "Permitted synthetic economic text.")
    version = seed_version(conn, sections=sections, key="treasury", doc="v3")
    assert (old1, old2, version) == (1, 2, 3)
    for version_id, experiment in history:
        spend(conn, version_id, experiment)
    if v3_attempt:  # an earlier attempt on version 3 itself, before the freeze
        spend(conn, 3, None)
    raw = "\n".join(sections).encode()
    sha = hashlib.sha256(raw).hexdigest()
    path = data / "raw" / sha[:2] / sha
    path.parent.mkdir(parents=True)
    path.write_bytes(raw)
    reg = {"treasury": institution("treasury"), "rbnz": institution("rbnz")}
    frozen = data / "frozen"
    before = conn.total_changes
    pilot.freeze(conn, reg, {3: (1,)}, frozen, plan=pilot.TREASURY_V3_PLAN)
    assert conn.total_changes == before
    gold = data / "gold.json"
    gold.write_text('{"synthetic":true}')
    approval = pilot.Approval(
        state="approved", experiment=EXPERIMENT, experiment_spend_limit_usd=0.5,
        approved_by="Synthetic Owner", approved_at=NOW, expires_at=NOW + timedelta(hours=1),
        frozen_sha256=pilot.file_sha256(frozen / "freeze.json"), gold_path=gold,
        gold_sha256=pilot.file_sha256(gold), gold_review="Synthetic human gold review",
        provider_review="Synthetic acceptance of the exact route",
        account_controls_evidence="Synthetic signed account review",
        dedicated_key_confirmed=True,
        rights=(
            pilot.DocumentRights(
                version_id=3,
                sections=(
                    pilot.SectionRight(
                        ordinal=1, rights_basis="Synthetic owner-authored text",
                        third_party_rights="None in this synthetic section",
                        attribution="Synthetic owner; AI interpretation labelled",
                    ),
                ),
            ),
        ),
    )  # fmt: skip
    posts = []

    def respond(req):
        if req.url.path == "/api/v1/key":  # a real key's usage equals the ledger's recorded spend
            used = ss.lifetime_spent(conn)
            data_ = {
                "limit": 5, "limit_reset": None, "limit_remaining": 5 - used, "usage": used,
                "byok_usage": 0, "is_management_key": False,
            }  # fmt: skip
            return httpx.Response(200, json={"data": data_})
        return remote(req, posts)

    client = httpx.Client(transport=httpx.MockTransport(respond))
    return conn, reg, data, frozen, approval, posts, client


def attempt(conn, reg, data, frozen, approval, client, out="run"):
    return run(
        conn, reg, data, frozen, approval, data / out, "synthetic-secret",
        client=client, now_fn=lambda: NOW,
    )  # fmt: skip


def lifetime_attempts(conn):
    return conn.execute(
        "SELECT COUNT(*) FROM research_llm_reservation WHERE provider='openrouter'"
    ).fetchone()[0]


def test_experiment_is_a_separate_reviewed_configuration():
    experiment = openrouter.EXPERIMENTS[EXPERIMENT]
    assert experiment.prompt_version == "outlook-v5"
    assert (experiment.reasoning_effort, experiment.max_output_tokens) == ("low", 12000)
    assert (experiment.scope.max_attempts, experiment.scope.max_usd) == (1, 0.5)
    assert openrouter.EXPERIMENTS["phase-4n-second-pilot"].prompt_version == "outlook-v4"
    assert dict(pilot.PLANS[EXPERIMENT].versions) == {3: "treasury"}


def test_freeze_binds_version_three_prompt_effort_cap_and_a_cost_inside_the_experiment(tmp_path):
    conn, reg, data, frozen, approval, posts, client = setup_v3(tmp_path)
    manifest = json.loads((frozen / "freeze.json").read_bytes())
    assert (manifest["format"], manifest["experiment"]) == (3, EXPERIMENT)
    assert manifest["experiment_spend_limit_usd"] == 0.5
    assert (manifest["prompt_version"], manifest["verifier_version"]) == ("outlook-v5", "verify-4")
    assert (manifest["reasoning_effort"], manifest["max_output_tokens"]) == ("low", 12000)
    assert [d["version_id"] for d in manifest["documents"]] == [3]
    assert manifest["documents"][0]["worst_case_usd"] < 0.5
    assert manifest["documents"][0]["approved_section_ordinals"] == [1]


def test_each_plan_refuses_the_other_plans_versions(tmp_path):
    conn, reg, data, frozen, approval, posts, client = setup_v3(tmp_path)
    with pytest.raises(pilot.PilotRefused):  # the Phase 4N plan still cannot take version 3
        pilot.freeze(conn, reg, {3: (1,)}, data / "other", plan=pilot.SECOND_PLAN)
    with pytest.raises(pilot.PilotRefused):  # version 3's plan cannot take a consumed version
        pilot.freeze(conn, reg, {1: (0,)}, data / "other2", plan=pilot.TREASURY_V3_PLAN)
    pilot.freeze(conn, reg, {2: (1,)}, data / "control", plan=pilot.SECOND_PLAN)  # valid for 4N
    with pytest.raises(pilot.PilotRefused):  # so only the plan keeps RBNZ out of version 3's
        pilot.freeze(conn, reg, {2: (1,)}, data / "other3", plan=pilot.TREASURY_V3_PLAN)
    with pytest.raises(pilot.PilotRefused):  # nor two documents
        pilot.freeze(conn, reg, {1: (0,), 3: (1,)}, data / "other4", plan=pilot.TREASURY_V3_PLAN)


def test_one_request_is_sent_and_it_uses_the_last_lifetime_attempt(tmp_path):
    conn, reg, data, frozen, approval, posts, client = setup_v3(tmp_path)
    assert lifetime_attempts(conn) == 3
    attempt(conn, reg, data, frozen, approval, client)
    assert len(posts) == 1
    assert posts[0].content == (frozen / "v3-request.json").read_bytes()
    assert json.loads(posts[0].content)["max_tokens"] == 12000
    assert lifetime_attempts(conn) == 4
    assert ss.version_attempts(conn, 3) == 1
    tagged = conn.execute(
        "SELECT json_extract(limits,'$.experiment') FROM research_llm_run"
    ).fetchall()
    assert tagged[-1][0] == EXPERIMENT


def test_no_second_attempt_and_no_history_change(tmp_path):
    conn, reg, data, frozen, approval, posts, client = setup_v3(tmp_path)
    attempt(conn, reg, data, frozen, approval, client)
    before = conn.execute("SELECT * FROM research_llm_reservation ORDER BY id").fetchall()
    with pytest.raises(pilot.PilotRefused):
        attempt(conn, reg, data, frozen, approval, client, out="again")
    assert len(posts) == 1
    after = conn.execute("SELECT * FROM research_llm_reservation ORDER BY id").fetchall()
    assert [tuple(r) for r in before] == [tuple(r) for r in after]


def test_version_three_with_an_existing_attempt_is_refused_by_the_plan_itself(tmp_path):
    # Lifetime attempts stand at 2 of 4 here, so only the plan's ledger precondition can refuse.
    conn, reg, data, frozen, approval, posts, client = setup_v3(
        tmp_path, history=((1, None),), v3_attempt=True
    )
    assert lifetime_attempts(conn) == 2 and ss.version_attempts(conn, 3) == 1
    with pytest.raises(pilot.PilotRefused):
        attempt(conn, reg, data, frozen, approval, client)
    assert not posts


@pytest.mark.parametrize(
    "change",
    [
        {"experiment": "phase-4n-second-pilot"},
        {"experiment": "phase-4m"},
        {"experiment": "phase-4n-second-pilot", "experiment_spend_limit_usd": 1.0},
        {"experiment_spend_limit_usd": 1.0},
        {"experiment_spend_limit_usd": 5.0},
    ],
)
def test_approval_for_another_experiment_or_cap_cannot_run_this_freeze(tmp_path, change):
    conn, reg, data, frozen, approval, posts, client = setup_v3(tmp_path)
    with pytest.raises(pilot.PilotRefused):
        attempt(conn, reg, data, frozen, approval.model_copy(update=change), client)
    assert not posts


@pytest.mark.parametrize(
    "change",
    [
        {"format": 2},
        {"experiment": "phase-4n-second-pilot"},
        {"prompt_version": "outlook-v4"},
        {"max_output_tokens": 6000},
        {"reasoning_effort": "high"},
        {"experiment_spend_limit_usd": 1.0},
    ],
)
def test_edited_freeze_manifest_cannot_execute(tmp_path, change):
    conn, reg, data, frozen, approval, posts, client = setup_v3(tmp_path)
    manifest = {**json.loads((frozen / "freeze.json").read_bytes()), **change}
    (frozen / "freeze.json").write_bytes(json.dumps(manifest).encode())
    approval = approval.model_copy(
        update={"frozen_sha256": pilot.file_sha256(frozen / "freeze.json")}
    )
    with pytest.raises(pilot.PilotRefused):
        attempt(conn, reg, data, frozen, approval, client)
    assert not posts


def test_a_fifth_lifetime_attempt_is_refused_even_for_this_experiment(tmp_path):
    conn, reg, data, frozen, approval, posts, client = setup_v3(tmp_path)
    spend(conn, 2, None)  # a fourth attempt under another tag: only the lifetime limit can refuse
    with pytest.raises(pilot.PilotRefused):
        attempt(conn, reg, data, frozen, approval, client)
    assert not posts


def test_a_manifest_edited_into_the_other_plan_still_cannot_run_version_three(tmp_path):
    conn, reg, data, frozen, approval, posts, client = setup_v3(tmp_path)
    manifest = {**json.loads((frozen / "freeze.json").read_bytes())}
    manifest.update(
        format=2, experiment="phase-4n-second-pilot", experiment_spend_limit_usd=1.0,
        prompt_version="outlook-v4",
    )  # fmt: skip
    (frozen / "freeze.json").write_bytes(json.dumps(manifest).encode())
    approval = approval.model_copy(
        update={
            "experiment": "phase-4n-second-pilot",
            "experiment_spend_limit_usd": 1.0,
            "frozen_sha256": pilot.file_sha256(frozen / "freeze.json"),
        }
    )  # a fully re-hashed, self-consistent Phase 4N approval of a version it never covered
    with pytest.raises(pilot.PilotRefused):
        attempt(conn, reg, data, frozen, approval, client)
    assert not posts
