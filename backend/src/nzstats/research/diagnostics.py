"""Phase 4V: offline, read-only diagnosis and replay of a stored summary.

Takes the useful, general parts of the Phase 4U forensic script and makes them reviewed, tested tooling. For one stored summary it
re-runs the verifier it was stored with and a proposed one, and reports, claim by claim, which errors each raises, where the
cited evidence sits, which errors share one root cause, and what changed between the two.

- The database is opened read-only. Nothing is written, migrated or re-graded: the stored verification is only compared.
- The model data carries codes, claim ids and evidence *locations*. Claim text and quotes are present only when the caller asks
  (`with_text=True`), so a default report or JSON cannot leak document or model text to a terminal or an assistant.
- A label is a rule-computed proposal. Nothing is ever labelled valid: an error the rules cannot settle stays a conservative failure,
  and a lower error count is not evidence of better economics (see `Replay.NOTICE`).
"""

from __future__ import annotations

import html
import os
import re
import sqlite3
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from nzstats.research import verify as V
from nzstats.research.contract import OutlookSummary
from nzstats.research.evaluate import REF_CODES
from nzstats.research.prompt import injection_findings
from nzstats.research.summarise import load_sections

LABELS = (
    "resolved_by_proposed",  # raised by the baseline verifier, not by the proposed one
    "cascade",  # a guaranteed consequence of another error on the same claim
    "contract_limitation",  # the figure carries a unit the contract cannot express
    "conservative_failure",  # a rule that fails closed; rules cannot say whether the claim is true
    "unsupported_by_stored_evidence",  # the stored text does not support it, by a rule (not a human reading)
)
# When no sentence passes the decision-wording rule, `PolicyDecision` checking has nothing to test: these follow deterministically
# (see `_RecordChecker.decision`). The date error follows only when the claimed date is not in the nearby text, so it is "possible".
CASCADE_ROOT = "decision_not_in_evidence"
CASCADE_GUARANTEED = frozenset(
    {
        "decision_instrument_not_supported",
        "decision_rate_not_supported",
        "decision_action_not_supported",
    }
)
CASCADE_POSSIBLE = frozenset({"decision_date_not_supported"})
# Rules that fail closed on wording they cannot settle. Whether the claim is true is not decided here.
CONSERVATIVE = frozenset({"period_not_supported", "forecast_as_fact", CASCADE_ROOT})
_FOREIGN_MARKER = re.compile(
    r"\b(?:US|A|C|HK|S)\$|\bUSD\b|\bAUD\b|\bCAD\b|\bEUR\b|\bGBP\b|[€£¥]|\bUS\s+dollars?\b"
)
_COLLECTIONS = ("drivers", "risks", "forecasts", "facts", "decisions", "guidance", "assumptions")
_KIND = {"facts": "fact", "decisions": "decision", "forecasts": "forecast", "guidance": "guidance",
         "assumptions": "assumption"}  # fmt: skip
NOTICE = (
    "A new assessment computed offline from stored output, for diagnosis. The stored verification is unchanged and is not replaced"
    " by this page. The checks locate quotes, numbers, units, periods and wording in the stored text; this page does not test the"
    " economics. A smaller error count is not evidence that a claim is correct, and no claim here is labelled valid."
)


class DiagnosticError(RuntimeError):
    """The summary cannot be diagnosed. The message never includes stored text."""


@dataclass(frozen=True)
class EvidenceSite:
    """Where a claim's quote sits in the stored section text. No text."""

    section: int
    page: int | None
    start: int | None
    end: int | None
    sentence: int | None


@dataclass(frozen=True)
class ClaimView:
    path: str
    kind: str
    baseline_errors: tuple[str, ...]
    proposed_errors: tuple[str, ...]
    baseline_warnings: tuple[str, ...]
    proposed_warnings: tuple[str, ...]
    evidence: tuple[EvidenceSite, ...]
    text: str | None = None  # only with `with_text`
    quotes: tuple[str, ...] = ()  # only with `with_text`


@dataclass(frozen=True)
class Finding:
    path: str
    code: str
    label: str
    in_baseline: bool
    in_proposed: bool


@dataclass(frozen=True)
class Cluster:
    root: str
    path: str
    guaranteed: tuple[str, ...]
    possible: tuple[str, ...]


@dataclass(frozen=True)
class VersionResult:
    version: str
    n_errors: int
    n_warnings: int
    errors: Counter[str]
    warnings: Counter[str]
    problems: tuple[tuple[str, str, str], ...]  # (path, code, severity)
    claims_total: int
    claims_failed: int
    claims_warning: int
    claims_clean: int
    citation_errors: int

    def to_json(self) -> dict[str, Any]:
        return {"version": self.version, "errors": self.n_errors, "warnings": self.n_warnings,
                "error_codes": dict(self.errors), "warning_codes": dict(self.warnings),
                "claims": {"total": self.claims_total, "failed": self.claims_failed,
                           "warning": self.claims_warning, "clean": self.claims_clean},
                "citation_errors": self.citation_errors}  # fmt: skip


@dataclass(frozen=True)
class Replay:
    summary_id: int
    version_id: int
    institution: str
    status: str
    stored_verifier: str
    stored_reproduced: bool
    output_hash_ok: bool
    baseline: VersionResult
    proposed: VersionResult
    newly_accepted: tuple[str, ...]
    newly_rejected: tuple[str, ...]
    findings: tuple[Finding, ...]
    clusters: tuple[Cluster, ...]
    claims: tuple[ClaimView, ...]
    notice: str = NOTICE

    @property
    def root_causes_baseline(self) -> int:
        """Errors that are not guaranteed consequences of another: the number of independent things to look at."""
        guaranteed = sum(
            len(c.guaranteed)
            for c in cascade_clusters(
                [
                    (path, code)
                    for path, code, severity in self.baseline.problems
                    if severity == "error"
                ]
            )
        )
        return self.baseline.n_errors - guaranteed

    def to_json(self) -> dict[str, Any]:
        return {
            "summary_id": self.summary_id, "version_id": self.version_id, "institution": self.institution,
            "status": self.status, "stored_verifier": self.stored_verifier,
            "stored_reproduced": self.stored_reproduced, "output_hash_ok": self.output_hash_ok,
            "baseline": self.baseline.to_json(), "proposed": self.proposed.to_json(),
            "newly_accepted": list(self.newly_accepted), "newly_rejected": list(self.newly_rejected),
            "root_causes_baseline": self.root_causes_baseline,
            "findings": [{"path": f.path, "code": f.code, "label": f.label, "in_baseline": f.in_baseline,
                          "in_proposed": f.in_proposed} for f in self.findings],
            "clusters": [{"root": c.root, "path": c.path, "guaranteed": list(c.guaranteed),
                          "possible": list(c.possible)} for c in self.clusters],
            "claims": [{"path": c.path, "kind": c.kind, "baseline_errors": list(c.baseline_errors),
                        "proposed_errors": list(c.proposed_errors),
                        "evidence": [vars(e) for e in c.evidence],
                        **({"text": c.text, "quotes": list(c.quotes)} if c.text is not None else {})}
                       for c in self.claims],
            "notice": self.notice,
        }  # fmt: skip


def open_readonly(path: str | os.PathLike[str]) -> sqlite3.Connection:
    """The database opened `mode=ro`: this module cannot create, migrate or modify it."""
    uri = f"{Path(path).resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def cascade_clusters(problems: Iterable[tuple[str, str]]) -> tuple[Cluster, ...]:
    """Group errors by root cause from codes alone. A cascade code without its root on the same claim is its own cause."""
    by_path: dict[str, set[str]] = {}
    for path, code in problems:
        by_path.setdefault(path, set()).add(code)
    return tuple(
        Cluster(
            CASCADE_ROOT,
            path,
            tuple(sorted(codes & CASCADE_GUARANTEED)),
            tuple(sorted(codes & CASCADE_POSSIBLE)),
        )
        for path, codes in by_path.items()
        if CASCADE_ROOT in codes
    )


def _kind(path: str) -> str:
    return _KIND.get(path.split("[")[0], "statement")


def _one(conn: sqlite3.Connection, sql: str, params: Sequence[Any]) -> dict[str, Any] | None:
    cursor = conn.execute(sql, params)
    row = cursor.fetchone()
    return None if row is None else dict(zip((d[0] for d in cursor.description), row, strict=True))


def _claims(summary: OutlookSummary) -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = [("outlook", summary.outlook)]
    for name in _COLLECTIONS:
        out += [(f"{name}[{i}]", item) for i, item in enumerate(getattr(summary, name))]
    if summary.uncertainty is not None:
        out.append(("uncertainty", summary.uncertainty))
    return out


def _site(ref: Any, sections: dict[int, Any]) -> EvidenceSite:
    section = sections.get(ref.section_ordinal)
    start = section.text.find(ref.quote) if section is not None else -1
    if start < 0:
        return EvidenceSite(ref.section_ordinal, ref.page, None, None, None)
    sentence = next(
        (i for i, (a, b) in enumerate(V._sentences(section.text)) if a <= start < b), None
    )
    return EvidenceSite(ref.section_ordinal, ref.page, start, start + len(ref.quote), sentence)


def _result(report: V.VerificationReport, claim_paths: Sequence[str]) -> VersionResult:
    problems = tuple((p.path, p.code, p.severity) for p in (*report.errors, *report.warnings))
    failed = {p.path for p in report.errors}
    warned = {p.path for p in report.warnings} - failed
    return VersionResult(
        version=report.version, n_errors=len(report.errors), n_warnings=len(report.warnings),
        errors=Counter(p.code for p in report.errors), warnings=Counter(p.code for p in report.warnings),
        problems=problems, claims_total=len(claim_paths),
        claims_failed=sum(p in failed for p in claim_paths), claims_warning=sum(p in warned for p in claim_paths),
        claims_clean=sum(p not in failed and p not in warned for p in claim_paths),
        citation_errors=sum(p.code in REF_CODES for p in report.errors),
    )  # fmt: skip


def _label(
    code: str, path: str, quotes: Sequence[str], root_paths: set[str], resolved: bool
) -> str:
    if resolved:
        return "resolved_by_proposed"
    if path in root_paths and code in CASCADE_GUARANTEED | CASCADE_POSSIBLE:
        return "cascade"
    if code in {"missing_unit", "unknown_unit"} and any(_FOREIGN_MARKER.search(q) for q in quotes):
        return "contract_limitation"
    if code in CONSERVATIVE:
        return "conservative_failure"
    return "unsupported_by_stored_evidence"


def replay_summary(
    conn: sqlite3.Connection,
    summary_id: int,
    *,
    baseline: str | None = None,
    proposed: str = V.VERIFIER_VERSION,
    with_text: bool = False,
) -> Replay:
    """Re-verify one stored summary under `baseline` (default: the verifier it was stored with) and `proposed`. Writes nothing."""
    row = _one(
        conn,
        "SELECT s.id, s.version_id, s.status, s.verifier_version, s.output_json, s.raw_output, s.output_sha256,"
        " s.verification, p.published_on, i.key AS institution FROM research_summary s"
        " JOIN research_document_version v ON v.id = s.version_id"
        " JOIN research_publication p ON p.id = v.publication_id"
        " JOIN research_institution i ON i.id = p.institution_id WHERE s.id = ?",
        (summary_id,),
    )
    if row is None or not row["output_json"]:
        raise DiagnosticError(f"no stored summary {summary_id} with output")
    stored_label = row["verifier_version"] or ""
    baseline = baseline or V.resolve_verifier(stored_label)
    for name in (baseline, proposed):
        if name not in V._VERSION_FEATURES:
            raise DiagnosticError(f"unknown verifier version {name!r}")
    try:
        summary = OutlookSummary.model_validate_json(row["output_json"])
    except ValueError as exc:
        raise DiagnosticError(f"the stored output does not parse ({type(exc).__name__})") from exc
    sections = load_sections(conn, row["version_id"])
    published = date.fromisoformat(row["published_on"]) if row["published_on"] else None
    ctx = V.VerificationContext(published_on=published, institution=row["institution"],
                                injection_ordinals=tuple(injection_findings(sections)))  # fmt: skip
    claims = _claims(summary)
    paths = [path for path, _ in claims]
    old, new = (V.verify(summary, sections, ctx, version=v) for v in (baseline, proposed))
    rerun = V.verify(summary, sections, ctx, version=V.resolve_verifier(stored_label))
    stored = _stored_pairs(row["verification"])
    reproduced = stored is not None and stored == (
        Counter((p.code, p.path) for p in rerun.errors),
        Counter((p.code, p.path) for p in rerun.warnings),
    )
    digest_ok = row["raw_output"] is not None and _sha(row["raw_output"]) == row["output_sha256"]
    base, prop = _result(old, paths), _result(new, paths)
    failed_old, failed_new = {p.path for p in old.errors}, {p.path for p in new.errors}
    quotes = {path: [e.quote for e in getattr(item, "evidence", ())] for path, item in claims}
    err_old, err_new = (
        {(p.path, p.code) for p in old.errors},
        {(p.path, p.code) for p in new.errors},
    )
    roots = {c.path for c in cascade_clusters(err_new)}
    findings = tuple(
        Finding(path, code, _label(code, path, quotes.get(path, ()), roots, (path, code) not in err_new),
                (path, code) in err_old, (path, code) in err_new)
        for path, code in sorted(err_old | err_new)
    )  # fmt: skip
    views = []
    for path, item in claims:
        evidence = tuple(_site(r, sections) for r in getattr(item, "evidence", ()))
        text = getattr(item, "text", None) if with_text else None
        views.append(ClaimView(
            path, _kind(path),
            tuple(sorted(p.code for p in old.errors if p.path == path)),
            tuple(sorted(p.code for p in new.errors if p.path == path)),
            tuple(sorted(p.code for p in old.warnings if p.path == path)),
            tuple(sorted(p.code for p in new.warnings if p.path == path)),
            evidence, text, tuple(quotes[path]) if with_text else (),
        ))  # fmt: skip
    return Replay(
        summary_id=row["id"], version_id=row["version_id"], institution=row["institution"], status=row["status"],
        stored_verifier=stored_label, stored_reproduced=reproduced, output_hash_ok=digest_ok,
        baseline=base, proposed=prop,
        newly_accepted=tuple(p for p in paths if p in failed_old and p not in failed_new),
        newly_rejected=tuple(p for p in paths if p in failed_new and p not in failed_old),
        findings=findings, clusters=cascade_clusters(err_old), claims=tuple(views),
    )  # fmt: skip


def _sha(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode()).hexdigest()


def _stored_pairs(
    verification: str | None,
) -> tuple[Counter[tuple[str, str]], Counter[tuple[str, str]]] | None:
    import json

    if not verification:
        return None
    try:
        data = json.loads(verification)
        return (
            Counter((p["code"], p["path"]) for p in data["errors"]),
            Counter((p["code"], p["path"]) for p in data["warnings"]),
        )
    except (ValueError, KeyError, TypeError):
        return None


# --- the page -----------------------------------------------------------------------------------------------------
_CSS = (
    "body{font:14px/1.45 system-ui,sans-serif;margin:24px;max-width:1100px;color:#1b1f23;background:#fff}"
    "table{border-collapse:collapse;margin:8px 0 20px;width:100%}th,td{border:1px solid #c9ced4;padding:4px 8px;text-align:left;"
    "vertical-align:top}th{background:#f1f3f5}code{font-family:ui-monospace,monospace}.note{background:#fff7e0;border:1px solid #e0c060;"
    "padding:8px 12px}.ok{color:#136f3a}.bad{color:#a4262c}@media(prefers-color-scheme:dark){body{background:#14161a;color:#e6e8eb}"
    "th{background:#22262b}th,td{border-color:#3a3f45}.note{background:#3a3220;border-color:#7a6a30}}"
)


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


def _site_text(site: EvidenceSite) -> str:
    if site.start is None:
        return f"s{site.section} p{site.page or '-'} (quote not located)"
    return f"s{site.section} p{site.page or '-'} chars {site.start}-{site.end} sentence {site.sentence}"


def render_html(replay: Replay) -> str:
    """One self-contained local page: no script, no network resource, nothing but escaped text."""
    rows = [
        ("Summary", replay.summary_id), ("Document version", replay.version_id), ("Institution", replay.institution),
        ("Stored status", replay.status), ("Stored verifier", replay.stored_verifier or "(none)"),
        ("Stored verification reproduced", "yes" if replay.stored_reproduced else "NO"),
        ("Output hash intact", "yes" if replay.output_hash_ok else "NO"),
    ]  # fmt: skip
    identity = "".join(f"<tr><th>{_e(k)}</th><td>{_e(v)}</td></tr>" for k, v in rows)
    totals = "".join(
        f"<tr><th>{_e(label)}</th><td>{_e(getattr(replay.baseline, attr))}</td><td>{_e(getattr(replay.proposed, attr))}</td></tr>"
        for label, attr in (
            ("Errors", "n_errors"),
            ("Warnings", "n_warnings"),
            ("Claims failed", "claims_failed"),
            ("Claims with warnings only", "claims_warning"),
            ("Claims clean", "claims_clean"),
            ("Citation errors", "citation_errors"),
        )  # fmt: skip
    )
    codes = sorted(set(replay.baseline.errors) | set(replay.proposed.errors))
    by_code = "".join(
        f"<tr><td><code>{_e(c)}</code></td><td>{replay.baseline.errors.get(c, 0)}</td>"
        f"<td>{replay.proposed.errors.get(c, 0)}</td></tr>" for c in codes
    )  # fmt: skip
    claim_rows = "".join(
        f"<tr><td><code>{_e(c.path)}</code></td><td>{_e(c.kind)}</td>"
        f"<td>{_e('; '.join(_site_text(s) for s in c.evidence) or '-')}</td>"
        f"<td>{_e(', '.join(c.baseline_errors) or '-')}</td><td>{_e(', '.join(c.proposed_errors) or '-')}</td>"
        f"<td>{_e(', '.join(f.label for f in replay.findings if f.path == c.path) or '-')}</td>"
        + (f"<td>{_e(c.text or '')}<br>{'<br>'.join(_e(q) for q in c.quotes)}</td>" if c.text is not None else "")
        + "</tr>"
        for c in replay.claims
        if c.baseline_errors or c.proposed_errors or c.baseline_warnings or c.proposed_warnings
    )  # fmt: skip
    has_text = any(c.text is not None for c in replay.claims)
    cluster_rows = "".join(
        f"<tr><td><code>{_e(c.path)}</code></td><td><code>{_e(c.root)}</code></td>"
        f"<td>{_e(', '.join(c.guaranteed) or '-')}</td><td>{_e(', '.join(c.possible) or '-')}</td></tr>"
        for c in replay.clusters
    )  # fmt: skip
    finding_rows = "".join(
        f"<tr><td><code>{_e(f.path)}</code></td><td><code>{_e(f.code)}</code></td><td>{_e(f.label)}</td>"
        f"<td>{'yes' if f.in_baseline else 'no'}</td><td>{'yes' if f.in_proposed else 'no'}</td></tr>"
        for f in replay.findings
    )  # fmt: skip
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'\">"
        '<meta name="robots" content="noindex"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>Offline diagnostic, summary {_e(replay.summary_id)}</title><style>{_CSS}</style></head><body>"
        f'<h1>Offline diagnostic: summary {_e(replay.summary_id)}</h1><p class="note">{_e(replay.notice)}</p>'
        f"<p>{_e(V.SCOPE)}</p><h2>Identity and integrity</h2><table>{identity}</table>"
        f"<h2>Before and after</h2><table><tr><th></th><th>{_e(replay.baseline.version)} (baseline)</th>"
        f"<th>{_e(replay.proposed.version)} (proposed)</th></tr>{totals}</table>"
        f"<p>Claims newly accepted: {_e(', '.join(replay.newly_accepted) or 'none')}. "
        f"Claims newly rejected: {_e(', '.join(replay.newly_rejected) or 'none')}. "
        f"Independent root causes in the baseline: {_e(replay.root_causes_baseline)} of {_e(replay.baseline.n_errors)} errors.</p>"
        f"<h2>Error codes</h2><table><tr><th>Code</th><th>{_e(replay.baseline.version)}</th><th>{_e(replay.proposed.version)}</th></tr>"
        f"{by_code}</table><h2>Root-cause clusters</h2><table><tr><th>Claim</th><th>Root</th><th>Guaranteed cascade</th>"
        f"<th>Possible cascade</th></tr>{cluster_rows}</table>"
        f"<h2>Findings</h2><table><tr><th>Claim</th><th>Code</th><th>Label</th><th>In baseline</th><th>In proposed</th></tr>"
        f"{finding_rows}</table><h2>Claims with a problem</h2><table><tr><th>Claim</th><th>Kind</th><th>Evidence location</th>"
        f"<th>Baseline errors</th><th>Proposed errors</th><th>Labels</th>{'<th>Text</th>' if has_text else ''}</tr>"
        f"{claim_rows}</table></body></html>"
    )


def write_report(path: Path, page: str) -> None:
    """Write the page owner-only. The caller picks a path under the ignored data directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(page)
    os.chmod(path, 0o600)
