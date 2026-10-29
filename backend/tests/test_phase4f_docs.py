"""The Phase 4F specification and runbook must describe what the code actually does."""

from __future__ import annotations

import re
from dataclasses import fields
from pathlib import Path

import pytest

from nzstats.cli import main
from nzstats.ops.thresholds import Thresholds

REPO = Path(__file__).resolve().parents[2]
SPEC = (REPO / "docs" / "phase-4f-operational-health.md").read_text(encoding="utf-8")
RUNBOOK = (REPO / "docs" / "phase-4f-runbook.md").read_text(encoding="utf-8")
SRC = REPO / "backend" / "src" / "nzstats"


def test_the_threshold_table_matches_the_code() -> None:
    block = SPEC.split("<!-- thresholds:start -->")[1].split("<!-- thresholds:end -->")[0]
    documented = {
        m.group(1): m.group(2) for m in re.finditer(r"^\| `(\w+)` \| (\d+) \|", block, flags=re.M)
    }
    actual = {f.name: str(getattr(Thresholds(), f.name)) for f in fields(Thresholds)}
    assert documented == actual


def test_every_issue_key_in_the_spec_is_raised_by_the_code() -> None:
    table = SPEC.split("## Checks, keys, severities and actions")[1].split("## Thresholds")[0]
    keys = re.findall(r"^\| `([a-z_]+:[a-z_]+)(?::<\w+>)?`", table, flags=re.M)
    assert len(keys) >= 17
    code = "".join(
        (SRC / "ops" / name).read_text(encoding="utf-8") for name in ("health.py", "collect.py")
    )
    missing = [k for k in keys if f'"{k}' not in code and f'f"{k}' not in code]
    assert missing == []


def _commands() -> list[list[str]]:
    blocks = re.findall(r"```sh\n(.*?)```", RUNBOOK, flags=re.DOTALL)
    out = []
    for line in (ln.strip() for b in blocks for ln in b.splitlines()):
        match = re.search(r"(?:scripts/run\.sh|nzstats)\s+(.*)", line.split("#")[0])
        if match and match.group(1).split():
            out.append(match.group(1).split())
    return out


def test_the_runbook_names_only_real_subcommands() -> None:
    known = set(re.findall(r"[{,]([a-z-]+)", _help()))
    for argv in _commands():
        first = next((a for a in argv if not a.startswith("-") and "=" not in a), None)
        # `scripts/run.sh [flags]` with no subcommand is `serve`, the script's default.
        assert first is None or first in known, f"unknown subcommand in runbook: {argv}"


def _help() -> str:
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), pytest.raises(SystemExit):
        main(["--help"])
    return buf.getvalue()


@pytest.mark.parametrize(
    "sub", ["status", "alert-check", "backup", "verify-backup", "restore-backup"]
)
def test_the_commands_the_runbook_relies_on_exist(sub) -> None:
    assert sub in _help()


def test_every_runbook_backup_command_names_a_destination() -> None:
    for argv in _commands():
        if argv[0] == "backup":
            assert [a for a in argv[1:] if a != "--bundle"], f"backup without a destination: {argv}"


def test_the_runbook_never_copies_the_live_database_file() -> None:
    offenders = [
        ln for ln in RUNBOOK.splitlines() if re.search(r"^\s*(cp|rsync|scp)\b.*nzstats\.db", ln)
    ]
    assert offenders == []
