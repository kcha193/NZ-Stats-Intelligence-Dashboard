from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path

from nzstats.clock import utc_now
from nzstats.config import load_settings
from nzstats.pipeline.discover import discover, discovery_months
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


def _publish_command(args: argparse.Namespace, settings) -> int:
    from nzstats.publish.publisher import PublisherConfig, publish

    outcome = publish(
        PublisherConfig(
            data_dir=settings.data_dir,
            work_dir=Path(args.work_dir),
            repo_root=Path(args.repo_root).resolve(),
            site_url=args.site_url.rstrip("/"),
            netlify_site_id=os.environ.get("NETLIFY_SITE_ID", ""),
            netlify_auth_token=os.environ.get("NETLIFY_AUTH_TOKEN", ""),
            min_interval_hours=args.min_interval_hours,
            draft=args.draft,
            dry_run=args.dry_run,
            force=args.force,
        )
    )
    snapshot = outcome.snapshot_id[:12] if outcome.snapshot_id else "-"
    print(f"{outcome.status}: snapshot {snapshot}: {outcome.message}")
    return 0 if outcome.ok else 1


def _snapshot_command(args: argparse.Namespace, settings) -> int:
    from datetime import UTC, datetime

    from nzstats.publish.snapshot import SnapshotError, export_snapshot
    from nzstats.publish.validate import validate_snapshot

    if args.command == "export-snapshot":
        now = datetime.fromisoformat(args.now).astimezone(UTC) if args.now else None
        try:
            manifest = export_snapshot(
                settings.data_dir, Path(args.out), now=now, allow_fixtures=args.allow_fixtures
            )
        except SnapshotError as exc:
            print(f"export failed: {exc}", file=sys.stderr)
            return 2
        c = manifest["counts"]
        print(
            f"snapshot {manifest['snapshot_id'][:12]} origin {manifest['origin']}: {c['files']} files, "
            f"{c['bytes'] / 1e6:.2f} MB, {c['published_releases']} published releases -> {args.out}"
        )
        return 0
    if args.command == "check-site":
        from nzstats.publish.sitecheck import check_site

        report = check_site(
            Path(args.path),
            site_url=args.site_url,
            netlify_toml=Path(args.netlify_toml) if args.netlify_toml else None,
            for_publish=args.for_publish,
        )
    else:
        report = validate_snapshot(Path(args.path), for_publish=getattr(args, "for_publish", False))
    for warning in report.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for error in report.errors:
        print(f"error: {error}", file=sys.stderr)
    if args.command == "snapshot-id":
        if not report.ok:
            return 1
        print(report.manifest["snapshot_id"])
        return 0
    if report.ok:
        print("site is ready" if args.command == "check-site" else "snapshot is valid")
    return 0 if report.ok else 1


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
    p_back.add_argument("--until", help="latest reference period, YYYY-MM")
    p_back.add_argument("--series-slug", help="restrict backfill to a supported release series")
    p_serve = sub.add_parser("serve", help="run the API, UI and scheduler")
    p_serve.add_argument("--host", default="0.0.0.0")  # noqa: S104 - container default
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument(
        "--no-scheduler", action="store_true", help="serve the API and UI without background jobs"
    )
    sub.add_parser("health", help="print source health as JSON")
    p_backup = sub.add_parser("backup", help="write a consistent copy of the database")
    p_backup.add_argument("dest")
    sub.add_parser("openapi", help="print the OpenAPI document")
    p_export = sub.add_parser(
        "export-snapshot", help="write a validated public JSON snapshot of the database"
    )
    p_export.add_argument("out", help="output directory (replaced if it is an earlier snapshot)")
    p_export.add_argument(
        "--allow-fixtures",
        action="store_true",
        help="tests only: export fixture data, labelled origin=fixture and never publishable",
    )
    p_export.add_argument(
        "--now", help="override the export time (ISO-8601, UTC); for reproducible tests"
    )
    p_validate = sub.add_parser("validate-snapshot", help="validate a snapshot directory")
    p_validate.add_argument("path")
    p_validate.add_argument(
        "--for-publish", action="store_true", help="also require production origin"
    )
    p_site = sub.add_parser("check-site", help="check a built static site before deploying it")
    p_site.add_argument("path")
    p_site.add_argument("--site-url", required=True)
    p_site.add_argument("--netlify-toml")
    p_site.add_argument("--for-publish", action="store_true")
    p_pub = sub.add_parser(
        "publish-site", help="export, validate, build and (if the data changed) deploy to Netlify"
    )
    p_pub.add_argument("--work-dir", required=True, help="state, lock and staged snapshot")
    p_pub.add_argument(
        "--site-url", required=True, help="canonical https origin of the public site"
    )
    p_pub.add_argument("--repo-root", default=os.environ.get("NZSTATS_REPO_ROOT", "."))
    p_pub.add_argument(
        "--min-interval-hours",
        type=float,
        default=24.0,
        help="shortest gap between deploys that carry no new verified data",
    )
    p_pub.add_argument("--draft", action="store_true", help="deploy to a draft URL, not production")
    p_pub.add_argument("--dry-run", action="store_true", help="build but do not deploy")
    p_pub.add_argument("--force", action="store_true", help="ignore the minimum interval")
    p_sid = sub.add_parser("snapshot-id", help="print a snapshot's content id")
    p_sid.add_argument("path")
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
        Path(args.dest).parent.mkdir(parents=True, exist_ok=True)
        dest = sqlite3.connect(args.dest)
        conn.backup(dest)
        dest.close()
        print(f"backup written to {args.dest}")
        return 0
    if args.command == "openapi":
        from nzstats.api.app import create_app

        print(json.dumps(create_app(settings, start_scheduler=False).openapi(), indent=2))
        return 0
    if args.command == "publish-site":
        return _publish_command(args, settings)
    if args.command in ("export-snapshot", "validate-snapshot", "snapshot-id", "check-site"):
        return _snapshot_command(args, settings)
    if args.command == "serve":
        import uvicorn

        from nzstats.api.app import create_app

        uvicorn.run(
            create_app(settings, start_scheduler=not args.no_scheduler),
            host=args.host,
            port=args.port,
        )
        return 0

    rt = build_runtime(settings)
    if args.command == "discover":
        result = discover(rt, months=discovery_months(utc_now()))
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
        bounds = {}
        if args.until:
            bounds["until"] = args.until
        if args.series_slug:
            bounds["series_slug"] = args.series_slug
        outcomes = backfill(rt, since=args.since or settings.backfill_since, **bounds)
    for o in outcomes:
        suffix = (
            f" ({o.error_class.value}: {o.detail})"
            if o.error_class
            else f" ({o.detail})"
            if o.detail
            else ""
        )
        print(f"{o.release_key}: {o.outcome}{suffix}")
    # A requested release that was not ingested (failed, files not available, or no adapter for an
    # explicit key; catch-up and backfill only select releases that have one) is a gap.
    gaps = ("failed", "not_available", "skipped_no_adapter")
    return 1 if any(o.outcome in gaps for o in outcomes) else 0


if __name__ == "__main__":
    sys.exit(main())
