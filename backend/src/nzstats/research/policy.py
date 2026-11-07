"""Phase 4W: operator-run inference policy. Offline: nothing here imports a provider or contacts a network.

A policy is a small JSON file in the private data directory that narrows what one operator-run command may do: one
institution and series, one call per document version, a route, pinned prompt and verifier, per-call and aggregate caps and
a window of at most 30 days. It is a set of limits the code enforces, **never evidence**: the file cannot grant a source
permission, assert that rights or account controls are genuine, or raise a ceiling. Every eligibility check reads the
reviewed registry, the stored document or an append-only record. The ceilings below are code constants (changing one is a
reviewed code change), and a file can only be stricter.

Two independent records decide what was spent: the reservation ledger (migration 009) and the policy audit (migration 014).
Usage is the larger of the two, so retagging a run or renaming a document restores nothing.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import stat
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError, model_validator

from nzstats.clock import to_utc_iso
from nzstats.research import verify as verify_module
from nzstats.research.contract import SectionText
from nzstats.research.hosted import section_inventory_sha256
from nzstats.research.prompt import RULES_SHA256
from nzstats.research.registry import ContentPolicy, Institution
from nzstats.research.summary_store import (
    LIFETIME_ATTEMPTS,
    LIFETIME_USD,
    POLICY_MAX_ATTEMPTS,
    POLICY_MAX_USD,
    POLICY_PREFIX,
    lifetime_spent,
    version_attempts,
)

# --- ceilings (code constants: a file can only be stricter) -----------------------------------------------------------
POLICY_MAX_CALLS = POLICY_MAX_ATTEMPTS  # 4
POLICY_MAX_PER_CALL_USD = 0.50
POLICY_MAX_AGGREGATE_USD = POLICY_MAX_USD
POLICY_MAX_DAYS = 30
POLICY_INSTITUTION = "treasury"
POLICY_SERIES = "FEU"  # the Fortnightly Economic Update, as the manual import stores it
POLICY_PROMPTS = frozenset({"outlook-v6"})
POLICY_VERIFIERS = frozenset({"verify-5"})
TIMEOUT_SECONDS = 300.0
MAX_OUTPUT_TOKENS = 12_000  # equal to openrouter.MAX_OUTPUT_TOKENS (a test checks it); policy.py imports no provider

# Explicit rights tripwires on a section's own text. A tripwire, not a legal review: it keeps flagged sections out of the
# request and the operator still confirms, at the terminal, that they read the document's own notices.
THIRD_PARTY_NOTICE = re.compile(
    r"©|\(c\)\s*\d{4}|copyright\s+(?:held|owned|belongs)|non[- ]crown|third[- ]party\s+(?:material|content|copyright)"
    r"|(?:reproduced|used|published)\s+(?:with|by)\s+(?:the\s+)?(?:kind\s+)?permission|all\s+rights\s+reserved",
    re.IGNORECASE,
)


class PolicyRefused(ValueError):
    """A fixed, content-free refusal with a stable code. Never carries document text."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


Hex64 = Field(pattern=r"^[0-9a-f]{64}$")


class PolicyRoute(_Strict):
    """The reviewed route, matched exactly. None of these may be relaxed."""

    model: Literal["anthropic/claude-opus-5.5"]
    provider_id: Literal["google-vertex/europe"]
    zdr: Literal[True]
    data_collection: Literal["deny"]
    allow_fallbacks: Literal[False]
    require_parameters: Literal[True]
    reasoning_effort: Literal["low", "medium"]
    max_output_tokens: StrictInt = Field(ge=1, le=MAX_OUTPUT_TOKENS)


class InferencePolicy(_Strict):
    policy_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,60}$")
    issued_by: str = Field(min_length=1)
    issued_on: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    institution: Literal["treasury"]
    series: Literal["FEU"]
    document_scope: Literal["one_call_per_document_version"]
    route: PolicyRoute
    prompt_version: str
    prompt_sha256: str = Hex64
    verifier_version: str
    verifier_sha256: str = Hex64
    licence_sha256: str = Hex64
    per_call_usd: float = Field(gt=0, le=POLICY_MAX_PER_CALL_USD)
    aggregate_usd: float = Field(gt=0, le=POLICY_MAX_AGGREGATE_USD)
    max_calls: StrictInt = Field(ge=1, le=POLICY_MAX_CALLS)
    not_before: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def _bounded(self) -> InferencePolicy:
        if (
            self.prompt_version not in POLICY_PROMPTS
            or self.verifier_version not in POLICY_VERIFIERS
        ):
            raise ValueError("prompt or verifier not in the reviewed set")
        if self.aggregate_usd < self.per_call_usd:
            raise ValueError("aggregate below one call")
        if self.not_before.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("window needs timezones")
        if (
            not self.not_before
            < self.expires_at
            <= self.not_before + timedelta(days=POLICY_MAX_DAYS)
        ):
            raise ValueError("window must be positive and at most 30 days")
        return self


def canonical(policy: InferencePolicy) -> bytes:
    return json.dumps(
        policy.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode()


def policy_sha256(policy: InferencePolicy) -> str:
    return hashlib.sha256(canonical(policy)).hexdigest()


def verifier_sha256(version: str) -> str:
    """A fingerprint of the verifier code: the sha256 of verify.py. Any edit to it is a new pin and so a new policy."""
    if version not in POLICY_VERIFIERS:
        raise PolicyRefused("verifier_pin_mismatch")
    return hashlib.sha256(Path(verify_module.__file__).read_bytes()).hexdigest()


def licence_sha256(inst: Institution) -> str:
    """The licence terms a policy relies on: only the licence text and its address, not approvals that may change."""
    snap = inst.licence_snapshot()
    return _licence_digest(snap)


def _licence_digest(snapshot: object) -> str:
    snap = snapshot if isinstance(snapshot, dict) else {}
    body = json.dumps(
        {"licence": snap.get("licence"), "licence_url": snap.get("licence_url")}, sort_keys=True
    )
    return hashlib.sha256(body.encode()).hexdigest()


def scope_name(sha: str) -> str:
    """The ledger scope a policy spends in. `policy_run` derives its experiment from this name and the policy's own caps."""
    return f"{POLICY_PREFIX}{sha[:16]}"


def load_sections(conn: sqlite3.Connection, version_id: int) -> dict[int, SectionText]:
    return {
        int(r["ordinal"]): SectionText(r["text"], r["page_start"], r["page_end"], r["heading"])
        for r in conn.execute(
            "SELECT ordinal, heading, text, page_start, page_end FROM research_section"
            " WHERE version_id=? ORDER BY ordinal",
            (version_id,),
        )
    }


def load_policy(path: Path, data_dir: Path) -> tuple[InferencePolicy, str]:
    """Parse a policy file and verify its pins. The file must be a private regular file inside the data directory."""
    try:
        info = os.lstat(path)
    except OSError:
        raise PolicyRefused("policy_file_missing") from None
    if stat.S_ISLNK(info.st_mode):
        raise PolicyRefused("policy_file_symlink")
    if not stat.S_ISREG(info.st_mode):
        raise PolicyRefused("policy_file_unreadable")
    if info.st_mode & 0o077:
        raise PolicyRefused("policy_file_not_private")
    if not path.resolve().is_relative_to(data_dir.resolve()):
        raise PolicyRefused("policy_file_outside_data")
    try:
        policy = InferencePolicy.model_validate_json(path.read_bytes())
    except (UnicodeDecodeError, OSError):
        raise PolicyRefused("policy_file_unreadable") from None
    except ValidationError as exc:
        unreadable = any(e["type"] == "json_invalid" for e in exc.errors())
        raise PolicyRefused("policy_file_unreadable" if unreadable else "policy_invalid") from None
    if policy.prompt_sha256 != RULES_SHA256.get(policy.prompt_version):
        raise PolicyRefused("prompt_pin_mismatch")
    if policy.verifier_sha256 != verifier_sha256(policy.verifier_version):
        raise PolicyRefused("verifier_pin_mismatch")
    return policy, policy_sha256(policy)


# --- checks --------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Check:
    code: str
    ok: bool
    detail: str = ""


def window_check(policy: InferencePolicy, now: datetime) -> Check:
    if now < policy.not_before:
        return Check("policy_not_yet_valid", False)
    if now >= policy.expires_at:
        return Check("policy_expired", False)
    return Check("policy_window", True)


@dataclass(frozen=True)
class Capacity:
    checks: tuple[Check, ...]
    calls_used: int
    spent_usd: float
    lifetime_attempts_used: int
    lifetime_spent_usd: float

    @property
    def failures(self) -> tuple[Check, ...]:
        return tuple(c for c in self.checks if not c.ok)


@dataclass(frozen=True)
class SourceAssessment:
    version_id: int
    checks: tuple[Check, ...]
    title: str = ""
    published_on: str | None = None
    version_no: int | None = None
    content_sha256: str = ""
    sections_sha256: str = ""
    ordinals: tuple[int, ...] = ()
    excluded: tuple[int, ...] = ()
    page_range: tuple[int | None, int | None] = (None, None)

    @property
    def failures(self) -> tuple[Check, ...]:
        return tuple(c for c in self.checks if not c.ok)


def _file_sha256(path: Path) -> str | None:
    try:
        if path.is_symlink() or not path.is_file():
            return None
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1 << 20), b""):
                digest.update(block)
        return digest.hexdigest()
    except OSError:
        return None


def content_attempted(
    conn: sqlite3.Connection, content_sha256: str, *, exclude_version: int | None = None
) -> bool:
    """Whether any version carrying this exact content has a ledger attempt: a re-import cannot restore a spent one."""
    row = conn.execute(
        "SELECT 1 FROM research_llm_reservation x JOIN research_document_version v ON v.id = x.version_id"
        " WHERE x.provider='openrouter' AND v.content_sha256=? AND (? IS NULL OR v.id != ?) LIMIT 1",
        (content_sha256, exclude_version, exclude_version),
    ).fetchone()
    return row is not None


def audit_ready(conn: sqlite3.Connection) -> bool:
    """Whether migration 014 is applied. A dry run on an older database reports it instead of failing."""
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_policy_event'"
        ).fetchone()
        is not None
    )


def _executed_content(conn: sqlite3.Connection, content_sha256: str) -> bool:
    if not audit_ready(conn):
        return (
            False  # the missing table is its own refusal (`database_not_migrated`), never a crash
        )
    return (
        conn.execute(
            "SELECT 1 FROM research_policy_event WHERE event='executed' AND content_sha256=?",
            (content_sha256,),
        ).fetchone()
        is not None
    )


def assess_source(
    conn: sqlite3.Connection,
    registry: dict[str, Institution],
    policy: InferencePolicy,
    sha: str,
    version_id: int,
    data_dir: Path,
    *,
    ordinals: tuple[int, ...] | None = None,
) -> SourceAssessment:
    """Every source-side eligibility check, all evaluated so a refusal can list every reason. Read-only."""
    row = conn.execute(
        "SELECT v.id, v.version_no, v.title, v.content_sha256, v.acquisition, v.purged_at, v.superseded_at,"
        " v.licence_snapshot, p.series, p.published_on, p.current_version_id, p.duplicate_of_id, i.key"
        " FROM research_document_version v JOIN research_publication p ON p.id = v.publication_id"
        " JOIN research_institution i ON i.id = p.institution_id WHERE v.id=?",
        (version_id,),
    ).fetchone()
    if row is None:
        return SourceAssessment(version_id, (Check("version_not_found", False),))
    checks: list[Check] = []

    def check(code: str, ok: bool) -> None:
        checks.append(Check(code, ok))

    inst = registry.get(row["key"])
    check("institution_mismatch", row["key"] == policy.institution)
    check("series_mismatch", row["series"] == policy.series)
    check(
        "source_permission_refused",
        inst is not None
        and inst.holds(row["acquisition"])
        and inst.content_policy is ContentPolicy.FULL_TEXT,
    )
    check(
        "llm_processing_denied",
        inst is not None and inst.llm_refusal(hosted=True, acquisition=row["acquisition"]) is None,
    )
    check(
        "version_not_current",
        row["current_version_id"] == version_id
        and row["superseded_at"] is None
        and row["duplicate_of_id"] is None,
    )
    check("version_purged", row["purged_at"] is None)
    if row["acquisition"] == "manual":
        record = conn.execute(
            "SELECT 1 FROM research_manual_import WHERE version_id=? AND content_sha256=?"
            " AND length(trim(imported_by)) > 0 AND length(trim(note)) > 0",
            (version_id, row["content_sha256"]),
        ).fetchone()
        check("acquisition_provenance_missing", record is not None)
    else:
        check(
            "acquisition_provenance_missing", True
        )  # crawler versions are covered by the raw-file check
    raw = data_dir / "raw" / row["content_sha256"][:2] / row["content_sha256"]
    sections = load_sections(conn, version_id)
    check("source_text_unavailable", bool(sections) and _file_sha256(raw) == row["content_sha256"])
    try:
        stored_licence = json.loads(row["licence_snapshot"] or "{}")
    except ValueError:
        stored_licence = None
    check(
        "licence_changed",
        inst is not None
        and policy.licence_sha256 == licence_sha256(inst) == _licence_digest(stored_licence),
    )
    check("version_attempted", version_attempts(conn, version_id) == 0)
    check(
        "content_already_attempted",
        not content_attempted(conn, row["content_sha256"], exclude_version=version_id),
    )
    check("content_already_executed", not _executed_content(conn, row["content_sha256"]))
    flagged = tuple(n for n, s in sections.items() if THIRD_PARTY_NOTICE.search(s.text))
    eligible = tuple(n for n in sections if n not in flagged)
    chosen = eligible if ordinals is None else tuple(sorted(set(ordinals)))
    check("section_scope_invalid", bool(chosen) and all(n in sections for n in chosen))
    check("third_party_content", not any(n in flagged for n in chosen))
    check("no_eligible_sections", bool(eligible))
    pages = [sections[n] for n in chosen if n in sections]
    starts = [s.page_start for s in pages if s.page_start is not None]
    ends = [s.page_end for s in pages if s.page_end is not None]
    return SourceAssessment(
        version_id,
        tuple(c for c in checks if not c.ok) or (Check("source_eligible", True),),
        title=row["title"],
        published_on=row["published_on"],
        version_no=row["version_no"],
        content_sha256=row["content_sha256"],
        sections_sha256=section_inventory_sha256(sections) if sections else "",
        ordinals=chosen if all(n in sections for n in chosen) else (),
        excluded=flagged,
        page_range=(min(starts) if starts else None, max(ends) if ends else None),
    )


# --- usage, capacity, audit ------------------------------------------------------------------------------------------------
def policy_usage(conn: sqlite3.Connection, sha: str) -> tuple[int, float]:
    """(calls, USD) this policy has used: the larger of the reservation ledger and the policy audit."""
    name = scope_name(sha)
    cost = "CASE WHEN x.state='settled' THEN x.actual_usd ELSE x.reserved_usd END"
    ledger = conn.execute(
        f"SELECT COUNT(*), COALESCE(SUM({cost}), 0) FROM research_llm_reservation x"
        " JOIN research_llm_run r ON r.id = x.run_id"
        " WHERE x.provider='openrouter' AND json_extract(r.limits, '$.experiment') = ?",
        (name,),
    ).fetchone()
    audit = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(COALESCE(cost_usd, reserved_usd, 0)), 0) FROM research_policy_event"
        " WHERE policy_sha256=? AND event='executed'",
        (sha,),
    ).fetchone()
    return max(int(ledger[0]), int(audit[0])), max(float(ledger[1]), float(audit[1]))


def is_revoked(conn: sqlite3.Connection, sha: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM research_policy_event WHERE policy_sha256=? AND event='revoked'", (sha,)
        ).fetchone()
        is not None
    )


def capacity_checks(
    conn: sqlite3.Connection, policy: InferencePolicy, sha: str, worst_usd: float
) -> Capacity:
    """Caps and ceilings for one more call costing at most `worst_usd`, from the ledger and the audit."""
    calls, spent = policy_usage(conn, sha)
    attempts = int(
        conn.execute(
            "SELECT COUNT(*) FROM research_llm_reservation WHERE provider='openrouter'"
        ).fetchone()[0]
    )
    total = lifetime_spent(conn)
    eps = 1e-9
    checks = (
        Check("policy_revoked", not is_revoked(conn, sha)),
        Check("per_call_cap_exceeded", worst_usd <= policy.per_call_usd + eps),
        Check("policy_calls_exhausted", calls < policy.max_calls),
        Check("policy_budget_exhausted", spent + worst_usd <= policy.aggregate_usd + eps),
        Check("lifetime_attempts_exhausted", attempts < LIFETIME_ATTEMPTS),
        Check("lifetime_budget_exhausted", total + worst_usd <= LIFETIME_USD + eps),
    )
    return Capacity(checks, calls, spent, attempts, total)


_EVENT_FIELDS = (
    "version_id", "content_sha256", "request_sha256", "model", "provider_id", "prompt_version", "prompt_sha256",
    "verifier_version", "verifier_sha256", "attempt_no", "outcome", "summary_id", "run_id", "reserved_usd",
    "cost_usd", "input_tokens", "output_tokens", "errors", "warnings", "refusal_code", "detail",
)  # fmt: skip


def record_event(
    conn: sqlite3.Connection,
    event: Literal["refused", "executed", "revoked"],
    policy: InferencePolicy,
    sha: str,
    *,
    operator: str,
    now: datetime,
    **fields: object,
) -> int:
    """Append one audit row. Metadata only; the table has no column for text, output or credentials."""
    unknown = set(fields) - set(_EVENT_FIELDS)
    if unknown:
        raise ValueError("unknown audit field")
    columns = ["event", "policy_id", "policy_sha256", "operator", "created_at", *fields]
    values = [
        event,
        policy.policy_id,
        sha,
        operator,
        to_utc_iso(now.astimezone(UTC)),
        *fields.values(),
    ]
    cur = conn.execute(
        f"INSERT INTO research_policy_event({','.join(columns)}) VALUES ({','.join('?' * len(columns))})",
        values,
    )
    return int(cur.lastrowid)


def audit_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM research_policy_event ORDER BY id").fetchall()
