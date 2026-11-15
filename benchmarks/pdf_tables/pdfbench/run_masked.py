"""Masked, counts-only diagnostics of one stored document version, on the owner's machine.

Run from the repository root (NZSTATS_DATA_DIR defaults to ./data). The database is opened read-only, the version
passes the same registry gate as table extraction, and the stored bytes must match their recorded SHA-256. It prints
only `emit` output: no text, figure, coordinate, path or exception message from the document.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sqlite3
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

from nzstats.research.table_ingest import _VERSION, version_refusal  # same query and gate as `tables extract`
from nzstats.sources.artifacts import valid_rel

from pdfbench.masked import diagnose, emit


class VersionUnavailable(Exception):
    """Raised with a fixed code only: refused, unavailable or hash_mismatch."""


def load_version(
    conn: sqlite3.Connection,
    version_id: int,
    raw_root: Path,
    registry: Mapping,
    refusal: Callable = version_refusal,
) -> bytes:
    row = conn.execute(_VERSION, (version_id,)).fetchone()
    reason, inst = refusal(row, registry)
    if reason or inst is None or row["format"] != "pdf":
        raise VersionUnavailable("refused")
    path = row["path"]
    if not path or not valid_rel(path) or not (raw_root / path).is_file():
        raise VersionUnavailable("unavailable")
    body = (raw_root / path).read_bytes()
    if hashlib.sha256(body).hexdigest() != row["raw_sha256"]:
        raise VersionUnavailable("hash_mismatch")
    return body


def main(argv: list[str] | None = None) -> int:
    from nzstats.research.registry import load_registry

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("version_id", type=int)
    parser.add_argument("--pages", type=int, nargs="+", default=[5, 8])
    args = parser.parse_args(argv)
    data = Path(os.environ.get("NZSTATS_DATA_DIR", "./data"))
    conn = sqlite3.connect(f"file:{(data / 'nzstats.db').resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        body = load_version(conn, args.version_id, data / "raw", load_registry())
    except VersionUnavailable as exc:
        sys.stdout.write(emit({"error": str(exc)}) + "\n")
        return 1
    finally:
        conn.close()
    sys.stdout.write(emit(diagnose(body, args.pages)) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
