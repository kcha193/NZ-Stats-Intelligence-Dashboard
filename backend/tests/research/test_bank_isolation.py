"""Phase 4AE: bank research stays inside the loopback research boundary and never touches the Stats NZ pipeline, the
public site, a schedule, or committed frontend data (SYNTHETIC FIXTURE)."""

import ast
import re
from pathlib import Path

import nzstats
from nzstats.api.app import create_app  # noqa: F401  (imported to prove the public app builds without bank code)
from nzstats.research import store
from nzstats.research.api import research_router
from nzstats.research.ingest import run_institution
from nzstats.research.private_api import CLIENT_HEADER, private_research_router

from .bank_support import synthetic_registry
from .conftest import NOW
from .llm_support import seed_version
from .support import BASE, ROBOTS, Site, institution, research_fetcher
from .test_drafts_auto import store_hosted

SRC = Path(nzstats.__file__).parent
REPO = SRC.parents[2]  # backend/src/nzstats -> repo root
LOCAL = {"host": "127.0.0.1:8000", CLIENT_HEADER: "dashboard"}
REAL_BANKS = re.compile(r"\b(ANZ|ASB|BNZ|Westpac|Kiwibank)\b", re.IGNORECASE)
NEAR_A_NUMBER = re.compile(r"\d")


def imports(path: Path) -> set[str]:
    out = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
            out.update(f"{node.module}.{a.name}" for a in node.names)
    return out


def test_only_research_and_the_cli_wiring_import_the_bank_modules():
    bank = re.compile(r"^nzstats\.research\.(banks?(_[a-z]+)?)(\.|$)")
    offenders = {
        p.relative_to(SRC).as_posix()
        for p in SRC.rglob("*.py")
        if "research" not in p.relative_to(SRC).parts[:1] and any(bank.match(n) for n in imports(p))
    }
    assert offenders == set()


def test_the_bank_routes_are_mounted_only_from_the_draft_router():
    mounting = {
        p.relative_to(SRC).as_posix()
        for p in SRC.rglob("*.py")
        if "bank_router" in p.read_text() and p.name not in ("bank_api.py",)
    }
    assert mounting == {"research/drafts_api.py"}


def test_public_and_private_apis_return_no_bank_item(make):
    build, conn = make
    reg = synthetic_registry()
    store_hosted(conn, seed_version(conn, key="bank_a", doc="research/outlook/q4"))
    client = build(
        routers=[
            research_router(enabled=True, registry=lambda: reg),
            private_research_router(enabled=True, registry=lambda: reg),
        ]
    )
    for route, headers in (("/api/research/feed", {}), ("/api/private/research/items", LOCAL)):
        body = client.get(route, headers=headers).text
        assert "bank_a" not in body and "Example Bank A" not in body, route


def test_one_banks_blocked_run_does_not_touch_another_banks_run(conn):
    good = Site({ROBOTS: "", f"{BASE}/research/": '<a href="/x">x</a>'})
    blocked = Site({ROBOTS: "", f"{BASE}/research/": (403, {}, b"no")})
    a, b = institution("bank_a"), institution("bank_b")
    run_institution(conn, a, research_fetcher(a, blocked), now_fn=lambda: NOW)
    before = conn.execute(
        "SELECT h.state FROM research_source_health h JOIN research_institution i ON i.id = h.institution_id"
        " WHERE i.key = 'bank_a'"
    ).fetchone()[0]
    result_b = run_institution(conn, b, research_fetcher(b, good), now_fn=lambda: NOW)
    states = dict(
        conn.execute(
            "SELECT i.key, h.state FROM research_source_health h JOIN research_institution i"
            " ON i.id = h.institution_id"
        ).fetchall()
    )
    assert (
        before == "blocked" and states["bank_a"] == "blocked"
    )  # bank_b's run changed nothing of bank_a's
    assert result_b.outcome != "refused" and states["bank_b"] != "blocked"
    assert store.last_attempt_runs(conn, 1) is not None


def test_no_schedule_cron_or_workflow_mentions_a_bank_command_or_module():
    pattern = re.compile(
        r"bank-status|bank_(view|api|status|analytics)|research\s+(ingest|discover|import)"
    )
    files = [
        *SRC.joinpath("scheduler").rglob("*.py"),
        *REPO.joinpath("scripts").glob("*.sh"),
        *REPO.glob("Dockerfile*"),
        *REPO.glob("docker-compose*.y*ml"),
        *REPO.joinpath(".github").rglob("*.y*ml"),
    ]
    assert files
    offenders = [p.relative_to(REPO).as_posix() for p in files if pattern.search(p.read_text())]
    assert offenders == []


def test_committed_frontend_and_script_data_never_put_a_real_bank_beside_a_number():
    """Fictitious banks only in committed frontend data: a real bank name within 40 characters of a digit is refused."""
    roots = [REPO / "frontend" / "src", REPO / "frontend" / "e2e", REPO / "scripts"]
    offenders = []
    for root in roots:
        for p in root.rglob("*"):
            if (
                p.suffix not in {".ts", ".tsx", ".json", ".py", ".sh", ".md"}
                or "node_modules" in p.parts
            ):
                continue
            text = p.read_text(errors="ignore")
            for m in REAL_BANKS.finditer(text):
                window = text[max(0, m.start() - 40) : m.end() + 40]
                if NEAR_A_NUMBER.search(window):
                    offenders.append(f"{p.relative_to(REPO).as_posix()}: {m.group(0)}")
    assert offenders == []
