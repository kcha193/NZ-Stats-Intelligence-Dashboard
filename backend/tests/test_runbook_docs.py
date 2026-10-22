"""The CPI recovery runbook must only recommend backups that are safe for a live WAL database.

Review #6 (P2): `cp data/nzstats.db` can miss committed transactions that still sit in `nzstats.db-wal`, and
`nzstats backup` without a destination is rejected by the CLI.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from nzstats.cli import main

REPO = Path(__file__).resolve().parents[2]
RUNBOOK = REPO / "docs" / "cpi-release-runbook.md"


def _shell_lines() -> list[str]:
    text = RUNBOOK.read_text(encoding="utf-8")
    blocks = re.findall(r"```sh\n(.*?)```", text, flags=re.DOTALL)
    return [ln.strip() for block in blocks for ln in block.splitlines() if ln.strip()]


def test_runbook_never_copies_the_live_database_file() -> None:
    offenders = [ln for ln in _shell_lines() if re.search(r"\b(cp|rsync|scp)\b.*nzstats\.db", ln)]
    assert offenders == []


def test_every_nzstats_backup_command_names_a_destination() -> None:
    for line in _shell_lines():
        match = re.search(r"\bnzstats backup\b(.*)", line)
        if match:
            assert match.group(1).split("#")[0].strip(), f"backup without a destination: {line}"


def test_bare_backup_is_rejected_by_the_cli() -> None:
    """Guards the premise of the test above: the CLI really does require a positional destination."""
    with pytest.raises(SystemExit) as exc:
        main(["backup"])
    assert exc.value.code == 2


def test_runbook_backs_up_with_the_supported_script_before_ingesting() -> None:
    lines = _shell_lines()
    backup = next(i for i, ln in enumerate(lines) if "scripts/backup.sh" in ln)
    # The recovery sequence is the last ingest in the runbook; the manual-run block above it is generic.
    ingest = max(i for i, ln in enumerate(lines) if "nzstats ingest" in ln)
    assert backup < ingest
    assert (REPO / "scripts" / "backup.sh").is_file()


def test_runbook_ingests_where_the_database_lives() -> None:
    """`cd backend` made a bare `nzstats ingest` resolve ./data to backend/data, not the deployed database."""
    lines = _shell_lines()
    assert not any("cd backend" in ln for ln in lines)
    ingests = [ln for ln in lines if "ingest --release-key" in ln]
    assert ingests
    assert all(ln.startswith(("docker compose exec nzstats", "scripts/run.sh")) for ln in ingests)
