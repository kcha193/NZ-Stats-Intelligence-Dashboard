"""Phase 4W command handlers: `run-policy`, `policy-init`, `policy-audit` and `policy-revoke`.

Imported lazily by `research/cli.py` only when one of these commands runs, so `nzstats serve`, the scheduler and every API
route never load the module that can make a paid request. Output is codes, counts and metadata: no source text, request
body, model output or key.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import signal
import sqlite3
import sys
from datetime import timedelta
from pathlib import Path

from nzstats.clock import utc_now
from nzstats.config import Settings
from nzstats.research import diagnostics, pilot
from nzstats.research import policy as pol
from nzstats.research import policy_run as run
from nzstats.research.registry import Institution
from nzstats.research.summary_store import LIFETIME_ATTEMPTS, LIFETIME_USD, lifetime_spent

API_KEY_ENV = "NZSTATS_LLM_API_KEY"


_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def _out(text: str = "") -> None:
    """Print lines with non-ASCII escaped and terminal control characters removed (a title is import metadata)."""
    for line in str(text).split("\n"):
        print(_CONTROL.sub("", line.encode("ascii", "backslashreplace").decode()))


def _terminate(signum, frame):  # noqa: ARG001
    raise KeyboardInterrupt  # a closed terminal or SIGTERM unwinds through execute_policy, which audits the interruption


def _ordinals(text: str | None) -> tuple[int, ...] | None:
    if text is None:
        return None
    try:
        values = tuple(int(part) for part in text.split(","))
    except ValueError:
        raise pol.PolicyRefused("section_scope_invalid") from None
    return tuple(sorted(set(values)))


def _path(settings: Settings, text: str) -> Path:
    path = Path(text)
    return path if path.is_absolute() else Path.cwd() / path


def run_policy(
    args: argparse.Namespace, settings: Settings, registry: dict[str, Institution]
) -> int:
    policy_path = _path(settings, args.policy)
    try:
        ordinals = _ordinals(args.sections)
        if args.dry_run:
            return _dry_run(settings, registry, policy_path, args.version, ordinals)
        return _execute(settings, registry, policy_path, args.version, args.confirm, ordinals)
    except pol.PolicyRefused as exc:
        _out(f"Refused: {exc.code}. Nothing was requested or reserved.")
        return 2
    except pilot.PilotRefused as exc:
        _out(
            f"Refused by the pilot preflight: {exc}. No automatic retry; inspect local state before proceeding."
        )
        return 2


def _dry_run(settings, registry, policy_path: Path, version: int, ordinals) -> int:
    policy, sha = pol.load_policy(policy_path, settings.data_dir)
    if not settings.db_path.exists():
        raise pol.PolicyRefused("database_missing")
    conn = diagnostics.open_readonly(settings.db_path)
    try:
        pf = run.preflight(
            conn,
            registry,
            policy,
            sha,
            version,
            settings.data_dir,
            now=utc_now(),
            ordinals=ordinals,
        )
    finally:
        conn.close()
    _out(run.render_preflight(pf))
    return 0 if pf.eligible else 2


def _execute(settings, registry, policy_path: Path, version: int, confirm: str, ordinals) -> int:
    interactive = (
        sys.stdin.isatty() and sys.stdout.isatty()
    )  # execute_policy refuses, and logs it, when this is False
    if not settings.db_path.exists():
        raise pol.PolicyRefused("database_missing")
    conn = sqlite3.connect(str(settings.db_path), timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    for sig in (signal.SIGHUP, signal.SIGTERM):
        signal.signal(sig, _terminate)
    try:
        result = run.execute_policy(
            conn, registry, settings.data_dir, policy_path, version, confirm=confirm, interactive=interactive,
            ask=_ask, api_key=os.environ.get(API_KEY_ENV, ""), ordinals=ordinals,
        )  # fmt: skip
    finally:
        conn.close()
    _out(
        f"One request reserved. Outcome: {result.outcome}; automated checks: {result.errors} errors,"
        f" {result.warnings} warnings; cost US${result.cost_usd:.4f}."
    )
    if result.summary_id is None:
        _out(
            "No output was retained. The reservation and its cost remain in the audit and lifetime ledger."
        )
    else:
        _out(
            "The result is an unreviewed internal draft. It is shown only through the internal-draft gate, with its checks."
        )
    _out("No automatic retry. This document version cannot be run again under any policy.")
    return 0


def _ask(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError:
        return ""


def policy_init(
    args: argparse.Namespace, settings: Settings, registry: dict[str, Institution]
) -> int:
    inst = registry.get(pol.POLICY_INSTITUTION)
    if inst is None:
        _out("Refused: the Treasury is not in the research registry.")
        return 2
    now = utc_now()
    body = {
        "policy_id": args.policy_id,
        "issued_by": args.issued_by,
        "issued_on": now.date().isoformat(),
        "institution": pol.POLICY_INSTITUTION,
        "series": pol.POLICY_SERIES,
        "document_scope": "one_call_per_document_version",
        "route": {
            "model": pilot.MODEL, "provider_id": pilot.ROUTE, "zdr": True, "data_collection": "deny",
            "allow_fallbacks": False, "require_parameters": True, "reasoning_effort": "low",
            "max_output_tokens": pol.MAX_OUTPUT_TOKENS,
        },
        "prompt_version": "outlook-v6",
        "prompt_sha256": pol.RULES_SHA256["outlook-v6"],
        "verifier_version": "verify-5",
        "verifier_sha256": pol.verifier_sha256("verify-5"),
        "licence_sha256": pol.licence_sha256(inst),
        "per_call_usd": args.per_call_usd,
        "aggregate_usd": args.aggregate_usd,
        "max_calls": args.max_calls,
        "not_before": now.isoformat(),
        "expires_at": (now + timedelta(days=args.days)).isoformat(),
    }  # fmt: skip
    try:
        policy = pol.InferencePolicy.model_validate_json(
            json.dumps(body)
        )  # strict: parsed as the loader parses
    except ValueError:
        _out("Refused: those values are outside the policy ceilings.")
        return 2
    out = _path(settings, args.out)
    if not out.resolve().is_relative_to(settings.data_dir.resolve()):
        _out("Refused: a policy file must be created under the data directory.")
        return 2
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except OSError:
        _out("Refused: that file already exists or cannot be created.")
        return 2
    with os.fdopen(fd, "w") as stream:
        json.dump(json.loads(policy.model_dump_json()), stream, indent=2, sort_keys=True)
    _out(f"Wrote {out} (mode 0600), policy hash {pol.policy_sha256(policy)[:8]}.")
    _out(
        "This authorises nothing. Review it, then run `research run-policy ... --dry-run` for a document."
    )
    return 0


def policy_audit(
    args: argparse.Namespace, settings: Settings, registry: dict[str, Institution]
) -> int:
    if not settings.db_path.exists():
        _out("Refused: there is no database to read.")
        return 2
    conn = diagnostics.open_readonly(settings.db_path)
    try:
        attempts = conn.execute(
            "SELECT COUNT(*) FROM research_llm_reservation WHERE provider='openrouter'"
        ).fetchone()[0]
        _out(
            f"Lifetime ledger: {attempts} of {LIFETIME_ATTEMPTS} attempts used (policy scopes may use the last"
            f" {pol.POLICY_MAX_CALLS}); US${lifetime_spent(conn):.10f} of US${LIFETIME_USD:.2f} spent."
        )
        if (
            conn.execute(
                "SELECT 1 FROM sqlite_master WHERE name='research_policy_event'"
            ).fetchone()
            is None
        ):
            _out("Policy audit: not created yet (run `nzstats migrate`).")
            return 0
        rows = pol.audit_rows(conn)
        _out(f"Policy audit: {len(rows)} events (append-only).")
        for r in rows:
            detail = r["refusal_code"] or r["outcome"] or ""
            cost = f" US${r['cost_usd']:.4f}" if r["cost_usd"] is not None else ""
            _out(
                f"  #{r['id']:<3} {r['created_at'][:19]} {r['event']:<8} policy {r['policy_sha256'][:8]}"
                f" ({r['policy_id']}) version {r['version_id'] or '-'} {detail}{cost} by {r['operator']}"
            )
        unreconciled = conn.execute(
            "SELECT x.id, x.version_id FROM research_llm_reservation x JOIN research_llm_run r ON r.id = x.run_id"
            " WHERE json_extract(r.limits, '$.experiment') LIKE 'policy-%' AND NOT EXISTS ("
            " SELECT 1 FROM research_policy_event e WHERE e.event='executed' AND e.run_id = x.run_id)"
        ).fetchall()
        for r in unreconciled:
            _out(
                f"  ATTENTION: reservation {r['id']} (version {r['version_id']}) has no audit row."
            )
        return 1 if unreconciled else 0
    finally:
        conn.close()


def policy_revoke(
    args: argparse.Namespace, settings: Settings, registry: dict[str, Institution]
) -> int:
    try:
        return _revoke(args, settings)
    except pol.PolicyRefused as exc:
        _out(f"Refused: {exc.code}. Nothing was changed.")
        return 2


def _revoke(args: argparse.Namespace, settings: Settings) -> int:
    policy, sha = pol.load_policy(_path(settings, args.policy), settings.data_dir)
    if not settings.db_path.exists():
        raise pol.PolicyRefused("database_missing")
    conn = sqlite3.connect(str(settings.db_path), timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        if not pol.audit_ready(conn):
            raise pol.PolicyRefused("database_not_migrated")
        pol.record_event(
            conn,
            "revoked",
            policy,
            sha,
            operator=getpass.getuser(),
            now=utc_now(),
            detail=args.reason[:200],
        )
    finally:
        conn.close()
    _out(f"Policy {policy.policy_id} ({sha[:8]}) revoked. It can never run again.")
    return 0
