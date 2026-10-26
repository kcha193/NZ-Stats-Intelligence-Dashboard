"""`nzstats research ...`: list sources, probe discovery, ingest one institution, show health.

Nothing here runs on a schedule: every request is a deliberate command. A refused source makes no
request at all, and the refusal names the reason.
"""

from __future__ import annotations

import argparse

from nzstats.config import Settings
from nzstats.research.fetch import ResearchFetcher, build_research_client, research_pacer
from nzstats.research.ingest import RunResult, refusal_for, run_institution
from nzstats.research.registry import Institution, RegistryError, load_registry
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


def build_fetcher(inst: Institution, settings: Settings) -> ResearchFetcher:
    return ResearchFetcher(
        inst,
        build_research_client(settings.user_agent),
        pacer=research_pacer(settings.data_dir, inst),
    )


def research_command(args: argparse.Namespace, settings: Settings) -> int:
    try:
        registry = load_registry()
    except RegistryError as exc:
        print(f"research registry error: {exc}")
        return 2
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
