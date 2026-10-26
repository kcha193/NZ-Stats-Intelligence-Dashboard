"""`nzstats research ...`: sources, discovery, ingestion, health, and LLM summaries with review.

Nothing here runs on a schedule: every request is a deliberate command. A refused source makes no
request at all, and the refusal names the reason. Summaries need an explicitly configured provider
(`NZSTATS_LLM_*`) and a source whose `llm_processing` permits it; model text is printed with control
characters escaped and is labelled as interpretation, not an official statistic.
"""

from __future__ import annotations

import argparse
import json
import os

from nzstats.clock import to_akl_iso, utc_now
from nzstats.config import Settings
from nzstats.research import summary_store as ss
from nzstats.research.contract import Provider
from nzstats.research.fetch import ResearchFetcher, build_research_client, research_pacer
from nzstats.research.ingest import RunResult, refusal_for, run_institution
from nzstats.research.providers import (
    LlmConfigError,
    LlmSettings,
    build_provider,
    load_llm_settings,
)
from nzstats.research.registry import Institution, RegistryError, load_registry
from nzstats.research.summarise import summarise_versions
from nzstats.research.verify import SCOPE
from nzstats.sources.artifacts import ArtifactStore
from nzstats.store.db import connect, migrate


def _positive_int(text: str) -> int:
    number = int(text)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def add_research_parser(sub: argparse._SubParsersAction) -> None:
    research = sub.add_parser("research", help="institutional economic research sources (Phase 3A)")
    rsub = research.add_subparsers(dest="research_command", required=True)
    rsub.add_parser("sources", help="list registered institutions and their access status")
    p_disc = rsub.add_parser("discover", help="discovery-only dry run (no documents are fetched)")
    p_disc.add_argument("key")
    p_ing = rsub.add_parser("ingest", help="ingest one approved institution")
    p_ing.add_argument("key")
    p_ing.add_argument("--limit", type=_positive_int, help="at most this many documents")
    p_ing.add_argument("--dry-run", action="store_true", help="discover only; write nothing")
    rsub.add_parser("status", help="show research source health")
    p_sum = rsub.add_parser("summarise", help="summarise stored versions with the configured LLM")
    p_sum.add_argument("key", nargs="?", help="one institution (default: every permitted one)")
    p_sum.add_argument("--version", type=_positive_int, action="append", default=[],
                       help="a specific document version id (repeatable)")  # fmt: skip
    p_sum.add_argument("--limit", type=_positive_int, help="at most this many documents")
    p_sum.add_argument(
        "--dry-run", action="store_true", help="estimate cost; call and write nothing"
    )
    p_list = rsub.add_parser("summaries", help="list stored summaries")
    p_list.add_argument("--status", choices=("verified", "failed_verification", "invalid_output",
                                             "provider_error"))  # fmt: skip
    p_list.add_argument("--review", choices=("unreviewed", "approved", "rejected"))
    p_show = rsub.add_parser("summary", help="inspect one summary with its evidence and checks")
    p_show.add_argument("id", type=_positive_int)
    for name, help_text in (
        ("approve", "approve a verified summary"),
        ("reject", "reject a summary"),
    ):
        p_rev = rsub.add_parser(name, help=help_text)
        p_rev.add_argument("id", type=_positive_int)
        p_rev.add_argument("--reviewer", required=True)
        p_rev.add_argument("--note", required=name == "reject")


def build_fetcher(inst: Institution, settings: Settings) -> ResearchFetcher:
    return ResearchFetcher(
        inst,
        build_research_client(settings.user_agent),
        pacer=research_pacer(settings.data_dir, inst),
    )


def build_llm_provider(settings: LlmSettings) -> Provider:
    return build_provider(settings)


def research_command(args: argparse.Namespace, settings: Settings) -> int:
    try:
        registry = load_registry()
    except RegistryError as exc:
        print(f"research registry error: {exc}")
        return 2
    if args.research_command in _SUMMARY_COMMANDS:
        return _SUMMARY_COMMANDS[args.research_command](args, settings, registry)
    if args.research_command == "sources":
        print(f"{'key':<12} {'review':<13} {'policy':<14} {'llm':<11} {'verified':<11} access")
        for inst in registry.values():
            access = inst.refusal_reason() or "allowed"
            verified = inst.verified_on.isoformat() if inst.verified_on else "-"
            print(f"{inst.key:<12} {inst.review_status.value:<13} {inst.content_policy.value:<14}"
                  f" {inst.llm_processing.value:<11} {verified:<11} {access}")  # fmt: skip
        return 0
    if args.research_command == "status":
        return _status(settings, registry)
    inst = registry.get(args.key)
    if inst is None:
        print(f"unknown institution {args.key!r}; see `nzstats research sources`")
        return 2
    dry_run = args.research_command == "discover" or args.dry_run
    reason = refusal_for(inst, dry_run=dry_run)
    if reason is not None:  # before any client exists, so nothing can be requested
        print(f"{inst.key}: refused ({reason})")
        return 1
    conn = connect(settings.db_path)
    migrate(conn)
    result = run_institution(
        conn,
        inst,
        build_fetcher(inst, settings),
        artifacts=ArtifactStore(settings.raw_dir),
        dry_run=dry_run,
        limit=getattr(args, "limit", None),
    )
    return _report(result)


def _report(result: RunResult) -> int:
    if result.outcome == "dry_run":
        for c in result.candidates:
            print(f"{c.url}\t{c.title or ''}")
        for mechanism, error_class in result.discovery_errors:
            print(f"discovery {mechanism}: {error_class}")
        print(f"{result.institution}: {len(result.candidates)} candidates (dry run)")
        return 1 if result.discovery_errors and not result.candidates else 0
    for item in result.items:
        suffix = f" ({item.error_class}: {item.detail})" if item.error_class else ""
        print(f"{item.url}: {item.outcome}{suffix}")
    for mechanism, error_class in result.discovery_errors:
        print(f"discovery {mechanism}: {error_class}")
    print(f"{result.institution}: {result.outcome} {result.counts}")
    return 0 if result.outcome == "ok" else 1


def _status(settings: Settings, registry: dict[str, Institution]) -> int:
    conn = connect(settings.db_path)
    migrate(conn)
    rows = {
        r["key"]: r
        for r in conn.execute(
            "SELECT i.key, h.state, h.last_checked_at, h.last_success_at, h.consecutive_failures"
            " FROM research_institution i LEFT JOIN research_source_health h"
            " ON h.institution_id = i.id"
        )
    }
    print(f"{'key':<12} {'state':<10} {'last checked':<21} {'last success':<21} failures")
    for key, inst in registry.items():
        row = rows.get(key)
        if row is None or row["state"] is None:
            state = "never_run" if inst.automated_access_allowed else "gated"
            print(f"{key:<12} {state:<10} {'-':<21} {'-':<21} 0")
            continue
        print(f"{key:<12} {row['state']:<10} {row['last_checked_at'] or '-':<21}"
              f" {row['last_success_at'] or '-':<21} {row['consecutive_failures']}")  # fmt: skip
    return 0


def _safe(text: object) -> str:
    """Model and document text for a terminal: control characters escaped, never interpreted."""
    out = []
    for ch in str(text):
        if ch.isprintable() or ch == " ":
            out.append(ch)
        else:
            code = ord(ch)
            out.append(f"\\x{code:02x}" if code < 0x100 else f"\\u{code:04x}")
    return "".join(out)


def _emit(text: str = "") -> None:
    """Print one or more lines; every line is escaped, so no stored field reaches the terminal raw."""
    for line in str(text).split("\n"):
        print(_safe(line))


def _open(settings: Settings):
    conn = connect(settings.db_path)
    migrate(conn)
    return conn


def _summarise(
    args: argparse.Namespace, settings: Settings, registry: dict[str, Institution]
) -> int:
    try:
        llm = load_llm_settings(os.environ)
    except LlmConfigError as exc:
        _emit(f"LLM configuration error: {exc}")
        return 2
    if llm.provider == "disabled":
        _emit("no LLM provider is configured; set NZSTATS_LLM_PROVIDER and the related variables"
              " (docs/data-sources/research.md)")  # fmt: skip
        return 1
    if args.key and args.key not in registry:
        _emit(f"unknown institution {args.key!r}; see `nzstats research sources`")
        return 2
    provider = build_llm_provider(llm)
    conn = _open(settings)
    result = summarise_versions(
        conn, registry, provider, pricing=llm.pricing, limits=llm.limits, institution=args.key,
        version_ids=tuple(args.version), limit=args.limit, dry_run=args.dry_run,
    )  # fmt: skip
    for key, reason in result.refusals:
        _emit(f"{key}: refused ({reason})")
    for item in result.items:
        detail = f" ({item.error_class})" if item.error_class else ""
        if item.summary_id is not None:
            detail += f" summary {item.summary_id}, {item.errors} errors, {item.warnings} warnings"
        _emit(f"version {item.version_id} ({item.institution}): {item.outcome}{detail}"
              f" estimated ${item.estimated_usd:.4f}")  # fmt: skip
    where = "dry run" if args.dry_run else f"run {result.run_id}"
    _emit(f"{provider.name}/{provider.model} {where}: {result.outcome} {result.counts};"
          f" spent ${result.spent_usd:.4f} of ${llm.limits.max_run_usd:.2f}")  # fmt: skip
    return 0 if result.outcome == "ok" else 1


def _list(args: argparse.Namespace, settings: Settings, registry: dict[str, Institution]) -> int:
    rows = ss.list_summaries(_open(settings), status=args.status, review_status=args.review)
    _emit(
        f"{'id':>5} {'institution':<12} {'version':>7} {'status':<20} {'review':<11} model / prompt"
    )
    for r in rows:
        _emit(f"{r['id']:>5} {r['institution']:<12} {r['version_id']:>7} {r['status']:<20}"
              f" {r['review_status']:<11} {_safe(r['model'])} / {_safe(r['prompt_version'])}")  # fmt: skip
    _emit(f"{len(rows)} summaries")
    return 0


def _evidence(refs: list[dict]) -> list[str]:
    lines = []
    for ref in refs:
        page = f", page {ref['page']}" if ref.get("page") else ""
        lines.append(f"      [version {ref['version_id']}, section {ref['section_ordinal']}{page}]"
                     f" \"{_safe(ref['quote'])}\"")  # fmt: skip
    return lines


def _show(args: argparse.Namespace, settings: Settings, registry: dict[str, Institution]) -> int:
    conn = _open(settings)
    row = ss.get_summary(conn, args.id)
    if row is None:
        _emit(f"no summary {args.id}")
        return 1
    _emit(f"Summary {row['id']}: {row['institution']} \u2014 {_safe(row['document_title'])}")
    _emit(f"  document version {row['version_id']} (no. {row['version_no']}), published"
          f" {row['published_on'] or 'unknown'}{' (superseded)' if row['superseded_at'] else ''}")  # fmt: skip
    _emit(f"  {row['provider']}/{_safe(row['model'])}, prompt {row['prompt_version']}, processing"
          f" {row['processing_version']}, verifier {row['verifier_version']}, created"
          f" {to_akl_iso(row['created_at'])}")  # fmt: skip
    error = f" ({row['error_class']})" if row["error_class"] else ""
    review = row["review_status"]
    if row["reviewed_by"]:
        review += f" by {_safe(row['reviewed_by'])}: {_safe(row['review_note'] or '')}"
    _emit(f"  status {row['status']}{error}; review {review}")
    _emit("  Not an official statistic: an interpretation of institutional commentary.")
    _emit(f"  {SCOPE}")
    if row["output_json"]:
        out = json.loads(row["output_json"])
        for name in ("outlook", "uncertainty"):
            if out.get(name):
                _emit(f"  {name}: {_safe(out[name]['text'])}")
                _emit("\n".join(_evidence(out[name]["evidence"])))
        for name in ("drivers", "risks"):
            for st in out.get(name, []):
                _emit(f"  {name[:-1]}: {_safe(st['text'])}")
                _emit("\n".join(_evidence(st["evidence"])))
        _emit(f"  indicators: {', '.join(out.get('indicators', [])) or '-'}")
        for i, c in enumerate(out.get("forecasts", [])):
            value = "-" if c["value"] is None else f"{c['value']:g} {c['unit'] or '(no unit)'}"
            scenario = (
                f" [scenario: {_safe(c['scenario'])}]" if c.get("scenario") else " [baseline]"
            )
            _emit(f"  forecast {i}: {c['indicator']} ({_safe(c['indicator_label'])}), {_safe(c['horizon'])}:"
                  f" {value}, {c['direction']}{scenario}")  # fmt: skip
            if c.get("qualification"):
                _emit(f"      qualification: {_safe(c['qualification'])}")
            _emit("\n".join(_evidence(c["evidence"])))
    elif row["raw_output"] is not None:
        _emit(f"  raw output: {len(row['raw_output'])} characters (stored, not shown)")
    if row["verification"]:
        report = json.loads(row["verification"])
        for kind in ("errors", "warnings"):
            for p in report[kind]:
                _emit(f"  {kind[:-1]}: {p['code']}: {_safe(p['message'])}")
    usage = ss.usage_for(conn, row["id"])
    if usage:
        tokens_in = sum(u["input_tokens"] or 0 for u in usage)
        tokens_out = sum(u["output_tokens"] or 0 for u in usage)
        estimated = " (some estimated)" if any(u["usage_estimated"] for u in usage) else ""
        _emit(f"  usage: {len(usage)} calls, {tokens_in} input / {tokens_out} output tokens{estimated},"
              f" ${sum(u['cost_usd'] for u in usage):.4f}, {sum(u['latency_ms'] for u in usage)} ms")  # fmt: skip
    return 0


def _review(args: argparse.Namespace, settings: Settings, registry: dict[str, Institution]) -> int:
    decision = "approved" if args.research_command == "approve" else "rejected"
    try:
        ss.review(_open(settings), args.id, decision=decision, reviewer=args.reviewer, note=args.note,
                  now=utc_now())  # fmt: skip
    except ss.ReviewError as exc:
        _emit(f"refused: {exc}")
        return 1
    _emit(f"summary {args.id}: {decision} by {_safe(args.reviewer.strip())}")
    return 0


_SUMMARY_COMMANDS = {"summarise": _summarise, "summaries": _list, "summary": _show,
                     "approve": _review, "reject": _review}  # fmt: skip
