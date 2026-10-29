"""`scripts/run.sh` must let the caller's environment override `.env`.

Phase 4E internal readiness: `.env` sets `NZSTATS_DATA_DIR=./data`, and the script sourced it after the caller's
environment. `NZSTATS_DATA_DIR=/isolated/copy scripts/run.sh` therefore served the production database (and, without
`--no-scheduler`, started jobs that contact Stats NZ) instead of the copy the runbook asks for.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
STUB = '#!/bin/sh\nprintf "%s|%s\\n" "$NZSTATS_DATA_DIR" "$*"\n'


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


def _run(checkout: Path, env_file: str | None, **env: str) -> str:
    if env_file is not None:
        (checkout / ".env").write_text(env_file)
    base = {k: v for k, v in os.environ.items() if not k.startswith("NZSTATS_")}
    result = subprocess.run(
        ["bash", str(checkout / "scripts" / "run.sh"), "health"],
        env={**base, "PYTHON": sys.executable, **env},
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip().splitlines()[-1].split("|")[0]


def test_caller_data_dir_overrides_env_file(checkout: Path, tmp_path: Path) -> None:
    copy = tmp_path / "isolated-copy"
    assert _run(checkout, "NZSTATS_DATA_DIR=./data\n", NZSTATS_DATA_DIR=str(copy)) == str(copy)


def test_env_file_applies_when_the_caller_sets_nothing(checkout: Path) -> None:
    assert _run(checkout, "NZSTATS_DATA_DIR=./elsewhere\n") == "./elsewhere"


def test_default_data_dir_without_env_file(checkout: Path) -> None:
    assert _run(checkout, None) == str(checkout / "data")
