"""Local bounded hosted-pilot launcher. No runtime/scheduler construction or migrations."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path

from nzstats.research.pilot import (
    PLANS,
    PilotRefused,
    evaluation_record,
    execute,
    file_sha256,
    freeze,
    load_approval,
    verified_backup,
)
from nzstats.research.registry import load_registry
from pydantic import ValidationError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "execute"))
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--scope",
        type=Path,
        help="JSON mapping of version IDs to proposed ordinal arrays",
    )
    parser.add_argument(
        "--experiment",
        choices=sorted(PLANS),
        help="the reviewed experiment to freeze (execute takes it from the approval)",
    )
    parser.add_argument("--frozen", type=Path)
    parser.add_argument("--approval", type=Path)
    args = parser.parse_args()
    data = args.data_dir.resolve()
    if not args.output.resolve().is_relative_to(data):
        parser.error("sensitive artifacts must stay under the local data directory")
    conn = sqlite3.connect(
        f"{(data / 'nzstats.db').as_uri()}?mode={'ro' if args.action == 'freeze' else 'rw'}",
        uri=True,
        isolation_level=None,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        if args.action == "freeze" and args.scope and args.experiment:
            raw = json.loads(args.scope.read_bytes())
            scopes = {int(k): tuple(v) for k, v in raw.items()}
            freeze(conn, load_registry(), scopes, args.output, PLANS[args.experiment])
            print(
                "Local proposal frozen; no transmission or approval. Review local freeze.json."
            )
        elif args.action == "execute" and args.frozen and args.approval:
            # Either the gold-bound format or a Phase 4T internal-draft authorisation (gold optional).
            approval = load_approval(args.approval.read_bytes())
            execute(
                conn,
                load_registry(),
                data,
                args.frozen,
                approval,
                args.output,
                os.environ.get("NZSTATS_LLM_API_KEY", ""),
                backup_check=verified_backup,
            )
            evaluation = evaluation_record(approval)["human_evaluation"]
            print(
                "Pilot attempt recorded locally; output remains unreviewed. No automatic retry."
                f" Human evaluation: {evaluation.replace('_', ' ')}."
            )
        else:
            parser.error(
                "freeze requires --scope and --experiment; execute requires --frozen and --approval"
            )
        return 0
    except (PilotRefused, ValidationError, OSError, ValueError, sqlite3.Error):
        print(
            "Pilot refused or failed. No automatic retry; inspect local state before proceeding."
        )
        return 2
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
