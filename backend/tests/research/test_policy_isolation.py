"""Phase 4W: the only path to a paid request is `run-policy`. No server, scheduler, refresh or API route can reach it.

Static (who imports the runner) and dynamic (a fresh interpreter importing the server entry points never loads it).
"""

import ast
import subprocess
import sys
from pathlib import Path

import nzstats

ROOT = Path(nzstats.__file__).parent


def importers(module: str) -> set[str]:
    found = set()
    for path in ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
            elif isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            if module in names:
                found.add(str(path.relative_to(ROOT)))
    return found


def test_only_the_policy_commands_import_the_runner_and_only_the_cli_imports_those():
    assert importers("nzstats.research.policy_run") == {"research/policy_cli.py"}
    assert importers("nzstats.research.policy_cli") == {"research/cli.py"}


def test_nothing_but_the_runner_and_its_handlers_imports_pilot_execute_for_policies():
    assert {"research/policy_run.py", "research/policy_cli.py"} <= importers(
        "nzstats.research.pilot"
    )
    for forbidden in ("api", "scheduler", "pipeline", "publish", "sources"):
        assert not any(p.startswith(f"{forbidden}/") for p in importers("nzstats.research.pilot"))
        assert not any(
            p.startswith(f"{forbidden}/") for p in importers("nzstats.research.policy_run")
        )


def test_the_policy_audit_table_is_written_only_by_the_policy_module():
    writers = set()
    for path in (ROOT / "research").glob("*.py"):
        text = path.read_text()
        if "INSERT INTO research_policy_event" in text or "UPDATE research_policy_event" in text:
            writers.add(path.name)
    assert writers == {"policy.py"}


def _loaded(entry: str) -> dict[str, bool]:
    code = (
        f"import sys, {entry}\n"
        "print({m: m in sys.modules for m in ('nzstats.research.policy_run', 'nzstats.research.policy_cli',"
        " 'nzstats.research.pilot', 'nzstats.research.openrouter')})"
    )
    out = subprocess.run(
        [sys.executable, "-I", "-c", code], capture_output=True, text=True, check=True
    )
    return eval(out.stdout.strip().splitlines()[-1])  # a dict of bools printed by the line above


def test_importing_the_server_cli_or_api_never_loads_the_paid_request_path():
    for entry in (
        "nzstats.cli",
        "nzstats.api.app",
        "nzstats.research.api",
        "nzstats.research.drafts_api",
    ):
        loaded = _loaded(entry)
        assert (
            not loaded["nzstats.research.policy_run"] and not loaded["nzstats.research.policy_cli"]
        ), entry
        assert not loaded["nzstats.research.pilot"], entry
