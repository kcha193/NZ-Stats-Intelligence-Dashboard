"""Phase 4AP: an ANZ-shaped forecasts workbook through manual import, `tables extract`, the internal view and purge.

The real registry is used (ANZ's personal-scope manual import route), with a fictional workbook at the workbook's
address. Every figure is invented; no ANZ text, value or sheet name appears here.
"""

from __future__ import annotations

import json
import socket
from dataclasses import replace
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from nzstats.api.app import create_app
from nzstats.cli import main
from nzstats.config import load_settings
from nzstats.research import purge
from nzstats.research.api import research_router
from nzstats.research.drafts_api import internal_drafts_router
from nzstats.research.manual_import import ImportRefused, import_document
from nzstats.research.private_api import CLIENT_HEADER, private_research_router
from nzstats.research.registry import load_registry
from nzstats.research.table_ingest import candidate_hash8, extract_version_tables
from nzstats.research.table_store import load_forecasts, load_rejections
from nzstats.sources.artifacts import ArtifactStore
from nzstats.store.db import connect, migrate

from .conftest import NOW
from .test_xlsx_anz import GDP_AA, GDP_QQ, series, standard
from .xlsx_support import build

WORKBOOK_URL = "https://www.anz.co.nz/content/dam/anzconz/documents/economics-and-market-research/Latest-forecasts.xlsx"
LOCAL = {"host": "127.0.0.1:8000", CLIENT_HEADER: "dashboard"}
FILLER = " ".join(["Fictional filler for the minimum document length."] * 12)


LEGEND = "Figures in bold are ANZ forecasts"  # invented wording
# The analytics compare a GDP figure only when its label states the price basis (real or nominal).
REAL_GDP = [("Real GDP", [("% q/q", series(GDP_QQ)), ("Annual % change", series(GDP_AA))])]


def workbook(as_at: str = "Data as at 5 November 2026", growth=None) -> bytes:
    notes = (LEGEND, f"{as_at}. {FILLER}")
    kw = {"growth_kw": {"notes": notes}, "prices_kw": {"notes": notes}}
    kw["growth"] = REAL_GDP if growth is None else growth
    return build(standard(**kw), drawing_paragraphs=(("Fictional cover text",),))


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*_a, **_k):
        raise AssertionError("the workbook path must not use the network")

    monkeypatch.setattr(socket.socket, "connect", refuse)


@pytest.fixture()
def env(tmp_path):
    settings = load_settings({"NZSTATS_DATA_DIR": str(tmp_path / "data")})
    conn = connect(settings.db_path)
    migrate(conn)
    registry = load_registry()
    return SimpleNamespace(
        settings=settings,
        conn=conn,
        registry=registry,
        artifacts=ArtifactStore(settings.raw_dir),
        tmp=tmp_path,
    )


def do_import(env, body=None, *, url=WORKBOOK_URL, published_on=date(2026, 11, 5), key="anz"):
    return import_document(
        env.conn, env.registry[key], body=body or workbook(), file_format="xlsx", url=url, importer="Test Owner",
        note="saved from a browser (synthetic)", now=NOW, artifacts=env.artifacts, title="ANZ Forecasts",
        published_on=published_on,
    )  # fmt: skip


def extract(env, version, **kw):
    return extract_version_tables(
        env.conn, version, env.artifacts, env.registry, NOW, isolate=False, **kw
    )


def stored_count(env) -> int:
    return env.conn.execute("SELECT COUNT(*) FROM research_table_extraction").fetchone()[0]


def test_import_stores_an_xlsx_version_with_an_audit_record(env):
    result = do_import(env)
    assert result.outcome == "new"
    v = env.conn.execute(
        "SELECT * FROM research_document_version WHERE id = ?", (result.version_id,)
    ).fetchone()
    assert (v["format"], v["acquisition"], v["page_count"]) == ("xlsx", "manual", 3)
    audit = env.conn.execute("SELECT file_format, outcome FROM research_manual_import").fetchall()
    assert [tuple(r) for r in audit] == [("xlsx", "new")]
    pages = [
        r[0] for r in env.conn.execute("SELECT page_start FROM research_section ORDER BY ordinal")
    ]
    assert pages == [2, 3]  # one section per sheet that holds cells, at its sheet position


def test_a_body_that_is_not_a_workbook_is_refused(env):
    with pytest.raises(ImportRefused, match="not an XLSX workbook"):
        do_import(env, body=b"%PDF-1.7 not a workbook")
    assert env.conn.execute("SELECT COUNT(*) FROM research_manual_import").fetchone()[0] == 0


def test_a_duplicate_import_is_unchanged(env):
    first = do_import(env)
    again = do_import(env)
    assert again.outcome == "unchanged" and again.version_id == first.version_id


def test_a_dry_run_counts_codes_and_a_hash_and_writes_nothing(env):
    v = do_import(env).version_id
    result = extract(env, v, dry_run=True)
    assert (result.status, result.forecasts, result.rejections) == ("dry_run", 12, 0)
    assert result.candidate_hash8 is not None and len(result.candidate_hash8) == 8
    assert result.candidate_hash8 == candidate_hash8(result.candidates)
    assert stored_count(env) == 0


def test_storing_needs_the_matching_reconciliation_hash(env):
    v = do_import(env).version_id
    assert extract(env, v).status == "refused"
    wrong = extract(env, v, confirm="00000000")
    assert (wrong.status, wrong.reason) == (
        "refused",
        "confirmation does not match the current candidates",
    )
    assert stored_count(env) == 0
    code = extract(env, v, dry_run=True).candidate_hash8
    stored = extract(env, v, confirm=code)
    assert (stored.status, stored.forecasts) == ("stored", 12)
    assert extract(env, v, confirm=code).status == "unchanged"
    figures = load_forecasts(env.conn, v)
    assert {f.indicator for f in figures} == {"gdp", "cpi_inflation", "unemployment"}
    assert all(f.kind == "forecast" and f.evidence["bold"] and f.evidence["cell"] for f in figures)
    interpreter = env.conn.execute(
        "SELECT interpreter_version FROM research_table_extraction"
    ).fetchone()[0]
    assert interpreter == "xlsx-anz-1"


def test_a_workbook_is_read_only_for_anz_and_only_at_the_workbook_address(env):
    v = do_import(env).version_id
    elsewhere = {**env.registry, "anz": replace(env.registry["anz"], key="anz_other")}
    assert (
        extract_version_tables(env.conn, v, env.artifacts, elsewhere, NOW, isolate=False).status
        == "refused"
    )
    other = do_import(
        env,
        workbook("Data as at 6 November 2026"),
        url="https://www.anz.co.nz/content/dam/anzconz/documents/other.xlsx",
    ).version_id
    result = extract(env, other, dry_run=True)
    assert (result.status, result.reason) == ("refused", "not the ANZ forecasts workbook")


def _store(env, body=None, published_on=date(2026, 11, 5)) -> int:
    v = do_import(env, body, published_on=published_on).version_id
    assert extract(env, v, confirm=extract(env, v, dry_run=True).candidate_hash8).status == "stored"
    return v


def _auto(env) -> None:
    (env.settings.data_dir / "internal-drafts.json").write_text(json.dumps({"auto_display": {
        "enabled": True, "enabled_by": "Test Owner", "enabled_on": "2026-11-21", "note": "synthetic"}}))  # fmt: skip


def _client(env, *routers) -> TestClient:
    return TestClient(create_app(env.settings, routers=list(routers)))


def _internal(env) -> TestClient:
    return _client(env, internal_drafts_router(enabled=True, registry=lambda: env.registry))


def test_stored_figures_reach_the_internal_view_only_under_auto_display(env):
    _store(env)
    body = _internal(env).get("/api/internal/bank-intelligence/forecasts", headers=LOCAL).json()
    assert body["forecasts"] == []  # the owner's automatic mode is off
    _auto(env)
    body = _internal(env).get("/api/internal/bank-intelligence/forecasts", headers=LOCAL).json()
    got = {(f["forecast"]["indicator"], f["forecast"]["horizon"]): f for f in body["forecasts"]}
    assert len(got) == 12 and {f["extraction_method"] for f in got.values()} == {"table"}
    assert {f["forecast"]["institution"]["key"] for f in got.values()} == {"anz"}
    assert got[("gdp", "June 2026 quarter")]["forecast"]["value"] == 0.1


def test_a_gdp_figure_whose_label_states_no_price_basis_is_held_back(env):
    plain = [("GDP", [("% q/q", series(GDP_QQ)), ("Annual % change", series(GDP_AA))])]
    _store(env, workbook(growth=plain))
    _auto(env)
    body = _internal(env).get("/api/internal/bank-intelligence/forecasts", headers=LOCAL).json()
    assert {f["forecast"]["indicator"] for f in body["forecasts"]} == {
        "cpi_inflation",
        "unemployment",
    }
    held = [e for e in body["excluded"] if e["code"] == "table_unresolved_reconciliation"]
    assert len(held) == 6 and {e["institution_key"] for e in held} == {"anz"}


def test_one_bank_never_produces_a_consensus(env):
    _store(env)
    _auto(env)
    body = _internal(env).get("/api/internal/bank-intelligence/consensus", headers=LOCAL).json()
    groups = body["consensus"]["groups"]
    assert groups and all(
        (g["title"], g["status"], g["median"], g["n"])
        == ("Insufficient banks", "insufficient", None, 1)
        for g in groups
    )


def test_history_views_leave_workbook_figures_out_until_two_releases_are_verified(env):
    _store(env)
    _auto(env)
    client = _internal(env)
    revisions = client.get("/api/internal/bank-intelligence/revisions", headers=LOCAL).json()
    assert revisions["histories"] == []
    assert {e["code"] for e in revisions["excluded"]} == {"history_unverified"}
    evaluation = client.get(
        "/api/internal/bank-intelligence/evaluation?indicator=gdp", headers=LOCAL
    ).json()
    assert '"anz"' not in json.dumps(evaluation)


def test_a_second_vintage_is_a_new_version_and_leaves_the_first_extraction_intact(env):
    first = _store(env)
    before = [(f.horizon, f.value) for f in load_forecasts(env.conn, first)]
    revised = [
        (
            "Real GDP",
            [
                ("% q/q", series([*GDP_QQ[:5], 0.3, 0.9, 1.0], first_bold=6)),
                ("Annual % change", series([1.0] * 8)),
            ],
        )
    ]
    second = _store(
        env, workbook("Data as at 5 February 2027", growth=revised), published_on=date(2027, 2, 5)
    )
    assert second != first
    assert [(f.horizon, f.value) for f in load_forecasts(env.conn, first)] == before
    versions = env.conn.execute(
        "SELECT id, superseded_at IS NOT NULL FROM research_document_version ORDER BY id"
    )
    assert [tuple(r) for r in versions] == [(first, 1), (second, 0)]
    _auto(env)
    body = _internal(env).get("/api/internal/bank-intelligence/forecasts", headers=LOCAL).json()
    gdp = sorted(
        (f["forecast"]["horizon"], f["forecast"]["value"])
        for f in body["forecasts"]
        if f["forecast"]["indicator"] == "gdp" and "quarter" in f["forecast"]["horizon"]
    )
    assert gdp == [("December 2026 quarter", 1.0), ("September 2026 quarter", 0.9)]


def test_purge_removes_the_workbook_figures(env):
    v = _store(env)
    plan = purge.plan_purge(env.conn, "anz", version_ids=[v])
    purge.apply_purge(
        env.conn,
        plan,
        env.artifacts,
        reason="permission_withdrawn",
        purged_by="Owner",
        note="t",
        now=NOW,
    )
    assert load_forecasts(env.conn, v) == [] and load_rejections(env.conn, v) == []
    assert extract(env, v, dry_run=True).status == "refused"


def test_public_and_private_routes_carry_no_workbook_figure(env):
    _store(env)
    _auto(env)
    client = _client(
        env,
        research_router(enabled=True, registry=lambda: env.registry),
        private_research_router(enabled=True, registry=lambda: env.registry),
    )
    for route, headers in (("/api/research/feed", {}), ("/api/private/research/items", LOCAL)):
        body = client.get(route, headers=headers).text
        assert "Latest-forecasts" not in body and "xlsx" not in body and "0.7" not in body, route


# ---------------------------------------------------------------- command line


@pytest.fixture()
def cli(env, monkeypatch, tmp_path):
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(env.settings.data_dir))
    path = tmp_path / "Fictional-forecasts.xlsx"
    path.write_bytes(workbook())
    return path


def _imported(cli) -> int:
    args = ["research", "import", "anz", str(cli), "--url", WORKBOOK_URL, "--importer", "Owner", "--note", "n",
            "--title", "ANZ Forecasts", "--published-on", "2026-11-05"]  # fmt: skip
    assert main(args) == 0
    return 1


def _not_a_terminal(monkeypatch):
    monkeypatch.setattr("sys.stdin", SimpleNamespace(isatty=lambda: False))


def test_the_dry_run_command_prints_counts_codes_and_the_hash_but_no_value(cli, capsys):
    v = _imported(cli)
    assert main(["research", "tables", "extract", str(v), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "dry_run, 12 figures, 0 rejections" in out and "confirmation code " in out
    assert "0.7" not in out and "GDP" not in out and "Growth" not in out and "xlsx-anz-1" in out


def test_listing_candidates_refuses_outside_a_real_terminal(cli, capsys, monkeypatch):
    v = _imported(cli)
    _not_a_terminal(monkeypatch)
    assert main(["research", "tables", "extract", str(v), "--dry-run", "--list"]) == 2
    out = capsys.readouterr().out
    assert "real terminal" in out and "0.7" not in out


def test_listing_candidates_in_a_terminal_shows_each_cell_for_reconciliation(
    cli, capsys, monkeypatch
):
    v = _imported(cli)
    tty = SimpleNamespace(isatty=lambda: True)
    monkeypatch.setattr("sys.stdin", tty)
    monkeypatch.setattr("nzstats.research.cli._stdout_is_terminal", lambda: True)
    assert main(["research", "tables", "extract", str(v), "--dry-run", "--list"]) == 0
    out = capsys.readouterr().out
    assert "sheet 2 B8" in out and "0.1" in out and "confirmation code " in out


def test_storing_from_the_command_line_needs_the_code(cli, capsys):
    v = _imported(cli)
    assert main(["research", "tables", "extract", str(v)]) == 1
    assert "reconciliation" in capsys.readouterr().out
    main(["research", "tables", "extract", str(v), "--dry-run"])
    code = capsys.readouterr().out.split("confirmation code ")[1].split()[0]
    assert main(["research", "tables", "extract", str(v), "--confirm", code]) == 0
    assert "stored, 12 figures" in capsys.readouterr().out


def test_show_refuses_to_print_workbook_values_outside_a_real_terminal(cli, capsys, monkeypatch):
    v = _imported(cli)
    main(["research", "tables", "extract", str(v), "--dry-run"])
    code = capsys.readouterr().out.split("confirmation code ")[1].split()[0]
    main(["research", "tables", "extract", str(v), "--confirm", code])
    capsys.readouterr()
    _not_a_terminal(monkeypatch)
    assert main(["research", "tables", "show", str(v)]) == 2
    assert main(["research", "tables", "show", str(v), "--json"]) == 2
    out = capsys.readouterr().out
    assert "real terminal" in out and "0.1" not in out


def test_an_undated_import_takes_the_owners_date_on_reimport_without_a_new_version(env):
    """The workbook carries no publication date the importer reads; the owner states it, now or on a re-import."""
    first = do_import(env, published_on=None)
    dated = do_import(env, published_on=date(2026, 11, 5))
    assert dated.outcome == "unchanged" and dated.version_id == first.version_id
    row = env.conn.execute("SELECT published_on FROM research_publication").fetchone()
    assert row[0] == "2026-11-05"
