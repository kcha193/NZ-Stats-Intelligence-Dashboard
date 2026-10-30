"""`scripts/run.sh` must let the caller's environment override `.env`.

Phase 4E internal readiness: `.env` sets `NZSTATS_DATA_DIR=./data`, and the script sourced it after the caller's
environment. `NZSTATS_DATA_DIR=/isolated/copy scripts/run.sh` therefore served the production database (and, without
`--no-scheduler`, started jobs that contact Stats NZ) instead of the copy the runbook asks for.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
# The stub reports what `nzstats` would have received: its arguments and every NZSTATS_*/STATSNZ_* variable, as JSON.
STUB = """#!/bin/sh
exec "$PYTHON" -c 'import json, os, sys
print(json.dumps({"args": sys.argv[1:], "env": {k: v for k, v in os.environ.items() if k.startswith(("NZSTATS_", "STATSNZ_"))}}))' "$@"
"""


@pytest.fixture()
def checkout(tmp_path: Path) -> Path:
    """A minimal checkout: the real run.sh, a stub `nzstats` and a built UI, so nothing is installed."""
    (tmp_path / "scripts").mkdir()
    shutil.copy(REPO / "scripts" / "run.sh", tmp_path / "scripts" / "run.sh")
    stub = tmp_path / "backend" / ".venv" / "bin" / "nzstats"
    stub.parent.mkdir(parents=True)
    stub.write_text(STUB)
    stub.chmod(0o755)
    (tmp_path / "frontend" / "dist").mkdir(parents=True)
    (tmp_path / "frontend" / "dist" / "index.html").write_text("<!doctype html>")
    return tmp_path


def _invoke(
    checkout: Path, env_file: str | None, args: tuple[str, ...] = ("health",), **env: str
) -> dict:
    if env_file is not None:
        (checkout / ".env").write_text(env_file)
    base = {k: v for k, v in os.environ.items() if not k.startswith(("NZSTATS_", "STATSNZ_"))}
    result = subprocess.run(
        ["bash", str(checkout / "scripts" / "run.sh"), *args],
        env={**base, "PYTHON": sys.executable, **env},
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


def _run(checkout: Path, env_file: str | None, **env: str) -> str:
    return _invoke(checkout, env_file, **env)["env"]["NZSTATS_DATA_DIR"]


def test_caller_data_dir_overrides_env_file(checkout: Path, tmp_path: Path) -> None:
    copy = tmp_path / "isolated-copy"
    assert _run(checkout, "NZSTATS_DATA_DIR=./data\n", NZSTATS_DATA_DIR=str(copy)) == str(copy)


def test_env_file_applies_when_the_caller_sets_nothing(checkout: Path) -> None:
    assert _run(checkout, "NZSTATS_DATA_DIR=./elsewhere\n") == "./elsewhere"


def test_default_data_dir_without_env_file(checkout: Path) -> None:
    assert _run(checkout, None) == str(checkout / "data")


AWKWARD = [
    "two words",
    "",
    "quote \" and ' and \\ backslash",
    "dollar $HOME and `backtick` and $(subshell)",
    "semi; colon && pipe | redirect > glob *",
    "line one\nline two\n",
    "  leading and trailing  ",
    "tilde ~ and # hash",
]


@pytest.mark.parametrize("value", AWKWARD, ids=range(len(AWKWARD)))
def test_caller_values_survive_byte_for_byte(checkout: Path, value: str) -> None:
    """Quoted, empty, multi-line and shell-special values must reach nzstats unchanged and win over .env."""
    got = _invoke(checkout, "NZSTATS_CONTACT=from-env-file\n", NZSTATS_CONTACT=value)
    assert got["env"]["NZSTATS_CONTACT"] == value


def test_both_prefixes_are_restored_and_win_over_the_env_file(checkout: Path) -> None:
    env_file = "NZSTATS_MIN_INTERVAL_SECONDS=10\nSTATSNZ_TOKEN=from-env-file\nNZSTATS_BASE_URL=https://file.example\n"
    got = _invoke(
        checkout, env_file, NZSTATS_MIN_INTERVAL_SECONDS="25", STATSNZ_TOKEN="caller token"
    )
    assert got["env"]["NZSTATS_MIN_INTERVAL_SECONDS"] == "25"
    assert got["env"]["STATSNZ_TOKEN"] == "caller token"
    assert (
        got["env"]["NZSTATS_BASE_URL"] == "https://file.example"
    )  # not set by the caller: the file applies


def test_caller_values_are_never_executed(checkout: Path, tmp_path: Path) -> None:
    marker = tmp_path / "executed"
    _invoke(checkout, "", NZSTATS_CONTACT=f"$(touch {marker}); touch {marker}`touch {marker}`")
    assert not marker.exists()


def test_a_var_the_caller_did_not_export_is_not_invented(checkout: Path) -> None:
    got = _invoke(checkout, "NZSTATS_CONTACT=from-env-file\n")
    assert got["env"]["NZSTATS_CONTACT"] == "from-env-file"
    assert "STATSNZ_TOKEN" not in got["env"]


def test_no_arguments_serves_on_the_system_bash(checkout: Path) -> None:
    """macOS ships bash 3.2, where an empty array under `set -u` is an unbound variable."""
    got = _invoke(checkout, None, args=())
    assert got["args"] == ["serve", "--host", "127.0.0.1"]


def test_arguments_are_passed_through_untouched(checkout: Path) -> None:
    got = _invoke(checkout, None, args=("--no-scheduler", "--port", "9000"))
    assert got["args"] == ["serve", "--host", "127.0.0.1", "--no-scheduler", "--port", "9000"]


@pytest.mark.parametrize(
    "sub", ["status", "alert-check", "verify-backup", "restore-backup", "backup", "migrate"]
)
def test_operational_subcommands_reach_nzstats_instead_of_serve(checkout: Path, sub: str) -> None:
    """`scripts/run.sh status` once fell into the serve branch (`nzstats serve --host ... status`) and failed."""
    got = _invoke(checkout, None, args=(sub, "x"))
    assert got["args"] == [sub, "x"]
