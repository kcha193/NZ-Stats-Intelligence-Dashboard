"""Phase 4W fixtures: a synthetic Treasury world with one manually imported FEU version and a matching policy file.

SYNTHETIC FIXTURE. Nothing here is a Treasury document, a real licence, a real key or a real policy.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import timedelta
from pathlib import Path

from nzstats.research import store
from nzstats.research.policy import licence_sha256, verifier_sha256
from nzstats.research.prompt import RULES_SHA256
from nzstats.store.db import connect, migrate, transaction

from .llm_support import NOW
from .support import institution

SECTIONS = (
    "SYNTHETIC FIXTURE cover page. Fortnightly Economic Update.",
    "Activity is expected to grow 2.5% in the year to March 2027.",
    "Annual CPI inflation is forecast to fall to 2.1% in the year to June 2027.",
)


def registry(**over):
    raw = {
        "llm_processing": "hosted",
        "llm_processing_note": "synthetic test approval",
        "manual_import": "approved",
        "manual_import_approved_by": "Synthetic Owner",
        "manual_import_approved_on": "2026-10-31",
        "manual_import_note": "synthetic",
        "licence": "Synthetic licence text A",
        "licence_url": "https://example.org/licence",
        "review_status": "needs_review",
        "approved_by": None,
        "approved_on": None,
        "approval_note": None,
    }
    raw.update(over)
    return {"treasury": institution("treasury", **raw)}


def policy_dict(reg=None, **over):
    reg = reg or registry()
    base = {
        "policy_id": "treasury-feu-synthetic",
        "issued_by": "Synthetic Owner",
        "issued_on": "2026-10-26",
        "institution": "treasury",
        "series": "FEU",
        "document_scope": "one_call_per_document_version",
        "route": {
            "model": "anthropic/claude-opus-5.5",
            "provider_id": "google-vertex/europe",
            "zdr": True,
            "data_collection": "deny",
            "allow_fallbacks": False,
            "require_parameters": True,
            "reasoning_effort": "low",
            "max_output_tokens": 12000,
        },
        "prompt_version": "outlook-v6",
        "prompt_sha256": RULES_SHA256["outlook-v6"],
        "verifier_version": "verify-5",
        "verifier_sha256": verifier_sha256("verify-5"),
        "licence_sha256": licence_sha256(reg["treasury"]),
        "per_call_usd": 0.5,
        "aggregate_usd": 2.0,
        "max_calls": 4,
        "not_before": (NOW - timedelta(days=1)).isoformat(),
        "expires_at": (NOW + timedelta(days=29)).isoformat(),
    }
    base.update(over)
    return base


def write_policy(
    data: Path, body: dict | str | None = None, *, name="policy.json", mode=0o600
) -> Path:
    data.mkdir(parents=True, exist_ok=True)
    path = data / name
    text = body if isinstance(body, str) else json.dumps(policy_dict() if body is None else body)
    path.write_text(text)
    os.chmod(path, mode)
    return path


def world(
    tmp_path,
    *,
    sections=SECTIONS,
    series="FEU",
    acquisition="manual",
    doc="feu1",
    published_on="2026-10-29",
    reg=None,
    import_record=True,
    raw_ok=True,
    snapshot_licence=None,
):
    """(conn, registry, data_dir, version_id) with the raw file stored under its own hash."""
    data = tmp_path / "data"
    conn = connect(data / "nzstats.db")
    migrate(conn)
    reg = reg or registry()
    raw = ("\n".join(sections) + doc).encode()
    sha = hashlib.sha256(raw).hexdigest()
    if raw_ok:
        path = data / "raw" / sha[:2] / sha
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    snapshot = reg["treasury"].licence_snapshot()
    if snapshot_licence is not None:
        snapshot["licence"] = snapshot_licence
    with transaction(conn):
        inst = store.upsert_institution(
            conn, key="treasury", name="The Treasury", review_status="needs_review",
            content_policy="full_text", now=NOW,
        )  # fmt: skip
        pub, _ = store.upsert_publication(
            conn, inst, doc_key=f"treasury:research.example.org/{doc}", url=f"https://research.example.org/{doc}",
            title=f"Fortnightly Economic Update {doc}", series=series, categories=["economic_outlook"],
            published_on=published_on, published_at=None, precision="day",
            content_status="extracted", now=NOW,
        )  # fmt: skip
        rows, offset = [], 0
        for i, text in enumerate(sections):
            rows.append(store.SectionRow(i, None, text, i + 1, i + 1, offset, offset + len(text)))
            offset += len(text) + 1
        version, _ = store.add_version(
            conn, pub, content_sha256=sha, text_sha256=hashlib.sha256(raw + b"t").hexdigest(),
            fmt="pdf", fetched_at=NOW, extractor_version="pdf-1", raw_artifact_id=None,
            title=f"Fortnightly Economic Update {doc}", sections=rows, page_count=len(sections),
            licence_snapshot=json.dumps(snapshot), now=NOW, acquisition=acquisition,
        )  # fmt: skip
        if import_record and acquisition == "manual":
            conn.execute(
                "INSERT INTO research_manual_import(institution_id,url,publication_id,version_id,outcome,"
                "file_format,content_sha256,text_sha256,imported_by,note,licence_snapshot,imported_at)"
                " VALUES (?,?,?,?,'new','pdf',?,?,?,?,?,?)",
                (inst, f"https://research.example.org/{doc}", pub, version, sha, "t", "Synthetic Owner",
                 "synthetic provenance note", json.dumps(snapshot), NOW.isoformat()),
            )  # fmt: skip
    return conn, reg, data, version
