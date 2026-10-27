"""Phase 3C doubles: a displayable synthetic institution and stored, reviewed, published summaries (SYNTHETIC FIXTURE)."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from nzstats.research import summary_store as ss
from nzstats.research.contract import ModelProvenance, assemble, parse_draft
from nzstats.research.registry import Institution
from nzstats.research.summarise import load_sections
from nzstats.research.verify import VERIFIER_VERSION, verify
from nzstats.store.db import transaction

from .llm_support import NOW, draft
from .support import institution

DISPLAY = {
    "public_display_approved_by": "Test Reviewer",
    "public_display_approved_on": "2026-10-26",
    "public_display_note": "synthetic test source: display permitted",
}


def displayable(key: str = "example", level: str = "excerpt", **overrides: Any) -> Institution:
    raw: dict[str, Any] = {"llm_processing": "local_only", "llm_processing_note": "synthetic",
                           "public_display": level, **DISPLAY}  # fmt: skip
    raw.update(overrides)
    return institution(key, **raw)


def registry(*institutions: Institution) -> dict[str, Institution]:
    return {i.key: i for i in (institutions or (displayable(),))}


def store_summary(
    conn: sqlite3.Connection,
    version_id: int,
    *,
    output: dict[str, Any] | None = None,
    review: str | None = "approved",
    publish: bool = True,
    prompt_version: str = "outlook-v2",
    model: str = "fake-1",
) -> int:
    """A summary of `version_id` stored exactly as the pipeline would, then reviewed and published."""
    data = output if output is not None else draft(version_id)
    provenance = ModelProvenance(
        provider="fake", model=model, prompt_version=prompt_version, processing_version="3b-1",
        parameters={}, input_text_sha256="a" * 64, created_at=NOW,
    )  # fmt: skip
    summary = assemble(parse_draft(json.dumps(data)), version_id=version_id, provenance=provenance)
    report = verify(summary, load_sections(conn, version_id))
    key = ss.SummaryKey(version_id, "fake", model, prompt_version, "3b-1", "a" * 64)
    run = ss.start_run(conn, provider="fake", model=model, hosted=False, prompt_version=prompt_version,
                       processing_version="3b-1", limits={}, dry_run=False, now=NOW)  # fmt: skip
    status = "verified" if report.passed else "failed_verification"
    with transaction(conn):
        sid = ss.insert_summary(
            conn, key, run_id=run, attempt=ss.next_attempt(conn, key), hosted=False,
            verifier_version=VERIFIER_VERSION, parameters={"temperature": 0},
            raw_output="RAW MODEL OUTPUT (private)", output_json=summary.model_dump_json(), status=status,
            error_class=None, verification=report.to_json(), now=NOW,
        )  # fmt: skip
        if status == "verified":
            ss.insert_claims(conn, sid, summary.forecasts)
    if review:
        ss.review(conn, sid, decision=review, reviewer="Private Reviewer Name",
                  note="PRIVATE REVIEW NOTE" if review == "rejected" else None, now=NOW)  # fmt: skip
    if publish:
        ss.record_publication(conn, sid, decision="publish", approver="Private Approver",
                              note="PRIVATE PUBLICATION NOTE", now=NOW)  # fmt: skip
    return sid
