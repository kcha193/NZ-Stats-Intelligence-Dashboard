"""Read-only presentation assessment, separate from the original verification.

No verdict is stored or relabelled. Identity binds the exact parsed output, original
response hash, evidence, verification rules and context. Passing these checks is
not a finding of economic accuracy.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from nzstats.research import verify as verifier
from nzstats.research.contract import OutlookSummary
from nzstats.research.diagnostics import claim_path
from nzstats.research.drafts import DraftClaim, DraftSummary, _civil_date, claim_paths
from nzstats.research.summarise import load_sections

SCHEMA_VERSION = "presentation-1"
# Explicit pin: a future default verifier must not silently change the presentation.
PRESENTATION_VERIFIER = "verify-5"


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def classify_claims(
    summary: OutlookSummary, report: verifier.VerificationReport
) -> tuple[DraftClaim, ...]:
    """Map nested findings exactly. An error outside known claims excludes all highlights."""
    paths = claim_paths(summary)
    claims = []
    for path in paths:
        problems = tuple(
            p
            for p in (*report.errors, *report.warnings)
            if claim_path(p.path) == path or claim_path(p.path) not in paths
        )
        status = (
            "failed"
            if any(p.severity == "error" for p in problems)
            else "warning"
            if problems
            else "clean"
        )
        claims.append(DraftClaim(path, status, problems))
    return tuple(claims)


@dataclass(frozen=True)
class Assessment:
    id: str
    assessed_at: str
    original_output_hash: str
    evidence_hash: str
    errors: int
    draft: DraftSummary


def assess(conn: sqlite3.Connection, draft: DraftSummary) -> Assessment | None:
    """Reassess a gate-eligible draft without writes, network requests or stored-verdict changes."""
    raw, recorded_hash = conn.execute(
        "SELECT raw_output, output_sha256 FROM research_summary WHERE id = ?", (draft.id,)
    ).fetchone()
    if raw is None or hashlib.sha256(raw.encode()).hexdigest() != recorded_hash:
        return None
    sections = load_sections(conn, draft.summary.version_id)
    evidence_hash = _digest({str(k): asdict(v) for k, v in sections.items()})
    context = verifier.VerificationContext(
        published_on=_civil_date(draft.row["published_on"]), institution=draft.row["institution"]
    )
    report = verifier.verify(draft.summary, sections, context, version=PRESENTATION_VERIFIER)
    claims = classify_claims(draft.summary, report)
    identity = _digest(
        {
            "schema": SCHEMA_VERSION,
            "summary_id": draft.id,
            "output_hash": recorded_hash,
            "parsed_output": draft.summary.model_dump(mode="json"),
            "evidence_hash": evidence_hash,
            "verifier": PRESENTATION_VERIFIER,
            "rules_hash": hashlib.sha256(Path(verifier.__file__).read_bytes()).hexdigest(),
            "context": {
                "published_on": str(context.published_on),
                "institution": context.institution,
            },
            "problems": [asdict(p) for p in (*report.errors, *report.warnings)],
        }
    )
    return Assessment(
        id=f"{SCHEMA_VERSION}:{identity}",
        assessed_at=datetime.now(UTC).isoformat(),
        original_output_hash=recorded_hash,
        evidence_hash=evidence_hash,
        errors=len(report.errors),
        draft=replace(draft, passed=report.passed, warnings=len(report.warnings), claims=claims),
    )
