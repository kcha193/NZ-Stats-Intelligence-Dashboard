"""Phase 4W: the operator-run policy command. Preflight (dry run) and explicit execution; mocked provider, SYNTHETIC FIXTURE.

No real request is made anywhere in this file. A policy file, a confirmation code and a terminal prompt are all required, and
each refusal below must happen before any money is reserved or any request is sent.
"""

import json
import sqlite3
from dataclasses import replace
from datetime import timedelta

import httpx
import pytest

from nzstats.research import pilot
from nzstats.research import policy as pol
from nzstats.research import policy_run as run
from nzstats.research import summary_store as ss
from nzstats.research.drafts import DraftAllowlist, draft_summaries
from nzstats.research.registry import LlmProcessing

from .llm_support import NOW, seed_version
from .policy_support import policy_dict, world, write_policy
from .test_openrouter import envelope
from .test_pilot import remote
from .test_pilot_treasury_v3 import spend

KEY = "synthetic-key-never-printed"
AUTO = DraftAllowlist.model_validate(
    {"auto_display": {"enabled": True, "enabled_by": "x", "enabled_on": "2026-11-07", "note": "x"}}
)


def good_output(version):
    return {
        "outlook": {
            "text": "Synthetic view.",
            "evidence": [
                {"version_id": version, "section_ordinal": 1, "page": 2,
                 "quote": "Activity is expected to grow 2.5% in the year to March 2027"}
            ],
        },
        "indicators": [],
        "forecasts": [],
    }  # fmt: skip


class Env:
    """A synthetic Treasury world, a policy file and a mocked OpenRouter that records every request."""

    def __init__(self, tmp_path, *, content="{}", status=200, **kw):
        self.conn, self.reg, self.data, self.version = world(tmp_path, **kw)
        self.path = write_policy(self.data, policy_dict(self.reg))
        self.policy, self.sha = pol.load_policy(self.path, self.data)
        self.posts, self.gets, self.content, self.status = [], [], content, status
        self.client = httpx.Client(transport=httpx.MockTransport(self.respond))
        self.ask_log = []

    def respond(self, req):
        if req.method == "POST":
            self.posts.append(req)
            if self.status != 200:
                return httpx.Response(self.status, json={"error": {"message": "synthetic"}})
            choice = {"message": {"content": self.content}, "finish_reason": "stop"}
            return httpx.Response(200, json=envelope(choices=[choice]))
        self.gets.append(req.url.path)
        if req.url.path == "/api/v1/key":
            used = ss.lifetime_spent(self.conn)
            data = {"limit": 5, "limit_reset": None, "limit_remaining": 5 - used, "usage": used,
                    "byok_usage": 0, "is_management_key": False}  # fmt: skip
            return httpx.Response(200, json={"data": data})
        return remote(req, [])

    def pre(self, **kw):
        return run.preflight(
            self.conn, self.reg, self.policy, self.sha, self.version, self.data, now=NOW, **kw
        )

    def go(self, *, confirm=None, interactive=True, answer=None, key=KEY, **kw):
        confirm = confirm if confirm is not None else (self.pre().confirm_code or "")
        return run.execute_policy(
            self.conn, self.reg, self.data, self.path, self.version, confirm=confirm, interactive=interactive,
            ask=lambda prompt: (self.ask_log.append(prompt), answer if answer is not None else confirm)[1],
            api_key=key, client=self.client, now_fn=lambda: NOW, operator="synthetic-operator", **kw,
        )  # fmt: skip

    def events(self):
        return [
            dict(r) for r in self.conn.execute("SELECT * FROM research_policy_event ORDER BY id")
        ]

    def attempts(self):
        return ss.version_attempts(self.conn, self.version)


def fill(env, n, cost, *, policy_scopes=False):
    """`n` settled historical-style attempts on their own document versions (the ledger needs real version rows)."""
    for i in range(n):
        version = seed_version(env.conn, key="treasury", doc=f"fill{i}-{cost}")
        spend(env.conn, version, f"policy-{i:016d}" if policy_scopes else f"e{i}", cost=cost)


def refused(call):
    with pytest.raises(pol.PolicyRefused) as info:
        call()
    return info.value.code


# --- preflight ------------------------------------------------------------------------------------------------------
def test_a_dry_run_shows_the_decision_facts_and_contacts_nothing(tmp_path):
    env = Env(tmp_path)
    before = env.conn.total_changes
    pf = env.pre()
    assert pf.eligible and pf.refusal_codes == () and len(pf.confirm_code) == 8
    assert env.conn.total_changes == before and not env.posts and not env.gets
    assert pf.ordinals == (0, 1, 2) and pf.page_range == (1, 3) and pf.worst_case_usd <= 0.5
    assert (pf.prompt_version, pf.verifier_version) == ("outlook-v6", "verify-5")
    assert (
        len(pf.request_sha256) == 64
        and pf.capacity.calls_used == 0
        and pf.capacity.lifetime_attempts_used == 0
    )


def test_the_dry_run_text_holds_no_source_text_request_body_key_or_private_annotation(tmp_path):
    env = Env(tmp_path)
    text = run.render_preflight(env.pre())
    for forbidden in (
        "Activity is expected",
        "Annual CPI",
        "SYNTHETIC FIXTURE cover",
        KEY,
        "Authorization",
        "messages",
    ):
        assert forbidden not in text
    for wanted in (
        "treasury-feu-synthetic",
        "outlook-v6",
        "verify-5",
        "anthropic/claude-opus-5.5",
        "google-vertex/europe",
        "zero data retention",
        "request hash",
        "Confirmation code",
        "pages 1-3",
    ):
        assert wanted.lower() in text.lower(), wanted


def test_the_confirmation_code_is_bound_to_policy_document_scope_and_request(tmp_path):
    env = Env(tmp_path)
    base = env.pre().confirm_code
    assert env.pre(ordinals=(1, 2)).confirm_code != base  # a different scope is a different request
    other = write_policy(env.data, policy_dict(env.reg, per_call_usd=0.4), name="other.json")
    policy, sha = pol.load_policy(other, env.data)
    changed = run.preflight(env.conn, env.reg, policy, sha, env.version, env.data, now=NOW)
    assert changed.confirm_code != base


def test_every_refusal_reason_is_listed_without_text(tmp_path):
    env = Env(tmp_path, series="Budget")
    env.reg = {"treasury": replace(env.reg["treasury"], llm_processing=LlmProcessing.DENIED)}
    pf = env.pre()
    assert not pf.eligible and {"series_mismatch", "llm_processing_denied"} <= set(pf.refusal_codes)
    text = run.render_preflight(pf)
    assert "REFUSED" in text and "series_mismatch" in text and "llm_processing_denied" in text
    assert pf.confirm_code is None  # nothing to confirm while refused


def test_an_expired_or_future_policy_is_refused_in_the_dry_run(tmp_path):
    env = Env(tmp_path)
    late = run.preflight(
        env.conn, env.reg, env.policy, env.sha, env.version, env.data, now=env.policy.expires_at
    )
    assert "policy_expired" in late.refusal_codes and not late.eligible


def test_over_the_per_call_cap_the_dry_run_refuses(tmp_path):
    env = Env(tmp_path)
    tight = write_policy(env.data, policy_dict(env.reg, per_call_usd=0.0001), name="tight.json")
    policy, sha = pol.load_policy(tight, env.data)
    pf = run.preflight(env.conn, env.reg, policy, sha, env.version, env.data, now=NOW)
    assert "per_call_cap_exceeded" in pf.refusal_codes


# --- execution: every refusal happens before money moves ----------------------------------------------------------------
@pytest.mark.parametrize(
    "kwargs,code",
    [
        ({"interactive": False}, "not_interactive"),
        ({"confirm": "deadbeef"}, "confirmation_mismatch"),
        ({"confirm": ""}, "confirmation_mismatch"),
        ({"answer": "wrong123"}, "not_confirmed"),
        ({"answer": ""}, "not_confirmed"),
        ({"key": ""}, "api_key_missing"),
    ],
)
def test_execution_refuses_before_any_request_or_reservation(tmp_path, kwargs, code):
    env = Env(tmp_path)
    assert refused(lambda: env.go(**kwargs)) == code
    assert not env.posts and not env.gets and env.attempts() == 0
    assert [e["event"] for e in env.events()] == ["refused"] and env.events()[0][
        "refusal_code"
    ] == code
    assert pol.policy_usage(env.conn, env.sha) == (0, 0.0)


def test_a_non_interactive_run_never_even_prompts(tmp_path):
    env = Env(tmp_path)
    refused(lambda: env.go(interactive=False))
    assert env.ask_log == []


def test_the_terminal_prompt_names_the_scope_and_never_the_key_or_text(tmp_path):
    env = Env(tmp_path, content=json.dumps(good_output(1)))
    env.go()
    (prompt,) = env.ask_log
    assert "Fortnightly Economic Update" in prompt and "pages 1-3" in prompt and "US$" in prompt
    assert KEY not in prompt and "Activity is expected" not in prompt


@pytest.mark.parametrize(
    "mutate,code",
    [
        (
            lambda e: setattr(
                e,
                "reg",
                {"treasury": replace(e.reg["treasury"], llm_processing=LlmProcessing.DENIED)},
            ),
            "llm_processing_denied",
        ),
        (
            lambda e: e.conn.execute(
                "UPDATE research_document_version SET superseded_at=?", (NOW.isoformat(),)
            ),
            "version_not_current",
        ),
        (lambda e: spend(e.conn, e.version, None), "version_attempted"),
    ],
)
def test_a_change_after_the_dry_run_is_refused_at_execution(tmp_path, mutate, code):
    env = Env(tmp_path)
    confirm = env.pre().confirm_code
    mutate(env)
    got = refused(lambda: env.go(confirm=confirm))
    assert got == code or got == "confirmation_mismatch"
    assert not env.posts


def test_changed_source_text_changes_the_code_so_the_old_one_is_refused(tmp_path):
    env = Env(tmp_path)
    confirm = env.pre().confirm_code
    raw = next(p for p in (env.data / "raw").rglob("*") if p.is_file())
    raw.write_bytes(b"swapped after the dry run")
    assert refused(lambda: env.go(confirm=confirm)) in (
        "source_text_unavailable",
        "confirmation_mismatch",
    )
    assert not env.posts


def test_a_revoked_policy_cannot_run(tmp_path):
    env = Env(tmp_path)
    pol.record_event(
        env.conn, "revoked", env.policy, env.sha, operator="o", now=NOW, detail="withdrawn"
    )
    assert refused(lambda: env.go()) == "policy_revoked"
    assert not env.posts


def test_global_budget_exhaustion_refuses_even_inside_the_policy_caps(tmp_path):
    env = Env(tmp_path)
    fill(env, 4, 1.2)  # the four historical attempts, nearly the whole US$5
    assert refused(lambda: env.go()) in ("lifetime_budget_exhausted",)
    assert not env.posts


def test_the_eight_attempt_ceiling_refuses_a_ninth(tmp_path):
    env = Env(tmp_path)
    fill(env, 8, 0.01, policy_scopes=True)
    assert refused(lambda: env.go()) == "lifetime_attempts_exhausted"
    assert not env.posts


# --- a complete run -----------------------------------------------------------------------------------------------------------
def test_a_confirmed_run_makes_exactly_one_request_and_records_everything(tmp_path):
    env = Env(tmp_path, content=json.dumps(good_output(1)))
    pf = env.pre()
    result = env.go()
    assert len(env.posts) == 1 and env.attempts() == 1
    body = json.loads(env.posts[0].content)
    assert body["provider"] == {"only": ["google-vertex/europe"], "zdr": True, "data_collection": "deny",
                                "allow_fallbacks": False, "require_parameters": True}  # fmt: skip
    (summary,) = env.conn.execute(
        "SELECT status, prompt_version, verifier_version, review_status, hosted FROM research_summary"
    ).fetchall()
    assert (summary["prompt_version"], summary["verifier_version"], summary["review_status"]) == (
        "outlook-v6",
        "verify-5",
        "unreviewed",
    )
    assert result.outcome in ("verified", "failed_verification")
    (event,) = env.events()
    assert event["event"] == "executed" and event["policy_sha256"] == env.sha
    assert (event["prompt_version"], event["verifier_version"]) == ("outlook-v6", "verify-5")
    assert (
        event["prompt_sha256"] == env.policy.prompt_sha256
        and event["verifier_sha256"] == env.policy.verifier_sha256
    )
    assert (
        event["request_sha256"] == pf.request_sha256
        and event["content_sha256"] == pf.content_sha256
    )
    assert (
        event["model"] == "anthropic/claude-opus-5.5"
        and event["provider_id"] == "google-vertex/europe"
    )
    assert (
        event["operator"] == "synthetic-operator"
        and event["cost_usd"] > 0
        and event["attempt_no"] == 1
    )
    assert event["input_tokens"] and event["output_tokens"] and event["summary_id"]
    assert KEY not in json.dumps(event)
    assert pol.policy_usage(env.conn, env.sha)[0] == 1
    # The experiment tag, not the policy file, is what the legacy-safe ledger counts.
    tag = env.conn.execute(
        "SELECT json_extract(limits,'$.experiment') FROM research_llm_run"
    ).fetchone()[0]
    assert tag == pol.scope_name(env.sha)


def test_a_successful_response_shows_as_an_unreviewed_internal_draft(tmp_path):
    env = Env(tmp_path, content=json.dumps(good_output(1)))
    env.go()
    (draft,) = draft_summaries(env.conn, env.reg, AUTO)
    assert (
        draft.row["review_status"] == "unreviewed" and draft.row["verifier_version"] == "verify-5"
    )


def test_an_unusable_response_consumes_the_attempt_and_never_displays(tmp_path):
    env = Env(tmp_path, content="not json at all")
    env.go()
    assert env.attempts() == 1 and len(env.posts) == 1
    status = env.conn.execute("SELECT status FROM research_summary").fetchone()[0]
    assert status in ("invalid_output", "provider_error")  # either way: stored, billed, never shown
    assert draft_summaries(env.conn, env.reg, AUTO) == []
    (event,) = env.events()
    assert event["event"] == "executed" and event["outcome"] == status and event["cost_usd"] > 0


def test_a_provider_failure_is_not_retried_and_consumes_the_attempt(tmp_path):
    env = Env(tmp_path, status=500)
    env.go()
    assert len(env.posts) == 1 and env.attempts() == 1  # no automatic retry
    assert env.events()[0]["outcome"] == "provider_error" and env.events()[0]["cost_usd"] > 0
    assert refused(lambda: env.go()) in ("version_attempted", "content_already_executed")
    assert len(env.posts) == 1


def test_a_second_run_on_the_same_version_is_refused_under_any_policy(tmp_path):
    env = Env(tmp_path, content=json.dumps(good_output(1)))
    env.go()
    reissued = write_policy(
        env.data, policy_dict(env.reg, policy_id="treasury-feu-reissued"), name="again.json"
    )
    env.path = reissued
    env.policy, env.sha = pol.load_policy(reissued, env.data)
    assert refused(lambda: env.go(confirm="00000000")) == "version_attempted"
    assert len(env.posts) == 1


def test_retagging_a_run_and_renaming_a_document_do_not_restore_the_spent_attempt(tmp_path):
    env = Env(tmp_path, content=json.dumps(good_output(1)))
    env.go()
    try:
        env.conn.execute("UPDATE research_llm_run SET limits='{}'")
    except sqlite3.DatabaseError:
        pass
    env.conn.execute("UPDATE research_publication SET title='Renamed', series='Other'")
    assert pol.policy_usage(env.conn, env.sha)[0] == 1
    assert env.attempts() == 1


def test_an_interrupted_call_keeps_its_worst_case_reservation_is_audited_and_cannot_rerun(tmp_path):
    env = Env(tmp_path)

    def interrupted(req):
        if req.method == "POST":
            raise KeyboardInterrupt  # the process is stopped mid-call: whether it was billed is unknown
        return Env.respond(env, req)

    env.client = httpx.Client(transport=httpx.MockTransport(interrupted))
    with pytest.raises(KeyboardInterrupt):
        env.go()
    assert env.attempts() == 1  # the reservation was written before the request
    (event,) = env.events()
    assert (
        event["event"] == "executed" and event["outcome"] == "interrupted" and event["cost_usd"] > 0
    )
    state = env.conn.execute("SELECT state FROM research_llm_reservation").fetchone()[0]
    assert state in ("held", "abandoned")  # still counted at its worst case
    assert pol.policy_usage(env.conn, env.sha)[0] == 1
    assert refused(lambda: env.go()) in ("version_attempted", "content_already_executed")


def test_the_legacy_ledger_is_unchanged_by_a_policy_run(tmp_path):
    env = Env(tmp_path, content=json.dumps(good_output(1)))
    fill(env, 1, 0.18)
    before = [
        tuple(r) for r in env.conn.execute("SELECT * FROM research_llm_reservation ORDER BY id")
    ]
    env.go()
    after = [
        tuple(r) for r in env.conn.execute("SELECT * FROM research_llm_reservation ORDER BY id")
    ]
    assert after[: len(before)] == before and len(after) == len(before) + 1
    assert ss.lifetime_spent(env.conn) > 0.18


def test_loss_of_zdr_eligibility_stops_the_run_before_the_request(tmp_path):
    env = Env(tmp_path)
    original = env.respond
    env.respond = lambda req: (
        remote(req, [], unsafe=True) if req.url.path.endswith("zdr") else original(req)
    )
    env.client = httpx.Client(transport=httpx.MockTransport(env.respond))
    with pytest.raises(pilot.PilotRefused):
        env.go()
    assert not env.posts and env.attempts() == 0
    assert [e["event"] for e in env.events()] == ["refused"]


def test_a_changed_price_or_model_route_stops_the_run_before_the_request(tmp_path):
    env = Env(tmp_path)
    original = Env.respond

    def repriced(req):
        resp = original(env, req)
        if req.url.path.endswith("/endpoints") and resp.status_code == 200:
            payload = resp.json()
            payload["data"]["endpoints"][0]["pricing"]["prompt"] = "0.00001"
            return httpx.Response(200, json=payload)
        return resp

    env.client = httpx.Client(transport=httpx.MockTransport(repriced))
    with pytest.raises(pilot.PilotRefused):
        env.go()
    assert not env.posts and env.attempts() == 0


def test_a_dashboard_open_or_a_dry_run_never_calls_the_provider(tmp_path):
    env = Env(tmp_path, content=json.dumps(good_output(1)))
    env.pre()
    draft_summaries(env.conn, env.reg, AUTO)
    assert env.posts == [] and env.gets == []


# --- independent review findings (Phase 4W) -------------------------------------------------------------------------------
def go_with(env, *, ask, now_fn=lambda: NOW, confirm=None):
    confirm = confirm or env.pre().confirm_code
    return run.execute_policy(
        env.conn, env.reg, env.data, env.path, env.version, confirm=confirm, interactive=True, ask=ask,
        api_key=KEY, client=env.client, now_fn=now_fn, operator="synthetic-operator",
    )  # fmt: skip


def test_a_revocation_while_the_prompt_is_open_still_stops_the_run(tmp_path):
    env = Env(tmp_path, content=json.dumps(good_output(1)))
    code = env.pre().confirm_code

    def ask(prompt):
        pol.record_event(
            env.conn, "revoked", env.policy, env.sha, operator="o", now=NOW, detail="withdrawn"
        )
        return code

    assert refused(lambda: go_with(env, ask=ask)) == "policy_revoked"
    assert not env.posts and env.attempts() == 0


def test_a_policy_that_expires_while_the_prompt_is_open_still_stops_the_run(tmp_path):
    env = Env(tmp_path)
    code = env.pre().confirm_code
    clock = [NOW]

    def ask(prompt):
        clock[0] = env.policy.expires_at
        return code

    assert refused(lambda: go_with(env, ask=ask, now_fn=lambda: clock[0])) in (
        "policy_expired",
        "confirmation_expired",
    )
    assert not env.posts and env.attempts() == 0


def test_a_confirmation_typed_long_after_the_dry_run_is_refused(tmp_path):
    env = Env(tmp_path)
    code = env.pre().confirm_code
    clock = [NOW]

    def ask(prompt):
        clock[0] = NOW + run.PROMPT_TIMEOUT + timedelta(seconds=1)
        return code

    assert refused(lambda: go_with(env, ask=ask, now_fn=lambda: clock[0])) == "confirmation_expired"
    assert not env.posts


def test_a_source_change_while_the_prompt_is_open_still_stops_the_run(tmp_path):
    env = Env(tmp_path)
    code = env.pre().confirm_code

    def ask(prompt):
        spend(
            env.conn, env.version, None
        )  # another process used this version while the prompt was open
        return code

    assert refused(lambda: go_with(env, ask=ask)) == "version_attempted"
    assert not env.posts


def test_two_processes_on_one_version_audit_exactly_one_execution_and_no_traceback(tmp_path):
    """The loser must not claim the winner's reservation, and the winner's real outcome must still be audited."""
    env = Env(tmp_path, content=json.dumps(good_output(1)))
    rival = {}

    def backup_with_rival(conn, data_dir, output, now):
        pilot.verified_backup(conn, data_dir, output, now)
        if not rival:  # the winner starts and finishes while the loser is between its backup and its reservation
            rival["outcome"] = env.go(confirm=env.pre().confirm_code)

    code = env.pre().confirm_code
    assert (
        refused(
            lambda: run.execute_policy(
                env.conn,
                env.reg,
                env.data,
                env.path,
                env.version,
                confirm=code,
                interactive=True,
                ask=lambda p: code,
                api_key=KEY,
                client=env.client,
                now_fn=lambda: NOW,
                operator="loser",
                backup_check=backup_with_rival,
            )  # fmt: skip
        )
        == "attempt_consumed"
    )
    assert len(env.posts) == 1 and env.attempts() == 1
    executed = [e for e in env.events() if e["event"] == "executed"]
    assert (
        len(executed) == 1
        and executed[0]["operator"] == "synthetic-operator"
        and executed[0]["cost_usd"] > 0
    )
    assert [e["refusal_code"] for e in env.events() if e["event"] == "refused"] == [
        "attempt_consumed"
    ]


def test_an_unknown_version_refusal_is_still_logged(tmp_path):
    env = Env(tmp_path)
    with pytest.raises(pol.PolicyRefused):
        run.execute_policy(
            env.conn, env.reg, env.data, env.path, 999, confirm="x", interactive=True, ask=lambda p: "x",
            api_key=KEY, client=env.client, now_fn=lambda: NOW, operator="o",
        )  # fmt: skip
    (event,) = env.events()
    assert (
        event["event"] == "refused"
        and event["version_id"] is None
        and event["refusal_code"] == "version_not_found"
    )


def test_a_frozen_request_that_differs_from_the_dry_run_is_refused(tmp_path, monkeypatch):
    env = Env(tmp_path)
    real = pilot.freeze

    def changed(*a, **k):
        manifest = real(*a, **k)
        manifest["documents"][0]["request_sha256"] = "0" * 64
        return manifest

    monkeypatch.setattr(pilot, "freeze", changed)
    assert refused(lambda: env.go()) == "request_changed"
    assert not env.posts and env.attempts() == 0


def test_a_frozen_worst_case_over_the_per_call_cap_is_refused_even_if_the_preflight_passed(
    tmp_path, monkeypatch
):
    env = Env(tmp_path)
    real = pilot.freeze

    def dearer(*a, **k):
        manifest = real(*a, **k)
        manifest["documents"][0]["worst_case_usd"] = 0.51
        return manifest

    monkeypatch.setattr(pilot, "freeze", dearer)
    assert refused(lambda: env.go()) == "per_call_cap_exceeded"
    assert not env.posts


def test_execute_refuses_a_plan_that_is_not_the_approvals_experiment(tmp_path):
    env = Env(tmp_path)
    pf = env.pre()
    plan = run.plan_for(env.policy, env.sha, env.version)
    run.register_policy_experiment(plan.experiment)
    manifest = pilot.freeze(env.conn, env.reg, {env.version: pf.ordinals}, env.data / "f", plan)
    approval = run._approval(
        env.policy, env.sha, plan, pf, manifest["documents"][0], env.data / "f", NOW
    )
    other = run.plan_for(env.policy, "f" * 64, env.version)
    with pytest.raises(pilot.PilotRefused):
        pilot.execute(env.conn, env.reg, env.data, env.data / "f", approval, env.data / "r", KEY,
                      backup_check=pilot.verified_backup, client=env.client, now_fn=lambda: NOW, plan=other)  # fmt: skip
    assert not env.posts


def test_terminal_control_characters_in_a_title_never_reach_the_report_or_the_prompt(tmp_path):
    env = Env(tmp_path)
    pf = env.pre()
    hostile = replace(pf, source=replace(pf.source, title="Update\x1b[2J\x1b[Hforged line\x07"))
    for text in (run.render_preflight(hostile), run._prompt_text(hostile)):
        assert "\x1b" not in text and "\x07" not in text and "Update" in text
