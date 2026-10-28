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
from datetime import date
from pathlib import Path

from nzstats.clock import to_akl_iso, utc_now
from nzstats.config import Settings
from nzstats.research import purge
from nzstats.research import summary_store as ss
from nzstats.research.contract import Provider
from nzstats.research.cpi_reconcile import reconcile
from nzstats.research.fetch import (
    DEFAULT_MAX_BYTES,
    ResearchFetcher,
    build_research_client,
    research_pacer,
)
from nzstats.research.health import research_health
from nzstats.research.ingest import RunResult, refusal_for, run_institution
from nzstats.research.manual_import import ImportRefused, import_document
from nzstats.research.outcomes import stored_cpi_releases
from nzstats.research.pilot_eval import AnnotationError, evaluate_stored, load_annotations
from nzstats.research.providers import (
    LlmConfigError,
    LlmSettings,
    build_provider,
    load_llm_settings,
)
from nzstats.research.public import why_not_public
from nzstats.research.quality import version_quality
from nzstats.research.readiness import assess, pipeline_state
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
    p_health = rsub.add_parser(
        "health", help="pipeline health, staleness, queues and withheld publications (Phase 3E)"
    )
    p_health.add_argument("--json", action="store_true", help="machine-readable output")
    rsub.add_parser(
        "cpi-vintages", help="which CPI quarters have a genuine first-published vintage stored (3E)"
    )
    rsub.add_parser(
        "cpi-reconcile",
        help="check stored CPI vintages and outcomes against the official files kept in data/raw (3F; no request)",
    )
    p_imp = rsub.add_parser(
        "import", help="store an owner-supplied copy of one document (Phase 3E; no request is made)"
    )
    p_imp.add_argument("key")
    p_imp.add_argument("file", help="the saved document (.html, .htm or .pdf)")
    p_imp.add_argument("--url", required=True, help="the document's address on an allowed host")
    p_imp.add_argument("--importer", required=True, help="who obtained and is importing the copy")
    p_imp.add_argument("--note", required=True, help="where and how it was obtained (private)")
    p_imp.add_argument("--title", help="fallback title when the document states none")
    p_imp.add_argument("--published-on", type=date.fromisoformat,
                       help="the institution's publication date (YYYY-MM-DD)")  # fmt: skip
    p_imp.add_argument("--series", help="the report series, e.g. HYEFU")
    p_purge = rsub.add_parser(
        "purge",
        help="remove stored source content when a permission is withdrawn (Phase 3F; dry run by default)",
    )
    p_purge.add_argument("key", nargs="?", help="the institution (omit with --finish)")
    sel = p_purge.add_mutually_exclusive_group()
    sel.add_argument("--acquisition", choices=("manual", "crawler", "all"),
                     help="every stored version obtained this way")  # fmt: skip
    sel.add_argument("--version", type=_positive_int, action="append", default=[],
                     help="a specific document version id (repeatable)")  # fmt: skip
    p_purge.add_argument("--reason", choices=("permission_withdrawn", "takedown", "other"))
    p_purge.add_argument("--by", help="who authorised the purge")
    p_purge.add_argument("--note", help="why, and who asked (private)")
    p_purge.add_argument(
        "--apply", action="store_true", help="do it (the default only shows the plan)"
    )
    p_purge.add_argument("--finish", action="store_true",
                         help="finish removing files left pending by an interrupted purge")  # fmt: skip
    p_orph = rsub.add_parser("orphans", help="stored files that no record references (Phase 3F)")
    p_orph.add_argument("--remove", action="store_true", help="delete the ones older than an hour")
    p_ready = rsub.add_parser(
        "readiness", help="the four pilot permissions per source (Phase 3D-A)"
    )
    p_ready.add_argument(
        "key", nargs="?", help="one institution in detail (default: all, one line each)"
    )
    p_eval = rsub.add_parser(
        "evaluate", help="score stored real summaries against an annotation file (3D-A)"
    )
    p_eval.add_argument(
        "--annotations", required=True, help="JSON annotation file (keep it under data/)"
    )
    p_eval.add_argument("--model", help="only summaries from this model")
    p_qual = rsub.add_parser(
        "quality", help="extraction quality of stored document versions (Phase 3D-A)"
    )
    p_qual.add_argument("version", type=_positive_int, nargs="*",
                        help="version ids (default: every current version)")  # fmt: skip
    p_sum = rsub.add_parser("summarise", help="summarise stored versions with the configured LLM")
    p_sum.add_argument("key", nargs="?", help="one institution (default: every permitted one)")
    p_sum.add_argument("--version", type=_positive_int, action="append", default=[],
                       help="a specific document version id (repeatable)")  # fmt: skip
    p_sum.add_argument("--limit", type=_positive_int,
                       help="summarise at most this many not-yet-summarised documents")  # fmt: skip
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
    for name, help_text in (
        ("publish", "allow an approved summary to be shown publicly (Phase 3C)"),
        ("withdraw", "stop showing a summary publicly"),
    ):
        p_pub = rsub.add_parser(name, help=help_text)
        p_pub.add_argument("id", type=_positive_int)
        p_pub.add_argument("--approver", required=True)
        p_pub.add_argument("--note", required=True, help="why (private; never shown publicly)")


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
        print(f"{'key':<12} {'review':<13} {'policy':<14} {'llm':<11} {'display':<10} {'verified':<11}"
              " access")  # fmt: skip
        for inst in registry.values():
            access = inst.refusal_reason() or "allowed"
            if inst.manual_import_allowed:
                access += "; manual import approved"
            verified = inst.verified_on.isoformat() if inst.verified_on else "-"
            print(f"{inst.key:<12} {inst.review_status.value:<13} {inst.content_policy.value:<14}"
                  f" {inst.llm_processing.value:<11} {inst.display_level().value:<10} {verified:<11}"
                  f" {access}")  # fmt: skip
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
          f" spent ${result.spent_usd:.4f} of ${llm.limits.max_run_usd:.2f}; 30-day cap"
          f" ${llm.limits.max_period_usd:.2f}, ${result.period_remaining_usd:.4f} left at start")  # fmt: skip
    return 0 if result.outcome == "ok" else 1


def _list(args: argparse.Namespace, settings: Settings, registry: dict[str, Institution]) -> int:
    conn = _open(settings)
    rows = ss.list_summaries(conn, status=args.status, review_status=args.review)
    _emit(f"{'id':>5} {'institution':<12} {'version':>7} {'status':<20} {'review':<11} {'publication':<11}"
          " model / prompt")  # fmt: skip
    for r in rows:
        decision = ss.publication_state(conn, r["id"])
        published = decision["decision"] if decision else "-"
        _emit(f"{r['id']:>5} {r['institution']:<12} {r['version_id']:>7} {r['status']:<20}"
              f" {r['review_status']:<11} {published:<11} {_safe(r['model'])} / {_safe(r['prompt_version'])}")  # fmt: skip
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
    decision = ss.publication_state(conn, row["id"])
    if decision:
        _emit(f"  publication {decision['decision']} by {_safe(decision['approver'])}"
              f" ({to_akl_iso(decision['decided_at'])})")  # fmt: skip
    reason = why_not_public(conn, registry, row["id"])
    if reason is None:
        inst = registry[row["institution"]]
        _emit(f"  public: yes ({inst.display_level().value}) when NZSTATS_PUBLIC_RESEARCH=1")
    else:
        _emit(f"  public: no ({_safe(reason)})")
    _emit("  Not an official statistic: an interpretation of institutional commentary.")
    _emit(f"  {SCOPE}")
    if ss.is_redacted(row["output_json"]):
        _emit(
            "  content purged: the source text and everything derived from it was removed (research purge)"
        )
    elif row["output_json"]:
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
    if row["verification"] and not ss.is_redacted(row["verification"]):
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


def _publication(
    args: argparse.Namespace, settings: Settings, registry: dict[str, Institution]
) -> int:
    decision = args.research_command  # "publish" or "withdraw"
    conn = _open(settings)
    try:
        ss.record_publication(conn, args.id, decision=decision, approver=args.approver, note=args.note,
                              now=utc_now())  # fmt: skip
    except ss.PublicationError as exc:
        _emit(f"refused: {exc}")
        return 1
    _emit(f"summary {args.id}: {decision} recorded by {_safe(args.approver.strip())}")
    if decision == "publish":
        reason = why_not_public(conn, registry, args.id)
        _emit("  shown publicly when NZSTATS_PUBLIC_RESEARCH=1" if reason is None
              else f"  still not public: {_safe(reason)}")  # fmt: skip
    return 0


def _readiness(
    args: argparse.Namespace, settings: Settings, registry: dict[str, Institution]
) -> int:
    try:
        llm = load_llm_settings(os.environ)
    except LlmConfigError as exc:
        _emit(f"LLM configuration error: {exc}")
        return 2
    if args.key is None:
        _emit(f"{'key':<12} {'gates':<16} first blocker")
        for inst in registry.values():
            report = assess(inst, llm, env=os.environ)
            granted = sum(g.granted for g in report.gates)
            _emit(f"{inst.key:<12} {f'granted {granted} of 4':<16} {report.first_blocker or '-'}")
        return 0
    inst = registry.get(args.key)
    if inst is None:
        _emit(f"unknown institution {args.key!r}; see `nzstats research sources`")
        return 2
    report = assess(inst, llm, env=os.environ)
    _emit(
        f"{inst.name} ({inst.key}): pilot readiness. Read-only: nothing was requested or changed."
    )
    for number, gate in enumerate(report.gates, 1):
        _emit(
            f"{number}. {gate.title}: {'granted' if gate.granted else 'not granted'} ({gate.detail})"
        )
        for line in gate.evidence:
            _emit(f"     {line}")
        for line in gate.warnings:
            _emit(f"     warning: {line}")
        if gate.blocker:
            _emit(f"     blocked: {gate.blocker}")
    _emit(f"first blocker: {report.first_blocker or 'none'}")
    state = pipeline_state(_open(settings), inst, registry)
    statuses = ", ".join(f"{k} {v}" for k, v in sorted(state.summaries.items())) or "none"
    _emit(f"stored: {state.publications} publications, {state.current_versions} current versions;"
          f" summaries: {statuses}; approved {state.approved}; public now {state.public}")  # fmt: skip
    return 0


def _evaluate(
    args: argparse.Namespace, settings: Settings, registry: dict[str, Institution]
) -> int:
    try:
        annotations = load_annotations(Path(args.annotations))
    except AnnotationError as exc:
        _emit(f"refused: {exc}")
        return 2
    _emit(
        evaluate_stored(_open(settings), annotations, model=args.model).to_markdown().rstrip("\n")
    )
    return 0


def _quality(args: argparse.Namespace, settings: Settings, registry: dict[str, Institution]) -> int:
    conn = _open(settings)
    ids = list(args.version) or [
        r[0] for r in conn.execute(
            "SELECT current_version_id FROM research_publication WHERE current_version_id IS NOT NULL ORDER BY id")
    ]  # fmt: skip
    missing = False
    for version_id in ids:
        report = version_quality(conn, version_id)
        if report is None:
            _emit(f"no version {version_id}")
            missing = True
            continue
        m = report.metrics
        _emit(f"version {version_id}: {report.grade} ({m['sections']} sections, {m['characters']} characters,"
              f" pages {m['page_count'] or '-'}, letters {m['letter_ratio']:.0%}, digits {m['digit_ratio']:.0%})")  # fmt: skip
        for f in report.findings:
            _emit(f"  {f.severity}: {f.code}: {f.message}")
    if not ids:
        _emit("no stored document versions")
    _emit("Heuristic checks: read any version graded review or poor before summarising it.")
    return 1 if missing else 0


def _health(args: argparse.Namespace, settings: Settings, registry: dict[str, Institution]) -> int:
    """Exit 1 when anything needs attention, so a scheduled check can alert on it."""
    try:
        limits = load_llm_settings(os.environ).limits
    except LlmConfigError as exc:
        _emit(f"LLM configuration error: {exc}")
        return 2
    report = research_health(
        _open(settings), registry, now=utc_now(), limits=limits, env=os.environ,
        artifacts=ArtifactStore(settings.raw_dir),
    )  # fmt: skip
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
        return 1 if report.needs_attention else 0
    _emit(f"Research health at {report.checked_at}. Read-only: nothing was requested or changed.")
    _emit(f"{'key':<12} {'routes':<14} {'crawler':<10} {'newest':<11} {'pubs':>5} {'todo':>5} {'review':>6}"
          f" {'to pub':>6} {'public':>6}")  # fmt: skip
    for src in report.sources:
        _emit(f"{src.key:<12} {src.routes:<14} {src.crawler_state or '-':<10} {src.newest_publication_on or '-':<11}"
              f" {src.publications:>5} {src.unsummarised:>5} {src.awaiting_review:>6} {src.awaiting_publication:>6}"
              f" {src.public:>6}")  # fmt: skip
        for f in src.findings:
            _emit(f"  {f.severity}: {f.code}: {f.message}")
    _emit(f"model spend, last 30 days: ${report.spent_period_usd:.4f} of ${report.period_cap_usd:.2f};"
          f" public research API {report.public_switch}")  # fmt: skip
    for f in report.findings:
        _emit(f"{f.severity}: {f.code}: {f.message}")
    _emit("needs attention" if report.needs_attention else "ok")
    return 1 if report.needs_attention else 0


def _cpi_vintages(
    args: argparse.Namespace, settings: Settings, registry: dict[str, Institution]
) -> int:
    rows = stored_cpi_releases(_open(settings))
    if not rows:
        _emit("no CPI release is stored: no forecast can be matched to an outcome yet")
        return 0
    _emit(f"{'quarter':<8} {'published (NZ)':<26} {'bundles':>7}  first stored")
    for r in rows:
        _emit(
            f"{r.reference_period:<8} {to_akl_iso(r.published_at):<26} {r.bundles:>7}  {to_akl_iso(r.earliest_captured_at)}"
        )
    _emit(f"Quarters listed have their own release stored: their first-published values are genuine. Every quarter"
          f" before {rows[0].reference_period} uses the earliest stored value, from {_safe(rows[0].title)}, and is"
          " labelled earliest stored. Backfilling older releases (a throttled real-site run) needs approval:"
          " docs/cpi-release-runbook.md.")  # fmt: skip
    return 0


_SUFFIXES = {".html": "html", ".htm": "html", ".pdf": "pdf"}


def _import(args: argparse.Namespace, settings: Settings, registry: dict[str, Institution]) -> int:
    inst = registry.get(args.key)
    if inst is None:
        _emit(f"unknown institution {args.key!r}; see `nzstats research sources`")
        return 2
    refusal = inst.import_refusal()
    if refusal is not None:  # before the file is read
        _emit(f"{inst.key}: refused ({refusal})")
        return 1
    path = Path(args.file)
    file_format = _SUFFIXES.get(path.suffix.lower())
    if file_format is None:
        _emit("refused: the file must be .html, .htm or .pdf (html or pdf)")
        return 2
    if not path.is_file():
        _emit("refused: the file does not exist")
        return 2
    if path.stat().st_size > DEFAULT_MAX_BYTES:
        _emit(f"refused: the file is larger than {DEFAULT_MAX_BYTES} bytes")
        return 1
    conn = _open(settings)
    try:
        result = import_document(
            conn, inst, body=path.read_bytes(), file_format=file_format, url=args.url,
            importer=args.importer, note=args.note, now=utc_now(), artifacts=ArtifactStore(settings.raw_dir),
            title=args.title, published_on=args.published_on, series=args.series,
        )  # fmt: skip
    except ImportRefused as exc:
        _emit(f"{inst.key}: refused ({exc})")
        return 1
    warnings = f" warnings: {', '.join(result.warnings)}" if result.warnings else ""
    _emit(f"{inst.key}: {result.outcome} publication {result.publication_id} version"
          f" {result.version_id or '-'} sha256 {result.content_sha256[:12]}{warnings}")  # fmt: skip
    _emit("Stored locally only. LLM processing, review and publication are separate decisions.")
    return 0


def _purge(args: argparse.Namespace, settings: Settings, registry: dict[str, Institution]) -> int:
    """Plan (default) or perform a purge; `--finish` completes the file step of an interrupted one."""
    conn = _open(settings)
    artifacts = ArtifactStore(settings.raw_dir)
    if args.finish:
        done = purge.finish_pending(conn, artifacts, now=utc_now())
        left = len(purge.pending_artifacts(conn))
        clean = purge.truncate_wal(conn)
        _emit(
            f"finished {done} pending artifact(s); {left} still pending; log {'truncated' if clean else 'still busy'}"
        )
        return 1 if left or not clean else 0
    if not args.key:
        _emit("refused: name the institution (or use --finish)")
        return 2
    try:
        plan = purge.plan_purge(
            conn, args.key, acquisition=args.acquisition, version_ids=tuple(args.version)
        )
    except purge.PurgeError as exc:
        _emit(f"refused: {exc}")
        return 2
    _emit(
        f"{args.key}: {len(plan.version_ids)} version(s) selected {json.dumps(plan.scope, sort_keys=True)}"
    )
    _emit(f"  would remove {plan.sections} section(s), redact {plan.summaries} summary(ies), delete {plan.claims}"
          f" forecast claim(s), withdraw {plan.published} published summary(ies), delete {len(plan.artifacts)} raw artifact(s)")  # fmt: skip
    _emit(
        "  kept: version tombstones and hashes, the import, review, publication and spend logs, and a purge record"
    )
    if not plan.version_ids:
        _emit("nothing to purge")
        return 0
    if not args.apply:
        _emit("Dry run: nothing was changed. Add --apply with --reason, --by and --note to purge.")
        return 0
    if not (args.reason and args.by and args.note):
        _emit("refused: --apply needs --reason, --by and --note")
        return 2
    try:
        result = purge.apply_purge(conn, plan, artifacts, reason=args.reason, purged_by=args.by,
                                   note=args.note, now=utc_now())  # fmt: skip
    except purge.PurgeError as exc:
        _emit(f"refused: {exc}")
        return 2
    _emit(f"purge {result.purge_id}: {result.versions} version(s) purged, {result.artifacts_removed} artifact(s)"
          f" removed, {result.pending} pending")  # fmt: skip
    _emit("Older backups may still hold this content: expire them (README, backup and restore).")
    if not result.wal_truncated:
        _emit("WARNING: a reader kept the write-ahead log busy, so the old pages may remain in the database files."
              " Stop the API and scheduler and run `research purge --finish`.")  # fmt: skip
        return 1
    if result.pending:
        _emit("Some files could not be removed; run `research purge --finish`.")
        return 1
    return 0


def _orphans(args: argparse.Namespace, settings: Settings, registry: dict[str, Institution]) -> int:
    conn = _open(settings)
    artifacts = ArtifactStore(settings.raw_dir)
    found = purge.find_orphan_files(conn, artifacts)
    for path in found:
        _emit(f"{path.parent.name}/{path.name}")
    problems = purge.integrity_problems(conn, artifacts)
    for problem in problems:
        _emit(f"problem: {problem}")
    if args.remove and found:
        _emit(f"removed {purge.remove_orphan_files(conn, artifacts)} unreferenced file(s)")
        return 1 if problems else 0
    _emit(f"{len(found)} unreferenced file(s) older than an hour; {len(problems)} problem(s)")
    return 1 if found or problems else 0


def _cpi_reconcile(
    args: argparse.Namespace, settings: Settings, registry: dict[str, Institution]
) -> int:
    """Exit 1 on any discrepancy. Reads the database and the kept files only; nothing is requested or changed."""
    result = reconcile(_open(settings), settings.raw_dir)
    matched = sum(1 for v in result.vintages if v.file_sha256)
    _emit(f"{len(result.vintages)} stored all-groups index vintages; {matched} reproduced by one of"
          f" {result.official_files} kept official files")  # fmt: skip
    for v in result.vintages:
        _emit(
            f"  {v.series} vintage {v.vintage_id} {v.release_key}: {v.file_sha256[:12] if v.file_sha256 else 'NO MATCH'}"
        )
    genuine = sorted({o.quarter for o in result.outcomes if o.genuine_first_release})
    _emit(f"{len(result.outcomes)} outcomes checked; first-published is a genuine first release only for:"
          f" {', '.join(genuine) or 'none'}")  # fmt: skip
    for line in result.discrepancies:
        _emit(f"DISCREPANCY: {line}")
    _emit(
        "reconciled: no discrepancies"
        if result.ok
        else f"{len(result.discrepancies)} discrepancy(ies)"
    )
    return 0 if result.ok else 1


_SUMMARY_COMMANDS = {"cpi-reconcile": _cpi_reconcile, "purge": _purge, "orphans": _orphans, "summarise": _summarise, "import": _import, "health": _health, "cpi-vintages": _cpi_vintages, "summaries": _list, "summary": _show,
                     "approve": _review, "reject": _review, "publish": _publication,
                     "withdraw": _publication, "readiness": _readiness,
                     "quality": _quality, "evaluate": _evaluate}  # fmt: skip
