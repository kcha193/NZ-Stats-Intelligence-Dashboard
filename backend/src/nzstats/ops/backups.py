"""Find the newest native backup and say how old and how sound it looks, without opening any database."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from nzstats.clock import from_utc_iso, to_akl_iso
from nzstats.ops.report import BackupEntry, BackupInfo
from nzstats.ops.thresholds import Thresholds
from nzstats.store.backup_bundle import MANIFEST, quick_problems, read_manifest


def _entry(path: Path, now: datetime) -> BackupEntry | None:
    mtime = datetime.fromtimestamp(path.stat().st_mtime, UTC)
    if path.is_dir():
        if (
            path.name.startswith(".")
            and ".partial" in path.name
            and (now - mtime).total_seconds() < 900
        ):
            return None  # a backup being written right now is not a failed one
        manifest = read_manifest(path)
        legacy = path / "nzstats.db"
        if manifest is None and legacy.is_file():
            # An earlier manual backup: a directory holding the database alone. Counted, but never "verified".
            stamp = datetime.fromtimestamp(legacy.stat().st_mtime, UTC)
            wal = legacy.with_name("nzstats.db-wal")
            problems = (
                [f"{wal.name} holds data: not taken with `nzstats backup`"]
                if wal.is_file() and wal.stat().st_size
                else []
            )
            return _build(
                path,
                "file",
                stamp,
                now,
                "unverified" if not problems else "incomplete",
                None,
                problems,
            )
        if manifest is None:
            if path.name.startswith(("nzstats-", ".")) and (
                path.name.startswith("nzstats-") or ".partial" in path.name
            ):
                return _build(
                    path,
                    "bundle",
                    mtime,
                    now,
                    "incomplete",
                    None,
                    ["no manifest: an unfinished or damaged set"],
                )
            return None
        created = from_utc_iso(manifest["created_at"]) if manifest.get("created_at") else mtime
        problems = quick_problems(path)
        recorded = manifest.get("verified")
        if problems:
            state = "incomplete"
        elif recorded is None:
            state = "unverified"
        else:
            state = "verified" if recorded.get("ok") else "failed"
        raw = (manifest.get("raw") or {}).get("count")
        return _build(path, "bundle", created, now, state, raw, problems)
    if path.suffix == ".db" and path.is_file():
        wal = path.with_name(path.name + "-wal")
        problems = (
            [f"{wal.name} sits beside it: not taken with `nzstats backup`"]
            if wal.is_file() and wal.stat().st_size
            else []
        )
        return _build(
            path, "file", mtime, now, "unverified" if not problems else "incomplete", None, problems
        )
    return None


def _build(path, kind, created, now, verification, raw, problems) -> BackupEntry:
    return BackupEntry(
        name=path.name,
        kind=kind,
        created_at=to_akl_iso(created),
        age_hours=round((now - created).total_seconds() / 3600, 1),
        verification=verification,
        raw_artifacts=raw,
        problems=problems,
    )


def scan_backups(directory: Path, now: datetime, t: Thresholds | None = None) -> BackupInfo:
    t = t or Thresholds()
    entries: list[BackupEntry] = []
    if directory.is_dir():
        for child in sorted(directory.iterdir()):
            if child.name in {MANIFEST, ".DS_Store"}:
                continue
            try:
                entry = _entry(child, now)
            except (OSError, ValueError, TypeError, AttributeError, KeyError):
                # One unreadable or malformed backup must not blind every other check: report it as incomplete.
                entry = _build(
                    child, "bundle", now, now, "incomplete", None, ["unreadable or malformed"]
                )
            if entry is not None:
                entries.append(entry)
    entries.sort(key=lambda e: e.age_hours)
    latest = entries[0] if entries else None
    good = next(
        (e for e in entries if e.verification in ("verified", "unverified") and not e.problems),
        None,
    )
    if latest is None:
        state = "none"
    elif latest.verification in ("failed", "incomplete"):
        state = "failed"
    elif good is None or good.age_hours >= t.backup_attention_days * 24:
        state = "stale"
    else:
        state = "ok"
    return BackupInfo(
        directory=directory.name,
        state=state,
        latest=latest,
        latest_good=good,
        entries_seen=len(entries),
    )
