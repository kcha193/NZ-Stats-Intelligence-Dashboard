from __future__ import annotations

import argparse
import fcntl
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
from nzstats.store.backup_check import verify_backup
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


STATUS_EXIT = {"ok": 0, "attention": 1, "critical": 2}


def _status_command(args: argparse.Namespace, settings) -> int:
    """Never starts the scheduler, never writes, never makes a network request: it reads local files only."""
    from nzstats.ops.collect import collect_status
    from nzstats.ops.render import render_text

    try:
        report = collect_status(
            settings, deep=args.deep, backup_dir=Path(args.backup_dir) if args.backup_dir else None
        )
    except Exception:  # monitoring must say it failed, not crash into a traceback or a false OK
        log.exception("status could not be computed")
        print("status could not be computed; see the log above", file=sys.stderr)
        return 3
    print(report.model_dump_json(indent=2) if args.json else render_text(report))
    return STATUS_EXIT[report.overall]


def _alert_command(args: argparse.Namespace, settings) -> int:
    """Local alerts only. Exit code is the application's state; a delivery failure is reported, never mixed into it."""
    from nzstats.ops.alerts import DEFAULT_CHANNELS, build_notifiers, deliver_unrecorded, process
    from nzstats.ops.collect import collect_status
    from nzstats.ops.render import render_text

    try:
        notifiers = build_notifiers(
            args.channels or os.environ.get("NZSTATS_ALERT_CHANNELS") or DEFAULT_CHANNELS, settings
        )
        now = utc_now()
        report = collect_status(
            settings, now=now, backup_dir=Path(args.backup_dir) if args.backup_dir else None
        )
        if not report.database.readable:
            # No state to keep, and never create a database just to record that it is missing, but do say so.
            print(render_text(report))
            result = deliver_unrecorded(report, notifiers)
            print(
                f"\nAlerts: delivered {result.sent}, failed {result.failed} (no database: not de-duplicated)"
            )
            if result.failed:
                print(
                    "ALERT DELIVERY PROBLEM (the application's state above is unaffected)",
                    file=sys.stderr,
                )
            return STATUS_EXIT[report.overall]
        lock = settings.db_path.with_name(settings.db_path.name + ".alert-lock")
        with lock.open("a+b") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                print("alert-check: another alert-check is running; skipped", file=sys.stderr)
                return 3
            conn = connect(settings.db_path)
            try:
                migrate(conn)
                result = process(conn, report, notifiers, now=now)
            finally:
                conn.close()
    except ValueError as exc:
        print(f"alert-check: {exc}", file=sys.stderr)
        return 3
    except Exception:
        log.exception("alert-check could not run")
        print("alert-check could not run; see the log above", file=sys.stderr)
        return 3
    print(render_text(report))
    print(
        f"\nAlerts: {len(result.changes)} change(s); delivered {result.sent}, failed {result.failed},"
        f" rate-limited {result.rate_limited}"
    )
    if result.failed:
        print(
            "ALERT DELIVERY PROBLEM (the application's state above is unaffected)", file=sys.stderr
        )
    return STATUS_EXIT[report.overall]


def _bundle_backup(conn: sqlite3.Connection, settings, dest: Path) -> int:
    from nzstats.store.backup_bundle import BackupError, create_bundle

    try:
        report = create_bundle(conn, settings.raw_dir, dest)
    except BackupError as exc:
        print(f"backup failed: {exc}", file=sys.stderr)
        return 1
    print(
        f"backup set written to {report.path}: database plus {report.raw_artifacts} raw artifact(s),"
        f" verified (schema {report.schema_version})"
    )
    return 0


def _verify_bundle(path: Path) -> int:
    from nzstats.store.backup_bundle import verify_bundle

    report = verify_bundle(path)
    for problem in report.problems:
        print(f"problem: {problem}")
    note = "; needs `nzstats migrate` after restoring" if report.needs_migration else ""
    print(
        f"{'ok' if report.ok else 'FAILED'}: schema {report.schema_version},"
        f" {report.raw_artifacts if report.raw_artifacts is not None else '?'} raw artifact(s){note}"
    )
    return 0 if report.ok else 1


def _restore_backup(src: Path, dest: Path) -> int:
    from nzstats.store.backup_bundle import BackupError, restore_bundle

    try:
        report = restore_bundle(src, dest)
    except BackupError as exc:
        print(f"restore failed: {exc}", file=sys.stderr)
        return 1
    note = " Run `nzstats migrate` against it before use." if report.needs_migration else ""
    print(f"restored to {report.path}: verified.{note} Point NZSTATS_DATA_DIR at it to use it.")
    return 0


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
            dry_run=args.dry_run or not (args.enable or os.environ.get("PUBLISH_ENABLED") == "1"),
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
    p_serve = sub.add_parser(
        "serve", help="run the API and UI, checking Stats NZ when the dashboard is opened"
    )
    # Loopback by default; the container passes --host 0.0.0.0 (with --refresh scheduler) explicitly.
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument(
        "--refresh",
        choices=("on-open", "scheduler", "off"),
        default="on-open",
        help="on-open: one bounded check when the dashboard is opened (loopback binds only; the default);"
        " scheduler: the APScheduler jobs (the container); off: never contact Stats NZ",
    )
    p_serve.add_argument(
        "--no-scheduler",
        "--offline",
        dest="offline",
        action="store_true",
        help="same as --refresh off: serve stored data only, never contact Stats NZ",
    )
    sub.add_parser("health", help="print source health as JSON")
    p_status = sub.add_parser(
        "status",
        help="read-only operational status (exit 0 OK, 1 ATTENTION, 2 CRITICAL, 3 could not run)",
    )
    p_status.add_argument("--json", action="store_true", help="print the full report as JSON")
    p_status.add_argument(
        "--deep", action="store_true", help="also run SQLite quick_check (slower)"
    )
    p_status.add_argument("--backup-dir", help="where to look for backups (default data/backups)")
    p_backup = sub.add_parser("backup", help="write a consistent copy of the database")
    p_backup.add_argument("dest")
    p_backup.add_argument(
        "--bundle",
        action="store_true",
        help="DEST becomes a directory holding the database AND every raw artifact, with a checksum manifest",
    )
    p_verify = sub.add_parser("verify-backup", help="check that a backup restores (read-only)")
    p_verify.add_argument("path")
    p_verify.add_argument("--live", help="compare row counts with this database")
    p_verify.add_argument(
        "--raw-dir", help="require every referenced raw artifact under this directory"
    )
    p_alert = sub.add_parser(
        "alert-check",
        help="evaluate status and deliver NEW or changed alerts to local channels (log, file); exit as `status`",
    )
    p_alert.add_argument(
        "--channels", help="comma-separated; default NZSTATS_ALERT_CHANNELS or log,file"
    )
    p_alert.add_argument("--backup-dir")
    p_restore = sub.add_parser(
        "restore-backup",
        help="copy a verified backup set into a NEW data directory (never overwrites; does not start anything)",
    )
    p_restore.add_argument("src")
    p_restore.add_argument("dest_data_dir")
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
    p_pub.add_argument(
        "--enable",
        action="store_true",
        help="allow a deploy (also PUBLISH_ENABLED=1); without it a run builds and validates only",
    )
    p_pub.add_argument(
        "--dry-run", action="store_true", help="build but do not deploy, even if enabled"
    )
    p_pub.add_argument(
        "--force",
        action="store_true",
        help="rebuild unchanged snapshots and ignore the minimum interval",
    )
    p_sid = sub.add_parser("snapshot-id", help="print a snapshot's content id")
    p_sid.add_argument("path")
    # Wiring only: the research domain is separate, and no Stats NZ package imports it.
    from nzstats.research.cli import add_research_parser, research_command

    add_research_parser(sub)
    args = parser.parse_args(argv)

    settings = load_settings()
    if args.command == "migrate":
        conn = connect(settings.db_path)
        print(f"schema version {migrate(conn)} at {settings.db_path}")
        return 0
    if args.command == "status":
        return _status_command(args, settings)
    if args.command == "alert-check":
        return _alert_command(args, settings)
    if args.command == "health":
        conn = connect(settings.db_path)
        migrate(conn)
        print(json.dumps(_health_payload(conn), indent=2))
        return 0
    if args.command == "backup":
        conn = connect(settings.db_path)
        migrate(conn)
        if args.bundle:
            return _bundle_backup(conn, settings, Path(args.dest))
        Path(args.dest).parent.mkdir(parents=True, exist_ok=True)
        dest = sqlite3.connect(args.dest)
        conn.backup(dest)
        dest.close()
        report = verify_backup(args.dest)
        if not report.ok:
            print(
                f"backup written to {args.dest} but it FAILED verification: {'; '.join(report.problems)}"
            )
            return 1
        print(f"backup written to {args.dest} and verified (schema {report.schema_version})")
        return 0
    if args.command == "restore-backup":
        return _restore_backup(Path(args.src), Path(args.dest_data_dir))
    if args.command == "verify-backup" and Path(args.path).is_dir():
        return _verify_bundle(Path(args.path))
    if args.command == "verify-backup":
        report = verify_backup(args.path, live=args.live, raw_dir=args.raw_dir)
        for problem in report.problems:
            print(f"problem: {problem}")
        for table, (copy, live) in sorted(report.count_differences.items()):
            print(f"rows differ from live: {table} {copy} in the backup, {live} live")
        print(f"{'ok' if report.ok else 'FAILED'}: schema {report.schema_version}"
              f" (expected {report.expected_schema_version}), {sum(report.counts.values())} rows"
              f" in {len(report.counts)} tables")  # fmt: skip
        return 0 if report.ok else 1
    if args.command == "openapi":
        from nzstats.api.app import create_app
        from nzstats.research.api import research_router

        app = create_app(settings, start_scheduler=False, routers=[research_router()])
        print(json.dumps(app.openapi(), indent=2))
        return 0
    if args.command == "research":
        return research_command(args, settings)
    if args.command == "publish-site":
        return _publish_command(args, settings)
    if args.command in ("export-snapshot", "validate-snapshot", "snapshot-id", "check-site"):
        return _snapshot_command(args, settings)
    if args.command == "serve":
        import uvicorn

        from nzstats.api.app import create_app
        from nzstats.research.api import (
            bind_refusal,
            public_research_enabled,
            research_router,
        )  # off unless NZSTATS_PUBLIC_RESEARCH=1

        loopback = args.host in ("127.0.0.1", "::1", "localhost")
        mode = "off" if args.offline else args.refresh.replace("-", "_")
        refusal = bind_refusal(args.host)
        if refusal is None and mode == "on_open" and not loopback:
            refusal = (
                f"refusing to serve on {args.host}: on-open refresh lets the page start downloads, so it is for"
                " loopback binds only; use --refresh scheduler or --refresh off"
            )
        if refusal is not None:  # before the app, the database or the scheduler exist
            print(refusal, file=sys.stderr)
            return 2
        uvicorn.run(
            create_app(
                settings,
                collection_mode=mode,
                routers=[research_router()],
                record_ops=True,
                # Unauthenticated, and it names the process, backups and errors: loopback binds only, unless opted in.
                ops_status_enabled=loopback or os.environ.get("NZSTATS_OPS_STATUS") == "1",
                capabilities={"research_public": public_research_enabled()},
            ),
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
