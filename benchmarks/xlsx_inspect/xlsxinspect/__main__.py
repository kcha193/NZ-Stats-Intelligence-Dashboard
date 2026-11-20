"""`python -m xlsxinspect PATH [--expect-sha256 HEX]`: one guarded JSON line on stdout. Exit 0 inspected, 2 otherwise.

Every failure, including an unexpected one, is a fixed code on stdout; stderr stays empty, so no path, part name or
document text can leave through a traceback.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import sys
from pathlib import Path

from xlsxinspect.guard import emit
from xlsxinspect.inspect import MAX_ARCHIVE, inspect
from xlsxinspect.layout import layout


def _run(args: argparse.Namespace) -> tuple[dict, int]:
    path: Path = args.path
    if path.stat().st_size > MAX_ARCHIVE:  # refuse before reading a byte
        return {"status": "refused"}, 2
    raw = path.read_bytes()
    if args.expect_sha256 and hashlib.sha256(raw).hexdigest() != args.expect_sha256.lower():
        return {"status": "refused"}, 2
    # the bytes that were hashed, not a second read
    result = layout(raw) if args.layout else inspect(path, raw=raw)
    return result, 0 if result["status"] == "ok" else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="xlsxinspect")
    parser.add_argument("path", type=Path)
    parser.add_argument("--expect-sha256", help="refuse unless the file has exactly this SHA-256")
    parser.add_argument("--layout", action="store_true", help="masked layout probe (Phase 4AO): indices and counts")
    args = parser.parse_args(argv)
    sink = io.StringIO()
    try:
        with contextlib.redirect_stderr(sink):
            result, code = _run(args)
        line = emit(result)
    except Exception:  # noqa: BLE001 - only a fixed code may leave, never a message, path or traceback
        line, code = emit({"status": "error"}), 2
    print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
