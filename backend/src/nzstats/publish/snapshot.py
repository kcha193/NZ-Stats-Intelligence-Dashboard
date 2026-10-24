"""Export a public snapshot from the private database.

The exporter does not compute anything. It copies the database (SQLite backup API), runs the existing FastAPI
application over the copy with a fixed clock, and records the responses. Each payload is therefore exactly what
the API serves, produced by the unchanged production code and response models.
"""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from nzstats.api.app import create_app
from nzstats.clock import utc_now
from nzstats.config import load_settings
from nzstats.publish.contract import (
    ATTRIBUTION,
    MANIFEST,
    ORIGIN_FIXTURE,
    ORIGIN_PRODUCTION,
    REQUIRED_REVISIONS,
    REQUIRED_SERIES,
    SCHEMA_VERSION,
    CalendarMeta,
    content_hash,
    dumps,
    kind_of,
    snapshot_id,
    validate_payload,
)
from nzstats.publish.provenance import is_fixture_data
from nzstats.publish.reconcile import reconcile_with_database

EXPORTER_VERSION = "1"
COUNTRY_WINDOW = {"months": 12, "top": 15}  # the only window the frontend requests


class SnapshotError(RuntimeError):
    """The snapshot could not be produced or did not pass its own checks. Nothing is written."""


class FixtureDataError(SnapshotError):
    """The data directory holds test fixtures, which are never published as releases."""


class MissingDataError(SnapshotError):
    """Expected categories or series are absent from the database."""


def _copy_database(src: Path, dest_dir: Path) -> Path:
    """Consistent copy of a (possibly live, WAL-mode) database. The source is opened read-only."""
    if not src.exists():
        raise SnapshotError(f"database not found: {src}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "nzstats.db"
    source = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=30)
    try:
        target = sqlite3.connect(dest)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()
    return dest


def _public_health(health: dict[str, Any]) -> dict[str, Any]:
    """Sources and counts only. The ingestion log and per-source error text stay private."""
    return {
        **health,
        "database_ok": True,  # read from a working copy at export time; says nothing about the live host
        "sources": [{**s, "detail": None} for s in health["sources"]],
        "recent_runs": [],
    }


def _public_overview(overview: dict[str, Any]) -> dict[str, Any]:
    return {**overview, "freshness": [{**s, "detail": None} for s in overview["freshness"]]}


class _Collector:
    def __init__(self) -> None:
        self.payloads: dict[str, Any] = {}

    def add(self, path: str, payload: Any) -> None:
        validate_payload(
            kind_of(path), payload
        )  # the API's own models; an unexpected shape stops the export
        self.payloads[path] = payload


def _collect(api: TestClient, conn: sqlite3.Connection) -> _Collector:
    out = _Collector()
    missing: list[str] = []

    def get(url: str, params: dict[str, Any] | None = None, *, required: bool = True) -> Any:
        r = api.get(url, params=params)
        if r.status_code == 404 and not required:
            return None
        if r.status_code != 200:
            if r.status_code == 404:
                missing.append(url)
                return None
            raise SnapshotError(f"{url} returned HTTP {r.status_code}")
        return r.json()

    overview = get("/api/overview")
    health = get("/api/health")
    cpi = get("/api/cpi")
    ect = get("/api/ect")
    countries = get("/api/migration/countries", COUNTRY_WINDOW)
    listing: list[dict[str, Any]] = []
    while True:
        page = get("/api/releases", {"limit": 200, "offset": len(listing)})
        listing += page
        if len(page) < 200:
            break
    calendar = get("/api/calendar", {"from": date.min.isoformat(), "to": date.max.isoformat()})

    keys = [
        r["key"]
        for r in conn.execute(
            "SELECT s.key FROM series s WHERE s.category = 'migration'"
            " AND EXISTS (SELECT 1 FROM vintage v WHERE v.series_id = s.id) ORDER BY s.key"
        )
    ]
    series = {k: get(f"/api/series/{k}") for k in keys}
    revisions = {k: get(f"/api/revisions/{k}", required=False) for k in keys}
    for k in REQUIRED_SERIES:
        if k not in series:
            missing.append(f"series {k}")
    for k in REQUIRED_REVISIONS:
        if revisions.get(k) is None:
            missing.append(f"revisions {k}")
    details = {r["id"]: get(f"/api/releases/{r['id']}") for r in listing}
    if missing:
        names = {"/api/cpi": "CPI (cpi)", "/api/ect": "card transactions (ect)"}
        raise MissingDataError(
            "expected data is missing from the database: "
            + ", ".join(names.get(m, m) for m in missing)
        )

    out.add("overview.json", _public_overview(overview))
    out.add("health.json", _public_health(health))
    out.add("cpi.json", cpi)
    out.add("ect.json", ect)
    out.add("releases.json", listing)
    out.add("calendar.json", CalendarMeta.model_validate(calendar).model_dump(mode="json"))
    out.add("migration/countries.json", countries)
    for rid, detail in details.items():
        out.add(f"releases/{rid}.json", detail)
    for k, payload in series.items():
        out.add(f"series/{k}.json", payload)
    for k, payload in revisions.items():
        if payload is not None:
            out.add(f"revisions/{k}.json", payload)
    return out


def _write(
    out_dir: Path, payloads: dict[str, Any], *, origin: str, now: datetime
) -> dict[str, Any]:
    sid = snapshot_id({p: content_hash(v) for p, v in payloads.items()})
    import hashlib

    files: dict[str, dict[str, Any]] = {}
    for path, payload in sorted(payloads.items()):
        text = dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "kind": kind_of(path),
                "snapshot_id": sid,
                "payload": payload,
            }
        )
        target = out_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        data = text.encode("utf-8")
        target.write_bytes(data)
        files[path] = {
            "kind": kind_of(path),
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
        }
    overview = payloads["overview.json"]
    listing = payloads["releases.json"]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "exporter_version": EXPORTER_VERSION,
        "origin": origin,
        "snapshot_id": sid,
        "generated_at": now.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data_updated_at": overview["data_updated_at"],
        "counts": {
            "releases": len(listing),
            "published_releases": sum(
                1 for r in listing if r["status"] in ("published", "corrected")
            ),
            "releases_with_analysis": sum(1 for r in listing if r["has_analysis"]),
            "series_files": sum(1 for p in payloads if p.startswith("series/")),
            "files": len(files),
            "bytes": sum(f["bytes"] for f in files.values()),
        },
        "attribution": ATTRIBUTION,
        "files": files,
    }
    (out_dir / MANIFEST).write_text(dumps(manifest), encoding="utf-8")
    return manifest


def export_snapshot(
    data_dir: Path,
    out_dir: Path,
    *,
    now: datetime | None = None,
    allow_fixtures: bool = False,
) -> dict[str, Any]:
    """Write a validated snapshot of `data_dir` to `out_dir` and return its manifest.

    Either the whole snapshot is produced and has passed validation and reconciliation, or `out_dir` is left as it
    was. Fixture data is refused unless `allow_fixtures`, and is then labelled `origin: "fixture"` so it can never
    pass `validate --for-publish`.
    """
    from nzstats.publish.validate import validate_snapshot

    data_dir, out_dir = Path(data_dir), Path(out_dir)
    logging.getLogger("httpx").setLevel(
        logging.WARNING
    )  # one INFO line per in-process request is noise
    now = now or utc_now()
    fixture = is_fixture_data(data_dir)
    if fixture and not allow_fixtures:
        raise FixtureDataError(
            f"{data_dir} was built from test fixtures and cannot be exported as Stats NZ releases"
        )
    if out_dir.exists() and (out_dir / MANIFEST).exists() is False and any(out_dir.iterdir()):
        raise SnapshotError(
            f"{out_dir} is not empty and is not a snapshot; refusing to overwrite it"
        )

    with tempfile.TemporaryDirectory(prefix="nzstats-export-") as tmp:
        work = Path(tmp)
        db = _copy_database(data_dir / "nzstats.db", work / "db")
        env = {"NZSTATS_DATA_DIR": str(work / "db")}
        if "NZSTATS_SOURCES_FILE" in os.environ:
            env["NZSTATS_SOURCES_FILE"] = os.environ["NZSTATS_SOURCES_FILE"]
        app = create_app(load_settings(env))
        app.state.now = lambda: now
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        try:
            with TestClient(app) as api:
                collected = _collect(api, conn)
            origin = ORIGIN_FIXTURE if fixture else ORIGIN_PRODUCTION
            staging = work / "snapshot"
            manifest = _write(staging, collected.payloads, origin=origin, now=now)
            problems = reconcile_with_database(collected.payloads, conn)
        finally:
            conn.close()
        if problems:
            raise SnapshotError(
                "snapshot does not reconcile with the database: " + "; ".join(problems)
            )
        report = validate_snapshot(staging, scrub=(str(data_dir), str(work), str(Path.home())))
        if report.errors:
            raise SnapshotError("snapshot failed validation: " + "; ".join(report.errors))
        if out_dir.exists():
            shutil.rmtree(out_dir)
        out_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(staging, out_dir)
    return manifest
