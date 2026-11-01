"""Synthetic end-to-end pilot runner; only MockTransport reaches the HTTP boundary."""

import hashlib
import json
import runpy
import stat
from datetime import timedelta
from pathlib import Path

import httpx
import pytest

from nzstats.research import pilot
from nzstats.store.db import connect, migrate

from .llm_support import NOW, seed_version
from .support import institution
from .test_openrouter import envelope


def run(*args, **kwargs):
    launcher = runpy.run_path(str(Path(__file__).parents[3] / "scripts/run_hosted_pilot.py"))
    return pilot.execute(*args, backup_check=launcher["verified_backup"], **kwargs)


def setup_pilot(tmp_path):
    data = tmp_path / "data"
    conn = connect(data / "nzstats.db")
    migrate(conn)
    sections = ("UNLICENSED SYNTHETIC TEXT", "Permitted synthetic economic text.")
    version = seed_version(conn, sections=sections, key="treasury")
    raw = "\n".join(sections).encode()
    sha = hashlib.sha256(raw).hexdigest()
    path = data / "raw" / sha[:2] / sha
    path.parent.mkdir(parents=True)
    path.write_bytes(raw)
    reg = {"treasury": institution("treasury")}
    frozen = data / "frozen"
    before = conn.total_changes
    pilot.freeze(conn, reg, {version: (1,)}, frozen)
    assert conn.total_changes == before
    gold = data / "gold.json"
    gold.write_text('{"synthetic":true}')
    approval = pilot.Approval(
        state="approved",
        approved_by="Synthetic Owner",
        approved_at=NOW,
        expires_at=NOW + timedelta(hours=1),
        frozen_sha256=pilot.file_sha256(frozen / "freeze.json"),
        gold_path=gold,
        gold_sha256=pilot.file_sha256(gold),
        gold_review="Synthetic human gold review; expected rejection cases retained",
        provider_review="Synthetic acceptance of exact intermediary/route/privacy limitations",
        account_controls_evidence="Synthetic signed account review: logging/training off; strict ZDR; no safety retention or auxiliary logging",
        dedicated_key_confirmed=True,
        rights=(
            pilot.DocumentRights(
                version_id=version,
                sections=(
                    pilot.SectionRight(
                        ordinal=1,
                        rights_basis="Synthetic owner-authored text",
                        third_party_rights="None in this synthetic section",
                        attribution="Synthetic owner; AI interpretation labelled",
                    ),
                ),
            ),
        ),
    )
    return conn, reg, data, frozen, approval


def remote(request, posts, response=None, unsafe=False):
    if request.method == "POST":
        posts.append(request)
        return response or httpx.Response(200, json=envelope())
    if request.url.path == "/api/v1/key":
        return httpx.Response(
            200,
            json={
                "data": {
                    "limit": 5,
                    "limit_reset": None,
                    "limit_remaining": 5,
                    "usage": 0,
                    "byok_usage": 0,
                    "is_management_key": False,
                }
            },
        )
    if request.url.path == "/api/v1/models":
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "anthropic/claude-opus-5.5",
                        "canonical_slug": "anthropic/claude-opus-5.5-20260921",
                    }
                ]
            },
        )
    entry = {
        "model_id": "anthropic/claude-opus-5.5",
        "tag": "google-vertex/europe",
        "provider_name": "Google",
        "status": 0,
        "safety_retention": unsafe,
        "supports_implicit_caching": False,
        "context_length": 1000000,
        "max_completion_tokens": 128000,
        "pricing": {"prompt": "0.0000044", "completion": "0.000022"},
        "supported_parameters": ["max_tokens", "response_format", "reasoning", "reasoning_effort"],
    }
    if request.url.path.endswith("/endpoints"):
        return httpx.Response(
            200, json={"data": {"id": "anthropic/claude-opus-5.5-20260921", "endpoints": [entry]}}
        )
    assert request.url.path == "/api/v1/endpoints/zdr"
    return httpx.Response(200, json={"data": [entry]})


def execute_fixture(tmp_path, *, change=None, response=None, unsafe=False):
    conn, reg, data, frozen, approval = setup_pilot(tmp_path)
    if change:
        approval = change(conn, data, frozen, approval)
    posts = []
    client = httpx.Client(
        transport=httpx.MockTransport(lambda req: remote(req, posts, response, unsafe))
    )
    return conn, reg, data, frozen, approval, posts, client


def test_frozen_subset_is_the_exact_transmitted_body_and_raw_response_is_private(tmp_path):
    conn, reg, data, frozen, approval, posts, client = execute_fixture(tmp_path)
    result = run(
        conn,
        reg,
        data,
        frozen,
        approval,
        data / "run",
        "synthetic-secret",
        client=client,
        now_fn=lambda: NOW,
    )
    assert len(posts) == 1
    assert posts[0].content == (frozen / "v1-request.json").read_bytes()
    assert b"UNLICENSED" not in posts[0].content
    assert b"Permitted synthetic economic text." in posts[0].content
    assert (data / "run/v1/request.json").read_bytes() == posts[0].content
    assert json.loads((data / "run/v1/response.bin").read_bytes())["id"] == "gen-synthetic-1"
    assert result[0].items[0].outcome == "invalid_output"
    assert conn.execute("SELECT review_status FROM research_summary").fetchone()[0] == "unreviewed"
    for p in (data / "run").rglob("*"):
        assert stat.S_IMODE(p.stat().st_mode) == (0o700 if p.is_dir() else 0o600)
    assert b"synthetic-secret" not in b"".join(
        p.read_bytes() for p in (data / "run").rglob("*") if p.is_file()
    )


@pytest.mark.parametrize(
    "change",
    [
        lambda c, d, f, a: a.model_copy(update={"state": "pending"}),
        lambda c, d, f, a: a.model_copy(update={"expires_at": NOW}),
        lambda c, d, f, a: a.model_copy(update={"rights": ()}),
        lambda c, d, f, a: a.model_copy(update={"gold_sha256": "0" * 64}),
        lambda c, d, f, a: ((f / "v1-request.json").write_text("{}"), a)[1],
        lambda c, d, f, a: (
            c.execute("UPDATE research_section SET heading='Changed' WHERE ordinal=0"),
            a,
        )[1],
    ],
)
def test_incomplete_or_changed_approval_refuses_before_any_inference_or_run_write(tmp_path, change):
    conn, reg, data, frozen, approval, posts, client = execute_fixture(tmp_path, change=change)
    with pytest.raises(pilot.PilotRefused):
        run(
            conn,
            reg,
            data,
            frozen,
            approval,
            data / "run",
            "synthetic-secret",
            client=client,
            now_fn=lambda: NOW,
        )
    assert not posts
    assert conn.execute("SELECT count(*) FROM research_llm_run").fetchone()[0] == 0


def test_privacy_change_blocks_inference(tmp_path):
    conn, reg, data, frozen, approval, posts, client = execute_fixture(tmp_path, unsafe=True)
    with pytest.raises(pilot.PilotRefused):
        run(
            conn,
            reg,
            data,
            frozen,
            approval,
            data / "run",
            "synthetic-secret",
            client=client,
            now_fn=lambda: NOW,
        )
    assert not posts


def test_malformed_actual_response_is_retained_without_retry_or_second_version_attempt(tmp_path):
    conn, reg, data, frozen, approval, posts, client = execute_fixture(
        tmp_path, response=httpx.Response(200, content=b"malformed SYNTHETIC response")
    )
    first = run(
        conn,
        reg,
        data,
        frozen,
        approval,
        data / "run",
        "synthetic-secret",
        client=client,
        now_fn=lambda: NOW,
    )
    assert first[0].items[0].outcome == "provider_error"
    assert (data / "run/v1/response.bin").read_bytes() == b"malformed SYNTHETIC response"
    with pytest.raises(pilot.PilotRefused):
        run(
            conn,
            reg,
            data,
            frozen,
            approval,
            data / "second",
            "synthetic-secret",
            client=client,
            now_fn=lambda: NOW,
        )
    assert len(posts) == 1


def test_freeze_refuses_rbnz_browser_chrome_and_unknown_versions(tmp_path):
    conn, reg, data, frozen, approval = setup_pilot(tmp_path)
    v2 = seed_version(conn, key="rbnz", doc="b")
    reg["rbnz"] = institution("rbnz")
    with pytest.raises(pilot.PilotRefused):
        pilot.freeze(conn, reg, {v2: (0, 1)}, data / "rbnz-bad")
    with pytest.raises(pilot.PilotRefused):
        pilot.freeze(conn, reg, {99: (1,)}, data / "unknown")


@pytest.mark.parametrize(
    "change",
    [
        {"limit_remaining": float("inf")},
        {"limit_remaining": 6},
        {"usage": -1},
        {"byok_usage": 1},
        {"limit_reset": "monthly"},
    ],
)
def test_invalid_or_unaccounted_key_metadata_refuses_before_inference(tmp_path, change):
    conn, reg, data, frozen, approval = setup_pilot(tmp_path)
    posts = []

    def handler(req):
        response = remote(req, posts)
        if req.url.path == "/api/v1/key":
            payload = response.json()
            payload["data"].update(change)
            # json.dumps permits non-finite values, which admission must reject.
            return httpx.Response(200, content=json.dumps(payload).encode())
        return response

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(pilot.PilotRefused):
            run(
                conn,
                reg,
                data,
                frozen,
                approval,
                data / "run",
                "synthetic-secret",
                client=client,
                now_fn=lambda: NOW,
            )
    assert not posts


def test_capture_failure_consumes_attempt_without_transmission(tmp_path):
    conn, reg, data, frozen, approval, posts, client = execute_fixture(tmp_path)
    # A pre-existing request capture must fail exclusively, never overwrite or send.
    original = pilot._write

    def fail_request(path, content):
        if path.name == "request.json":
            raise OSError("synthetic disk failure")
        return original(path, content)

    from unittest.mock import patch

    with patch.object(pilot, "_write", fail_request):
        result = run(
            conn,
            reg,
            data,
            frozen,
            approval,
            data / "run",
            "synthetic-secret",
            client=client,
            now_fn=lambda: NOW,
        )
    assert result[0].items[0].outcome == "provider_error"
    assert not posts
    with pytest.raises(pilot.PilotRefused):
        run(
            conn,
            reg,
            data,
            frozen,
            approval,
            data / "retry",
            "synthetic-secret",
            client=client,
            now_fn=lambda: NOW,
        )


def test_zdr_attestation_is_required_when_ordinary_endpoint_omits_optional_field(tmp_path):
    conn, reg, data, frozen, approval = setup_pilot(tmp_path)
    posts = []

    def handler(req):
        response = remote(req, posts)
        if req.url.path.endswith("/endpoints"):
            payload = response.json()
            del payload["data"]["endpoints"][0]["safety_retention"]
            return httpx.Response(200, json=payload)
        return response

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = run(
            conn,
            reg,
            data,
            frozen,
            approval,
            data / "run",
            "synthetic-secret",
            client=client,
            now_fn=lambda: NOW,
        )
    assert len(posts) == 1 and result[0].items[0].outcome == "invalid_output"


@pytest.mark.parametrize(
    "path", ["/api/v1/endpoints/zdr", "/api/v1/models/anthropic/claude-opus-5.5/endpoints"]
)
def test_missing_zdr_attestation_or_explicit_catalogue_conflict_refuses(tmp_path, path):
    conn, reg, data, frozen, approval = setup_pilot(tmp_path)
    posts = []

    def handler(req):
        response = remote(req, posts)
        if req.url.path == path:
            payload = response.json()
            entry = (
                payload["data"][0]
                if isinstance(payload["data"], list)
                else payload["data"]["endpoints"][0]
            )
            entry["safety_retention"] = None
            return httpx.Response(200, json=payload)
        return response

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(pilot.PilotRefused):
            run(
                conn,
                reg,
                data,
                frozen,
                approval,
                data / "run",
                "synthetic-secret",
                client=client,
                now_fn=lambda: NOW,
            )
    assert not posts


@pytest.mark.parametrize("status", [200, 500])
def test_upstream_credential_echo_is_redacted_and_never_stored_as_summary(tmp_path, status):
    response = httpx.Response(status, content=b"SYNTHETIC echoed Bearer synthetic-secret")
    conn, reg, data, frozen, approval, posts, client = execute_fixture(tmp_path, response=response)
    result = run(
        conn,
        reg,
        data,
        frozen,
        approval,
        data / "run",
        "synthetic-secret",
        client=client,
        now_fn=lambda: NOW,
    )
    captured = (data / "run/v1/response.bin").read_bytes()
    assert b"synthetic-secret" not in captured
    metadata = json.loads((data / "run/v1/response-status.json").read_text())
    assert metadata["credential_redacted"] is True
    assert result[0].items[0].error_class == (
        "credential_echo" if status == 200 else "server_error"
    )
    assert conn.execute("SELECT raw_output FROM research_summary").fetchone()[0] is None
    assert len(posts) == 1


@pytest.mark.parametrize("failure", ["timeout", "oversized"])
def test_received_response_prefix_survives_stream_failure_without_retry(tmp_path, failure):
    from nzstats.research.providers import MAX_RESPONSE_BYTES

    class Stream(httpx.SyncByteStream):
        def __iter__(self):
            yield b"SYNTHETIC received prefix"
            if failure == "timeout":
                raise httpx.ReadTimeout("Synthetic private failure detail")
            yield b"x" * MAX_RESPONSE_BYTES

    response = httpx.Response(200, stream=Stream())
    conn, reg, data, frozen, approval, posts, client = execute_fixture(tmp_path, response=response)
    result = run(
        conn,
        reg,
        data,
        frozen,
        approval,
        data / "run",
        "synthetic-secret",
        client=client,
        now_fn=lambda: NOW,
    )
    assert result[0].items[0].outcome == "provider_error"
    captured = (data / "run/v1/response.bin").read_bytes()
    assert captured.startswith(b"SYNTHETIC received prefix") and len(captured) <= MAX_RESPONSE_BYTES
    metadata = json.loads((data / "run/v1/response-status.json").read_text())
    assert metadata["complete"] is False
    assert metadata["truncated"] == (failure == "oversized")
    assert metadata["error_class"] == ("timeout" if failure == "timeout" else "response_too_large")
    assert len(posts) == 1


def test_model_alias_retargeting_cannot_use_the_existing_request_approval(tmp_path):
    conn, reg, data, frozen, approval = setup_pilot(tmp_path)
    posts = []

    def handler(req):
        response = remote(req, posts)
        if req.url.path == "/api/v1/models":
            payload = response.json()
            payload["data"][0]["canonical_slug"] = "anthropic/claude-opus-5.5-another-version"
            return httpx.Response(200, json=payload)
        return response

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(pilot.PilotRefused):
            run(
                conn,
                reg,
                data,
                frozen,
                approval,
                data / "run",
                "synthetic-secret",
                client=client,
                now_fn=lambda: NOW,
            )
    assert not posts
