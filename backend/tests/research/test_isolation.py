"""The research domain is separate from the Stats NZ pipeline, in both directions (AST checks)."""

import ast
from pathlib import Path

import nzstats

ROOT = Path(nzstats.__file__).parent
STATS_NZ_PACKAGES = (
    "adapters", "pipeline", "validate", "stats", "insights", "scheduler", "api", "publish", "store",
    "sources",
)  # fmt: skip
# What research code may use from the rest of the backend.
RESEARCH_MAY_IMPORT = (
    "nzstats.research", "nzstats.sources.fetcher", "nzstats.sources.artifacts", "nzstats.store.db",
    "nzstats.store.repo", "nzstats.domain", "nzstats.clock", "nzstats.config",
)  # fmt: skip


def _imports(path: Path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_no_stats_nz_module_imports_research():
    paths = [p for pkg in STATS_NZ_PACKAGES for p in (ROOT / pkg).rglob("*.py")]
    paths += [p for p in ROOT.glob("*.py") if p.name != "cli.py"]  # cli.py is the wiring
    offenders = {
        str(p.relative_to(ROOT))
        for p in paths
        if any(n.startswith("nzstats.research") for n in _imports(p))
    }
    assert paths and offenders == set()


def test_research_uses_only_the_shared_infrastructure():
    for path in (ROOT / "research").rglob("*.py"):
        internal = {n for n in _imports(path) if n.startswith("nzstats")}
        assert all(n.startswith(RESEARCH_MAY_IMPORT) for n in internal), (path.name, internal)


def test_research_never_writes_the_statistical_tables():
    for path in (ROOT / "research").rglob("*.py"):
        source = path.read_text()
        for table in ("release", "series", "vintage", "observation", "ingest_run", "source_health"):
            for verb in ("INSERT INTO", "UPDATE", "DELETE FROM"):
                assert f"{verb} {table} " not in source and f"{verb} {table}(" not in source, (
                    path.name
                )


def test_research_models_never_shadow_a_stats_nz_api_model():
    # OpenAPI components are keyed by class name: a clash silently replaces one schema with the other.
    import inspect

    from pydantic import BaseModel

    import nzstats.models as stats_models
    import nzstats.research.api_models as research_models

    def names(module):
        return {n for n, c in inspect.getmembers(module, inspect.isclass) if issubclass(c, BaseModel)
                and c.__module__ == module.__name__}  # fmt: skip

    assert names(research_models) and not names(research_models) & names(stats_models)
