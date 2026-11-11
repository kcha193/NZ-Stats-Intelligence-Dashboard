"""Phase 4AF: table extraction stays inside the research boundary. It is local and offline, reaches only the internal
bank routes, never the public or private gates, a snapshot, the Stats NZ pipeline or a schedule, and changes no
permission (SYNTHETIC FIXTURE)."""

import json
import re

import nzstats
from nzstats.research.registry import load_registry

from .bank_support import synthetic_registry
from .test_bank_isolation import LOCAL, REPO, SRC, imports

TABLE_MODULES = re.compile(r"^nzstats\.research\.table_[a-z]+(\.|$)")
GATES = ("public.py", "api.py", "private.py", "private_api.py")


def test_only_the_research_package_imports_the_table_modules():
    offenders = {
        p.relative_to(SRC).as_posix()
        for p in SRC.rglob("*.py")
        if "research" not in p.relative_to(SRC).parts[:1]
        and any(TABLE_MODULES.match(n) for n in imports(p))
    }
    assert offenders == set()


def test_the_public_and_private_gates_never_import_the_table_modules():
    for name in GATES:
        path = SRC / "research" / name
        assert path.exists(), name
        assert not any(TABLE_MODULES.match(n) for n in imports(path)), name


def test_the_table_modules_never_import_the_network_a_provider_or_the_stats_pipeline():
    banned = re.compile(
        r"^(httpx|requests|urllib\.request|socket|nzstats\.(pipeline|scheduler|sources\.fetcher|adapters|api))(\.|$)"
    )
    allowed_research = {
        "fetch",
        "providers",
        "openrouter",
        "hosted",
        "ingest",
        "discover",
        "summarise",
        "policy",
        "policy_run",
    }
    for path in (SRC / "research").glob("table_*.py"):
        for name in imports(path):
            assert not banned.match(name), (path.name, name)
            parts = name.split(".")
            assert not (
                parts[:2] == ["nzstats", "research"]
                and len(parts) > 2
                and parts[2] in allowed_research
            ), (path.name, name)


def test_the_table_modules_are_not_scheduled_or_wired_to_a_workflow():
    mentions = re.compile(r"research tables|table_ingest|extract_version_tables")
    hits = []
    for pattern in ("*.yml", "*.yaml", "*.toml", "*.sh", "Dockerfile*", "*.plist"):
        for path in REPO.rglob(pattern):
            rel = path.relative_to(REPO).as_posix()
            if any(
                part in rel for part in ("node_modules/", ".venv/", ".worktrees/", ".git/", "docs/")
            ):
                continue
            if mentions.search(path.read_text(errors="ignore")):
                hits.append(rel)
    assert hits == []
    scheduler = [p for p in (SRC / "scheduler").rglob("*.py") if mentions.search(p.read_text())]
    assert scheduler == []


def test_the_exporter_and_snapshot_code_know_nothing_of_table_rows():
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(SRC).as_posix()
        if rel.startswith(("publish/", "api/")) or "snapshot" in rel or "export" in rel:
            assert "research_table" not in path.read_text(), rel


def test_no_permission_field_of_any_real_bank_changed_and_none_is_permitted():
    registry = load_registry()
    for key in ("anz", "asb", "bnz", "westpac", "kiwibank"):
        inst = registry[key]
        assert not inst.source_permitted and not inst.manual_import_allowed, key
        assert inst.llm_processing.value == "denied", key


def test_synthetic_registry_is_not_a_real_bank():
    assert set(synthetic_registry()) & {"anz", "asb", "bnz", "westpac", "kiwibank"} == set()
    assert json.dumps(sorted(synthetic_registry()))  # keeps imports used
    assert nzstats.__file__ and LOCAL
