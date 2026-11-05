"""Owner-run, read-only: compare the dedicated OpenRouter key's spend with the local ledger.

    set -a; . ./.env; set +a; backend/.venv/bin/python scripts/openrouter_key_reading.py

Reads NZSTATS_LLM_API_KEY from the environment, makes one GET to the key-metadata endpoint (no inference, no spend), and prints numbers and
booleans only. The key is never printed. Writes data/phase-4r/key-reading.json (private).
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

import httpx

from nzstats.research.key_reading import read_key
from nzstats.research.pilot import PilotRefused


def main() -> int:
    data = Path(os.environ.get("NZSTATS_DATA_DIR", "data")).resolve()
    conn = sqlite3.connect(f"{(data / 'nzstats.db').as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        with httpx.Client() as client:
            reading = read_key(client, os.environ.get("NZSTATS_LLM_API_KEY", ""), conn)
    except PilotRefused as exc:
        print(f"refused: {exc}")
        return 2
    out = data / "phase-4r" / "key-reading.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(reading, handle, indent=2)
    for key, value in reading.items():
        print(f"{key}: {value}")
    return 0 if reading["usage_matches_ledger"] and reading["byok_is_zero"] else 1


if __name__ == "__main__":
    sys.exit(main())
