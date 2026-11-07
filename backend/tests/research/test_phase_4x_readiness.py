"""Phase 4X: the owner-approved Treasury hosted-processing entry (2026-11-08), exercised only on SYNTHETIC worlds.

The approved lines are read from docs/phase-4x-operational-readiness.md (between the approved-registry markers) and must appear
exactly once in config/research_sources.toml. The pre-approval baseline is that file with exactly those lines removed. No
network: the provider is an httpx.MockTransport and sockets are blocked for every test here. Nothing in this file reads or
writes the real database, raw files or policy.
"""

import hashlib
import json
import socket
import tomllib
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from nzstats.research import policy as pol
from nzstats.research import store
from nzstats.research import summary_store as ss
from nzstats.research.registry import LlmProcessing, PrivateDisplay, PublicDisplay, load_registry
from nzstats.store.db import transaction

from .llm_support import NOW, seed_version
from .policy_support import SECTIONS
from .test_pilot_treasury_v3 import spend
from .test_policy_run import Env, good_output, refused

ROOT = Path(__file__).resolve().parents[3]
REPORT = ROOT / "docs" / "phase-4x-operational-readiness.md"
REGISTRY = ROOT / "config" / "research_sources.toml"
START, END = "<!-- approved-registry:start -->", "<!-- approved-registry:end -->"
# The real ledger's shape (amounts and experiment tags), rebuilt on synthetic versions.
# The parsed registry (comments ignored) as it stood before the owner's 2026-11-08 approval, i.e. main `b5bf3c1`. Removing the two
# approved lines must give back exactly this; any other registry change is a separate reviewed decision that updates this pin.
PRE_APPROVAL_SHA256 = "7ad56e93fb0005b1fbc057ccaaf0f5803b1968af2b79cd71a3be44b6d76628f5"
REAL_LEDGER = ((None, 0.1798984440), (None, 0.2023797600), ("phase-4n-second-pilot", 0.1261846080),
               ("phase-4s-treasury-v3", 0.1182479760))  # fmt: skip


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("a Phase 4X readiness test tried to open a network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def approved_lines() -> str:
    text = REPORT.read_text(encoding="utf-8")
    block = text[text.index(START) + len(START) : text.index(END)]
    return block.split("```toml\n", 1)[1].split("```", 1)[0]


def pre_approval_registry(tmp_path):
    """The shipped registry with exactly the two approved Treasury lines removed."""
    text = REGISTRY.read_text(encoding="utf-8")
    assert text.count(approved_lines()) == 1
    path = tmp_path / "pre_approval_research_sources.toml"
    before = text.replace(approved_lines(), "")
    parsed = json.dumps(tomllib.loads(before), sort_keys=True, default=str).encode()
    assert hashlib.sha256(parsed).hexdigest() == PRE_APPROVAL_SHA256, (
        "registry changed beyond the two approved lines"
    )
    path.write_text(before, encoding="utf-8")
    return load_registry(path)


def import_feu(env, doc, *, raw=None, text_sha=None):
    """Store one more manually imported SYNTHETIC FEU in the env's world, as `world` does. Returns (version, change)."""
    sections = (f"SYNTHETIC FIXTURE cover page {doc}.", *SECTIONS[1:])
    raw = raw if raw is not None else ("\n".join(sections) + doc).encode()
    sha = hashlib.sha256(raw).hexdigest()
    path = env.data / "raw" / sha[:2] / sha
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    snapshot = json.dumps(env.reg["treasury"].licence_snapshot())
    (inst,) = env.conn.execute(
        "SELECT id FROM research_institution WHERE key='treasury'"
    ).fetchone()
    with transaction(env.conn):
        pub, _ = store.upsert_publication(
            env.conn, inst, doc_key=f"treasury:research.example.org/{doc}", url=f"https://research.example.org/{doc}",
            title=f"Fortnightly Economic Update {doc}", series="FEU", categories=["economic_outlook"],
            published_on="2026-11-12", published_at=None, precision="day", content_status="extracted", now=NOW,
        )  # fmt: skip
        rows, offset = [], 0
        for i, text in enumerate(sections):
            rows.append(store.SectionRow(i, None, text, i + 1, i + 1, offset, offset + len(text)))
            offset += len(text) + 1
        version, change = store.add_version(
            env.conn, pub, content_sha256=sha, text_sha256=text_sha or hashlib.sha256(raw + b"t").hexdigest(),
            fmt="pdf", fetched_at=NOW, extractor_version="pdf-1", raw_artifact_id=None,
            title=f"Fortnightly Economic Update {doc}", sections=rows, page_count=len(sections),
            licence_snapshot=snapshot, now=NOW, acquisition="manual",
        )  # fmt: skip
        if change == "new":
            env.conn.execute(
                "INSERT INTO research_manual_import(institution_id,url,publication_id,version_id,outcome,"
                "file_format,content_sha256,text_sha256,imported_by,note,licence_snapshot,imported_at)"
                " VALUES (?,?,?,?,'new','pdf',?,?,?,?,?,?)",
                (inst, f"https://research.example.org/{doc}", pub, version, sha, "t", "Synthetic Owner",
                 "synthetic provenance note", snapshot, NOW.isoformat()),
            )  # fmt: skip
    return version, change


def approved_env(tmp_path):
    """A synthetic world governed by the shipped (approved) Treasury entry."""
    reg = load_registry(REGISTRY)
    return Env(tmp_path, reg={"treasury": reg["treasury"]}, content=json.dumps(good_output(1)))


def run_on(env, version):
    env.version, env.content = version, json.dumps(good_output(version))
    return env.go()


# --- the approved entry itself -----------------------------------------------------------------------------------------------
def test_only_treasury_is_hosted_and_every_other_source_stays_denied():
    reg = load_registry(REGISTRY)
    assert reg["treasury"].llm_processing is LlmProcessing.HOSTED
    assert all(i.llm_processing is LlmProcessing.DENIED for k, i in reg.items() if k != "treasury")


def test_the_approval_added_only_the_two_llm_keys_and_keeps_the_policy_licence_pin(tmp_path):
    assert set(tomllib.loads(approved_lines())) == {"llm_processing", "llm_processing_note"}
    assert "2026-11-08" in approved_lines() and "<YYYY-MM-DD>" not in approved_lines()
    before, after = pre_approval_registry(tmp_path), load_registry(REGISTRY)
    assert before["treasury"].llm_processing is LlmProcessing.DENIED
    old, new = before["treasury"], after["treasury"]
    assert new.llm_processing is LlmProcessing.HOSTED and new.llm_processing_note
    # Every other Treasury field (acquisition, review, licence, display, hosts, discovery) is as before.
    assert (
        replace(old, llm_processing=new.llm_processing, llm_processing_note=new.llm_processing_note)
        == new
    )
    # A policy issued before the change stays valid: its pin covers the licence and its address only.
    assert pol.licence_sha256(new) == pol.licence_sha256(old)
    changed = {k for k, v in new.licence_snapshot().items() if old.licence_snapshot()[k] != v}
    assert changed == {"llm_processing"}
    # Acquisition and display are untouched: the crawler stays refused and nothing becomes visible.
    assert new.refusal_reason() == old.refusal_reason() is not None
    assert new.display_level("manual") is PublicDisplay.NONE
    assert new.private_display_level("manual") is PrivateDisplay.NONE
    # RBNZ and every other source are unchanged.
    assert all(after[k] == before[k] for k in before if k != "treasury")


# --- a new report under the proposal ------------------------------------------------------------------------------------------
def test_a_new_synthetic_feu_is_eligible_and_one_confirmed_run_makes_one_mocked_request(tmp_path):
    env = approved_env(tmp_path)
    pf = env.pre()
    assert pf.eligible and pf.refusal_codes == () and not env.posts and not env.gets
    env.go()
    assert len(env.posts) == 1 and env.attempts() == 1
    (summary,) = env.conn.execute(
        "SELECT prompt_version, verifier_version, review_status FROM research_summary"
    ).fetchall()
    assert tuple(summary) == ("outlook-v6", "verify-5", "unreviewed")


def test_the_same_report_again_is_refused_whether_re_saved_renamed_or_re_imported(tmp_path):
    env = approved_env(tmp_path)
    first = env.version
    env.go()
    sha, text = env.conn.execute(
        "SELECT content_sha256, text_sha256 FROM research_document_version WHERE id=?", (first,)
    ).fetchone()
    raw = (env.data / "raw" / sha[:2] / sha).read_bytes()
    # Re-imported at its own address with the same text: the stored, attempted version comes back unchanged.
    again, change = import_feu(env, "feu1", raw=raw + b" re-saved", text_sha=text)
    assert (again, change) == (first, "unchanged")
    assert refused(lambda: run_on(env, again)) == "version_attempted"
    # The same bytes under a new address and version row: still the attempted content.
    twin, change = import_feu(env, "feu1-renamed", raw=raw)
    assert change == "new" and twin != first
    env.version = twin
    assert "content_already_attempted" in env.pre().refusal_codes
    assert refused(lambda: run_on(env, twin)) == "content_already_attempted"
    assert len(env.posts) == 1


def test_on_the_real_ledger_shape_v3_is_refused_and_exactly_four_new_reports_can_run(tmp_path):
    env = approved_env(tmp_path)
    v2 = seed_version(env.conn, sections=("SYNTHETIC rbnz-shaped",), key="rbnz", doc="rbnz-shaped")
    v1 = seed_version(env.conn, sections=("SYNTHETIC v1-shaped",), key="treasury", doc="v1-shaped")
    # A manually imported FEU that used its one attempt in Phase 4S.
    v3, _ = import_feu(env, "v3-shaped")
    for version, (experiment, cost) in zip((v2, v1, v1, v3), REAL_LEDGER, strict=True):
        spend(env.conn, version, experiment, cost=cost)
    assert round(ss.lifetime_spent(env.conn), 10) == 0.6267107880
    env.version = v3
    assert "version_attempted" in env.pre().refusal_codes
    posts = 0
    for i in range(4):
        version, _ = import_feu(env, f"new{i}")
        env.version = version
        assert env.pre().eligible, f"new report {i} should be eligible"
        run_on(env, version)
        posts += 1
        assert len(env.posts) == posts
    fifth, _ = import_feu(env, "new4")
    env.version = fifth
    codes = env.pre().refusal_codes
    assert "policy_calls_exhausted" in codes
    assert refused(lambda: run_on(env, fifth)) in {
        "policy_calls_exhausted",
        "lifetime_attempts_exhausted",
    }
    assert len(env.posts) == 4
    # Older experiments keep the original ceiling of 4: none can spend again however many slots policies have.
    fresh = seed_version(env.conn, sections=("SYNTHETIC unused",), key="treasury", doc="unused")
    rid = ss.start_run(
        env.conn, provider="openrouter", model="anthropic/claude-opus-5.5", hosted=True, prompt_version="outlook-v4",
        processing_version="3b-1", limits={"experiment": "phase-4n-second-pilot"}, dry_run=False, now=NOW,
    )  # fmt: skip
    held = ss.reserve(
        env.conn, run_id=rid, version_id=fresh, call_no=1, provider="openrouter", model="anthropic/claude-opus-5.5",
        amount_usd=0.3, period_cap_usd=5, since=NOW - timedelta(days=30), now=NOW, expires_at=NOW + timedelta(hours=1),
        scope=ss.PilotScope("phase-4n-second-pilot", max_attempts=2, max_usd=1.0),
    )  # fmt: skip
    assert held is None
    assert ss.lifetime_spent(env.conn) <= ss.LIFETIME_USD
