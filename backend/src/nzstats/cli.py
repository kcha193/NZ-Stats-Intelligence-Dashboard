from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from collections.abc import Sequence

from nzstats.clock import utc_now
from nzstats.config import load_settings
from nzstats.pipeline.discover import current_and_next_months, discover
from nzstats.pipeline.ingest import backfill, ingest_release
from nzstats.runtime import build_runtime
from nzstats.scheduler.planner import releases_needing_ingest
from nzstats.store.db import connect, migrate

log = logging.getLogger("nzstats")


def _health_payload(conn: sqlite3.Connection) -> dict:
    sources = [dict(r) for r in conn.execute("SELECT * FROM source_health ORDER BY source")]
    runs = [
        dict(r)
        for r in conn.execute(
            "SELECT release_key, started_at, outcome, error_class, detail FROM ingest_run"
            " ORDER BY id DESC LIMIT 10"
        )
    ]
    return {"sources": sources, "recent_runs": runs}


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(prog="nzstats")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="create or upgrade the database")
    sub.add_parser("discover", help="refresh the release calendar")
    p_ingest = sub.add_parser("ingest", help="ingest one release or all that are due")
    group = p_ingest.add_mutually_exclusive_group(required=True)
    group.add_argument("--release-key")
    group.add_argument("--due", action="store_true")
    p_back = sub.add_parser("backfill", help="ingest historical releases")
    p_back.add_argument("--since", help="oldest reference period, YYYY-MM")
    p_serve = sub.add_parser("serve", help="run the API, UI and scheduler")
    p_serve.add_argument("--host", default="0.0.0.0")  # noqa: S104 - container default
    p_serve.add_argument("--port", type=int, default=8000)
    sub.add_parser("health", help="print source health as JSON")
    p_backup = sub.add_parser("backup", help="write a consistent copy of the database")
    p_backup.add_argument("dest")
    sub.add_parser("openapi", help="print the OpenAPI document")
    args = parser.parse_args(argv)

    settings = load_settings()
    if args.command == "migrate":
        conn = connect(settings.db_path)
        print(f"schema version {migrate(conn)} at {settings.db_path}")
        return 0
    if args.command == "health":
        conn = connect(settings.db_path)
        migrate(conn)
        print(json.dumps(_health_payload(conn), indent=2))
        return 0
    if args.command == "backup":
        conn = connect(settings.db_path)
        migrate(conn)
        dest = sqlite3.connect(args.dest)
        conn.backup(dest)
        dest.close()
        print(f"backup written to {args.dest}")
        return 0
    if args.command == "openapi":
        from nzstats.api.app import create_app

        print(json.dumps(create_app(settings, start_scheduler=False).openapi(), indent=2))
        return 0
    if args.command == "serve":
        import uvicorn

        from nzstats.api.app import create_app

        uvicorn.run(create_app(settings, start_scheduler=True), host=args.host, port=args.port)
        return 0

    rt = build_runtime(settings)
    if args.command == "discover":
        result = discover(rt, months=current_and_next_months(utc_now()))
        print(f"{result.refs} releases seen; errors: {list(result.errors)}")
        return 1 if result.errors else 0
    if args.command == "ingest":
        keys = (
            [args.release_key]
            if args.release_key
            else releases_needing_ingest(rt.conn, rt.adapters, utc_now(), settings.catch_up_days)
        )
        outcomes = [ingest_release(rt, k) for k in keys]
    else:  # backfill
        outcomes = backfill(rt, since=args.since or settings.backfill_since)
    for o in outcomes:
        suffix = f" ({o.error_class.value}: {o.detail})" if o.error_class else ""
        print(f"{o.release_key}: {o.outcome}{suffix}")
    return 1 if any(o.outcome == "failed" for o in outcomes) else 0


if __name__ == "__main__":
    sys.exit(main())
