"""A native backup set: the SQLite database plus every raw artifact it references, with a manifest (Phase 4F).

`nzstats backup DEST` writes only the database. A bundle also carries `raw/`, so a restore does not depend on
re-fetching files Stats NZ may have since replaced. Guarantees:

- Atomic: the set is built in a hidden sibling directory and renamed into place last, so a crash leaves no directory
  that looks complete. An existing destination is never touched.
- Complete or nothing: a referenced artifact that is missing or whose bytes do not match its content-addressed name
  aborts the backup instead of producing a set with a hole in it.
- Verifiable: the manifest records the size and SHA-256 of every file; `verify_bundle` re-checks them and then runs the
  same restore validation as `verify-backup` over the copied database and raw tree.
- Nothing is overwritten on restore: `restore_bundle` refuses a non-empty destination and never writes to the bundle.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from nzstats.clock import to_utc_iso, utc_now
from nzstats.sources.artifacts import valid_rel
from nzstats.store.backup_check import verify_backup

MANIFEST = "MANIFEST.json"
DB_NAME = "nzstats.db"
RAW = "raw"
FORMAT = 1
_IGNORED = {".DS_Store"}


class BackupError(Exception):
    """The backup or restore could not be completed; nothing was left behind or overwritten."""


@dataclass
class BundleReport:
    path: str
    created_at: str | None = None
    schema_version: int | None = None
    raw_artifacts: int | None = None
    verified_at: str | None = None
    needs_migration: bool = (
        False  # an older-schema bundle: valid, but `migrate` is needed after restoring
    )
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_manifest(path: Path) -> dict | None:
    try:
        data = json.loads((path / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("format") == FORMAT else None


def _write_manifest(path: Path, manifest: dict) -> None:
    with (path / MANIFEST).open("w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.flush()
        os.fsync(fh.fileno())


def _referenced(db: Path) -> list[str]:
    conn = sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro&immutable=1", uri=True)
    try:
        return sorted(r[0] for r in conn.execute("SELECT DISTINCT path FROM raw_artifact"))
    finally:
        conn.close()


def create_bundle(
    conn: sqlite3.Connection, raw_dir: Path, dest: Path, *, now: datetime | None = None
) -> BundleReport:
    dest = Path(dest)
    if dest.exists():
        raise BackupError(f"{dest} already exists; backups are never overwritten")
    staging = dest.parent / f".{dest.name}.partial-{os.getpid()}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    staging.mkdir()
    try:
        return _build(conn, Path(raw_dir), staging, dest, now or utc_now())
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _build(
    conn: sqlite3.Connection, raw_dir: Path, staging: Path, dest: Path, now: datetime
) -> BundleReport:
    copy = sqlite3.connect(staging / DB_NAME)
    try:
        conn.backup(copy)
    finally:
        copy.close()
    files, missing, damaged = [], [], []
    for rel in _referenced(staging / DB_NAME):
        source = raw_dir / rel
        if not valid_rel(rel) or source.is_symlink() or not source.is_file():
            missing.append(rel)
            continue
        target = staging / RAW / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        digest = _sha256(target)
        if digest != rel.split("/")[1]:  # content-addressed: the name is the hash
            damaged.append(rel)
            continue
        files.append({"path": rel, "sha256": digest, "bytes": target.stat().st_size})
    if missing or damaged:
        raise BackupError(
            f"backup abandoned, nothing written: {len(missing)} referenced raw artifact(s) missing"
            f" and {len(damaged)} damaged in {raw_dir}"
        )
    manifest = {
        "format": FORMAT,
        "created_at": to_utc_iso(now),
        "database": {
            "file": DB_NAME,
            "sha256": _sha256(staging / DB_NAME),
            "bytes": (staging / DB_NAME).stat().st_size,
        },
        "raw": {"count": len(files), "bytes": sum(f["bytes"] for f in files), "files": files},
        "verified": None,
    }
    _write_manifest(staging, manifest)
    report = verify_bundle(staging)
    if not report.ok:
        raise BackupError("backup abandoned, it failed verification: " + "; ".join(report.problems))
    manifest["verified"] = {
        "at": to_utc_iso(now),
        "ok": True,
        "schema_version": report.schema_version,
    }
    _write_manifest(staging, manifest)
    os.rename(staging, dest)
    report.path = str(dest)
    report.verified_at = manifest["verified"]["at"]
    return report


def quick_problems(path: Path) -> list[str]:
    """Cheap structural check (manifest, presence and sizes; no hashing): safe for a health check to run often."""
    manifest = read_manifest(path)
    if manifest is None:
        return ["the manifest is missing or unreadable"]
    problems = []
    try:
        db = manifest["database"]
        listed = {f["path"]: f["bytes"] for f in manifest["raw"]["files"]}
        if not (path / DB_NAME).is_file() or (path / DB_NAME).stat().st_size != db["bytes"]:
            problems.append("the database file is missing or has the wrong size")
        missing = sum(
            1
            for rel, size in listed.items()
            if not valid_rel(rel)
            or not (path / RAW / rel).is_file()
            or (path / RAW / rel).stat().st_size != size
        )
        if missing:
            problems.append(f"{missing} raw artifact(s) are missing or have the wrong size")
    except (KeyError, TypeError, OSError):
        problems.append("the manifest is malformed")
    return problems


def verify_bundle(path: Path | str) -> BundleReport:
    """Full verification: hashes of every file, then the restore validation over the copied database."""
    path = Path(path)
    report = BundleReport(str(path))
    if not path.is_dir():
        report.problems.append("the backup set is not a directory")
        return report
    manifest = read_manifest(path)
    if manifest is None:
        report.problems.append(
            "the manifest is missing or unreadable (an incomplete or foreign set)"
        )
        return report
    report.created_at = manifest.get("created_at")
    report.verified_at = (manifest.get("verified") or {}).get("at")
    try:
        db, entries = manifest["database"], manifest["raw"]["files"]
        report.raw_artifacts = len(entries)
        if not (path / DB_NAME).is_file():
            report.problems.append("the database file is missing")
        elif _sha256(path / DB_NAME) != db["sha256"]:
            report.problems.append("the database file does not match its recorded checksum")
        listed = set()
        for entry in entries:
            rel = entry["path"]
            listed.add(rel)
            target = path / RAW / rel
            if not valid_rel(rel):
                report.problems.append(f"unsafe raw artifact name {rel!r} in the manifest")
            elif not target.is_file():
                report.problems.append(f"raw artifact {rel} is missing")
            elif _sha256(target) != entry["sha256"] or entry["sha256"] != rel.split("/")[1]:
                report.problems.append(f"raw artifact {rel} does not match its checksum")
    except (KeyError, TypeError, IndexError):
        report.problems.append("the manifest is malformed")
        return report
    for found in sorted((path / RAW).rglob("*")) if (path / RAW).is_dir() else []:
        if (
            found.is_file()
            and found.name not in _IGNORED
            and found.relative_to(path / RAW).as_posix() not in listed
        ):
            report.problems.append(f"unlisted file raw/{found.relative_to(path / RAW).as_posix()}")
    for child in path.iterdir():
        if child.name not in {MANIFEST, DB_NAME, RAW} and child.name not in _IGNORED:
            report.problems.append(f"unexpected entry {child.name}")
    if (path / DB_NAME).is_file() and not any("database file" in p for p in report.problems):
        inner = verify_backup(path / DB_NAME, raw_dir=path / RAW, allow_older_schema=True)
        report.schema_version = inner.schema_version
        if (
            inner.schema_version is not None
            and inner.schema_version < inner.expected_schema_version
        ):
            # Older than this code but otherwise sound: restorable, then `nzstats migrate`.
            report.needs_migration = True
        report.problems.extend(inner.problems)
    return report


def restore_bundle(src: Path | str, dest_data_dir: Path | str) -> BundleReport:
    """Copy a verified bundle into a new data directory. The bundle is only read; an existing database is never replaced."""
    src, dest = Path(src), Path(dest_data_dir)
    report = verify_bundle(src)
    if not report.ok:
        raise BackupError("the backup set failed verification: " + "; ".join(report.problems))
    if dest.exists() and any(dest.iterdir()):
        raise BackupError(
            f"{dest} is not empty; restore into a new directory and switch over deliberately"
        )
    dest.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copyfile(src / DB_NAME, dest / "nzstats.db")
        if (src / RAW).is_dir():
            shutil.copytree(src / RAW, dest / "raw")
        else:
            (dest / "raw").mkdir()
        after = verify_backup(dest / "nzstats.db", raw_dir=dest / "raw", allow_older_schema=True)
        if after.problems:
            raise BackupError("the restored copy failed verification: " + "; ".join(after.problems))
    except BaseException:
        for leftover in ("nzstats.db", "nzstats.db-wal", "nzstats.db-shm"):
            (dest / leftover).unlink(missing_ok=True)
        shutil.rmtree(dest / "raw", ignore_errors=True)
        raise
    report.path = str(dest)
    return report
