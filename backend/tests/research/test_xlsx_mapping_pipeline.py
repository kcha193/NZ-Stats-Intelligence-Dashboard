"""The owner's canonical mapping end to end (Phase 4AR): dry run, the storage gate, the internal view and the CLI.

Fictional workbooks only (see `test_xlsx_mapping`). The ANZ registry entry is used because the workbook path is
ANZ-only; every title, note and figure is invented.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace
from types import SimpleNamespace

import pytest

from nzstats.cli import main
from nzstats.research.bank_analytics import HISTORY_UNVERIFIED
from nzstats.research.registry import ContentPolicy
from nzstats.research.table_ingest import (
    candidate_hash8,
    extract_version_tables,
    map_version_workbook,
)
from nzstats.research.table_store import load_forecasts
from nzstats.research.table_view import CURRENT_INTERPRETERS
from nzstats.research.xlsx_anz import MAPPED_INTERPRETER_VERSION, mapping_from_positions
from nzstats.research.xlsx_cells import read_cells
from nzstats.research.xlsx_mapping import parse_mapping

from .conftest import NOW
from .test_table_ingest import artifacts  # noqa: F401  (fixture)
from .test_table_ingest import imported as pdf_imported
from .test_xlsx_anz import AS_AT
from .test_xlsx_mapping import GROWTH, UNIT_CELL, UNIT_NOTE, sheets
from .test_xlsx_pipeline import (  # noqa: F401  (fixtures)
    LOCAL,
    WORKBOOK_URL,
    _auto,
    _internal,
    do_import,
    env,
    no_network,
    stored_count,
)
from .xlsx_support import build

ANZ_LEGEND = "Figures in bold are ANZ forecasts"  # invented wording
SERIES = [("gdp", 2, 1, "B", "quarterly"), ("cpi_inflation", 3, 1, "B", "annual"), ("unemployment", 3, 3, "D", "quarterly")]  # fmt: skip


def mapped_workbook(as_at: str = AS_AT) -> bytes:
    s = sheets(growth_notes=(ANZ_LEGEND, as_at), prices_notes=(ANZ_LEGEND, as_at, UNIT_NOTE))
    return build(s, drawing_paragraphs=(("Fictional cover text",),))


def manifest_for(body: bytes, *, decided_on: str = "2026-11-22", series=SERIES) -> bytes:
    return mapping_from_positions(
        read_cells(body, isolate=False), workbook_sha256=hashlib.sha256(body).hexdigest(), decided_on=decided_on,
        series=series, unit_evidence=(3, UNIT_CELL), sheet_context=[(2, "editorial")], published=None,
    )  # fmt: skip


def extract(env, version, **kw):  # noqa: F811
    return extract_version_tables(
        env.conn, version, env.artifacts, env.registry, NOW, isolate=False, **kw
    )


def imported(env):  # noqa: F811
    body = mapped_workbook()
    return do_import(env, body).version_id, body


def test_a_mapped_dry_run_counts_codes_and_a_code_over_the_mapping(env):  # noqa: F811
    v, body = imported(env)
    raw = manifest_for(body)
    sha = parse_mapping(raw).sha256
    result = extract(env, v, dry_run=True, mapping=raw)
    assert (result.status, result.forecasts, result.mapping_sha256) == ("dry_run", 9, sha)
    assert dict(result.rejection_codes) == {"not_canonical_series": 3}
    assert result.candidate_hash8 == candidate_hash8(result.candidates, mapping_sha256=sha)
    assert result.candidate_hash8 != extract(env, v, dry_run=True).candidate_hash8
    assert stored_count(env) == 0


def test_mapped_figures_are_stored_only_with_their_own_code(env):  # noqa: F811
    v, body = imported(env)
    raw = manifest_for(body)
    unmapped_code = extract(env, v, dry_run=True).candidate_hash8
    assert extract(env, v, mapping=raw).status == "refused"
    assert extract(env, v, mapping=raw, confirm=unmapped_code).status == "refused"
    code = extract(env, v, dry_run=True, mapping=raw).candidate_hash8
    stored = extract(env, v, mapping=raw, confirm=code)
    assert (stored.status, stored.forecasts) == ("stored", 9)
    assert extract(env, v, mapping=raw, confirm=code).status == "unchanged"
    interpreter = env.conn.execute(
        "SELECT interpreter_version FROM research_table_extraction"
    ).fetchone()[0]
    assert interpreter == MAPPED_INTERPRETER_VERSION
    figures = load_forecasts(env.conn, v)
    assert {f.evidence["mapping_sha256"] for f in figures} == {parse_mapping(raw).sha256}


def test_a_changed_mapping_needs_a_new_reconciliation_and_is_a_new_extraction(env):  # noqa: F811
    v, body = imported(env)
    first, second = manifest_for(body), manifest_for(body, decided_on="2026-11-23")
    code = extract(env, v, dry_run=True, mapping=first).candidate_hash8
    assert extract(env, v, mapping=first, confirm=code).status == "stored"
    assert extract(env, v, mapping=second, confirm=code).status == "refused"
    new_code = extract(env, v, dry_run=True, mapping=second).candidate_hash8
    assert new_code != code
    assert extract(env, v, mapping=second, confirm=new_code).status == "stored"
    assert stored_count(env) == 2


def _latest_mapping(env, v):  # noqa: F811
    row = env.conn.execute(
        "SELECT id, interpreter_version FROM research_table_extraction WHERE version_id=? ORDER BY id DESC LIMIT 1",
        (v,),
    ).fetchone()
    figures = load_forecasts(env.conn, v)
    return row[1], {f.evidence.get("mapping_sha256") for f in figures}


def test_reapplying_an_earlier_mapping_is_refused_not_reported_unchanged(env):  # noqa: F811
    v, body = imported(env)
    a, b = manifest_for(body), manifest_for(body, decided_on="2026-11-23")
    for raw in (a, b):
        code = extract(env, v, dry_run=True, mapping=raw).candidate_hash8
        assert extract(env, v, mapping=raw, confirm=code).status == "stored"
    again = extract(
        env, v, mapping=a, confirm=extract(env, v, dry_run=True, mapping=a).candidate_hash8
    )
    assert (again.status, again.reason) == (
        "refused",
        "an older identical extraction exists; restore a backup to return to it",
    )
    assert _latest_mapping(env, v) == ("xlsx-anz-4", {parse_mapping(b).sha256})
    assert stored_count(env) == 2


def test_going_back_to_no_mapping_is_refused_not_reported_unchanged(env):  # noqa: F811
    v, body = imported(env)
    plain = extract(env, v, dry_run=True).candidate_hash8
    assert extract(env, v, confirm=plain).status == "stored"
    raw = manifest_for(body)
    assert extract(env, v, mapping=raw, confirm=extract(env, v, dry_run=True, mapping=raw).candidate_hash8).status == "stored"  # fmt: skip
    back = extract(env, v, confirm=plain)
    assert back.status == "refused" and _latest_mapping(env, v)[0] == "xlsx-anz-4"


def test_a_mapping_for_another_workbook_is_refused_and_stores_nothing(env):  # noqa: F811
    v, body = imported(env)
    revised = mapped_workbook("Data as at 6 November 2026")
    revised_v = do_import(env, revised).version_id
    assert revised_v != v
    for version, raw in ((v, manifest_for(revised)), (revised_v, manifest_for(body))):
        result = extract(env, version, dry_run=True, mapping=raw)
        assert (result.status, result.reason) == ("refused", "mapping_hash_mismatch")
    assert stored_count(env) == 0


@pytest.mark.parametrize("raw", [b"{}", b"not json", json.dumps({"schema": "x"}).encode()])
def test_an_invalid_mapping_is_refused_whole(env, raw):  # noqa: F811
    v, _ = imported(env)
    result = extract(env, v, dry_run=True, mapping=raw)
    assert (result.status, result.reason) == ("refused", "mapping_invalid")


def test_a_revoked_source_refuses_the_mapped_extraction(env):  # noqa: F811
    v, body = imported(env)
    raw = manifest_for(body)
    code = extract(env, v, dry_run=True, mapping=raw).candidate_hash8
    revoked = {
        **env.registry,
        "anz": replace(env.registry["anz"], content_policy=ContentPolicy.METADATA_ONLY),
    }
    for kw in ({"dry_run": True}, {"confirm": code}):
        result = extract_version_tables(
            env.conn, v, env.artifacts, revoked, NOW, isolate=False, mapping=raw, **kw
        )
        assert result.status == "refused"
    assert stored_count(env) == 0


def test_a_revoked_source_refuses_the_owner_map_command(env):  # noqa: F811
    v, _ = imported(env)
    revoked = {
        **env.registry,
        "anz": replace(env.registry["anz"], content_policy=ContentPolicy.METADATA_ONLY),
    }
    reason, raw = map_version_workbook(
        env.conn, v, env.artifacts, revoked, decided_on="2026-11-22", series=SERIES, unit_evidence=None,
        sheet_context=[], published=None, isolate=False,
    )  # fmt: skip
    assert reason is not None and raw == b""


def test_a_mapping_is_refused_for_a_pdf_version(conn, artifacts):  # noqa: F811
    registry, v = pdf_imported(conn, artifacts)
    result = extract_version_tables(
        conn, v, artifacts, registry, NOW, isolate=False, dry_run=True, mapping=b"{}"
    )
    assert (result.status, result.reason) == (
        "refused",
        "a mapping applies only to the ANZ forecasts workbook",
    )


def test_mapped_figures_reach_the_internal_view_with_the_reviewed_sheet(env):  # noqa: F811
    v, body = imported(env)
    raw = manifest_for(body)
    assert extract(env, v, mapping=raw, confirm=extract(env, v, dry_run=True, mapping=raw).candidate_hash8).status == "stored"  # fmt: skip
    _auto(env)
    out = _internal(env).get("/api/internal/bank-intelligence/forecasts", headers=LOCAL).json()
    got = {(f["forecast"]["indicator"], f["forecast"]["horizon"]): f for f in out["forecasts"]}
    assert len(got) == 9 and {k[0] for k in got} == {"gdp", "cpi_inflation", "unemployment"}
    assert got[("gdp", "June 2026 quarter")]["forecast"]["value"] == 0.1
    assert [e for e in out["excluded"] if e["institution_key"] == "anz"] == []


def test_the_mapped_interpreter_is_current_and_its_history_is_unverified():
    assert MAPPED_INTERPRETER_VERSION in CURRENT_INTERPRETERS
    assert MAPPED_INTERPRETER_VERSION in HISTORY_UNVERIFIED


# --- CLI ----------------------------------------------------------------------------------------------------------


def _cli_import(env, tmp_path, monkeypatch) -> int:  # noqa: F811
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(env.settings.data_dir))
    path = tmp_path / "Fictional-forecasts.xlsx"
    path.write_bytes(mapped_workbook())
    args = ["research", "import", "anz", str(path), "--url", WORKBOOK_URL, "--importer", "Owner", "--note", "n",
            "--title", "ANZ Forecasts", "--published-on", "2026-11-05"]  # fmt: skip
    assert main(args) == 0
    return 1


MAP_ARGS = ["--series", "gdp:2:1:B:quarterly", "--series", "cpi_inflation:3:1:B:annual",
            "--series", "unemployment:3:3:D:quarterly", "--unit-evidence", f"3:{UNIT_CELL}",
            "--sheet-context", "2:editorial", "--published-on", "2026-11-05@3:A14",
            "--decided-on", "2026-11-22"]  # fmt: skip
WORKBOOK_TEXT = (
    GROWTH,
    "Real GDP",
    "CPI inflation",
    "Unemployment rate",
    UNIT_NOTE,
    AS_AT,
    ANZ_LEGEND,
)


def test_tables_map_writes_the_manifest_and_prints_only_its_hash_and_counts(
    env,  # noqa: F811
    tmp_path,
    monkeypatch,
    capsys,
):
    v = _cli_import(env, tmp_path, monkeypatch)
    out_file = env.settings.data_dir / "research" / "mapping.json"
    capsys.readouterr()
    assert main(["research", "tables", "map", str(v), *MAP_ARGS, "--out", str(out_file)]) == 0
    out = capsys.readouterr().out
    sha = hashlib.sha256(out_file.read_bytes()).hexdigest()
    assert sha in out and "3 series" in out and "1 sheet review" in out
    assert not any(text in out for text in WORKBOOK_TEXT)
    doc = json.loads(out_file.read_bytes())
    assert doc["published_on"]["text"] == AS_AT and doc["series"][0]["block_title"] == "Real GDP"
    # Never overwritten: the reviewed file is immutable provenance.
    before = out_file.read_bytes()
    assert main(["research", "tables", "map", str(v), *MAP_ARGS, "--decided-on", "2026-11-23", "--out", str(out_file)]) == 1  # fmt: skip
    assert out_file.read_bytes() == before


def test_tables_map_refuses_a_file_outside_the_data_directory(env, tmp_path, monkeypatch, capsys):  # noqa: F811
    v = _cli_import(env, tmp_path, monkeypatch)
    outside = tmp_path / "tracked" / "mapping.json"
    capsys.readouterr()
    assert main(["research", "tables", "map", str(v), *MAP_ARGS, "--out", str(outside)]) == 2
    assert "data directory" in capsys.readouterr().out and not outside.exists()
    sneaky = env.settings.data_dir / ".." / "mapping.json"
    assert main(["research", "tables", "map", str(v), *MAP_ARGS, "--out", str(sneaky)]) == 2
    assert not sneaky.exists()


@pytest.mark.parametrize(
    "bad",
    [
        ["--series", "gdp:2:1:B"],  # no basis
        ["--series", "gdp:x:1:B:quarterly"],
        ["--series", "gdp:2:1:B:quarterly", "--unit-evidence", "3"],
        ["--series", "gdp:2:1:B:quarterly", "--sheet-context", "2"],
        ["--series", "gdp:2:1:B:quarterly", "--published-on", "2026-11-05"],
    ],
)
def test_tables_map_refuses_malformed_positions(env, tmp_path, monkeypatch, capsys, bad):  # noqa: F811
    v = _cli_import(env, tmp_path, monkeypatch)
    out_file = env.settings.data_dir / "research" / "mapping.json"
    assert main(["research", "tables", "map", str(v), *bad, "--decided-on", "2026-11-22", "--out", str(out_file)]) == 2  # fmt: skip
    assert not out_file.exists()


def test_tables_map_refuses_a_position_not_in_the_workbook(env, tmp_path, monkeypatch, capsys):  # noqa: F811
    v = _cli_import(env, tmp_path, monkeypatch)
    out_file = env.settings.data_dir / "research" / "mapping.json"
    capsys.readouterr()
    args = [
        "research",
        "tables",
        "map",
        str(v),
        "--series",
        "gdp:2:2:B:quarterly",
        "--decided-on",
        "2026-11-22",
    ]
    assert main([*args, "--out", str(out_file)]) == 1
    assert "mapping_position_invalid" in capsys.readouterr().out and not out_file.exists()


def test_tables_extract_with_a_mapping_reports_the_mapped_interpreter(
    env,  # noqa: F811
    tmp_path,
    monkeypatch,
    capsys,
):
    v = _cli_import(env, tmp_path, monkeypatch)
    out_file = env.settings.data_dir / "research" / "mapping.json"
    assert main(["research", "tables", "map", str(v), *MAP_ARGS, "--out", str(out_file)]) == 0
    capsys.readouterr()
    assert (
        main(["research", "tables", "extract", str(v), "--dry-run", "--mapping", str(out_file)])
        == 0
    )
    out = capsys.readouterr().out
    assert "dry_run, 9 figures, 3 rejections" in out and "interpreter xlsx-anz-4" in out
    assert f"mapping {hashlib.sha256(out_file.read_bytes()).hexdigest()[:12]}" in out
    assert not any(text in out for text in WORKBOOK_TEXT)
    code = re.search(r"confirmation code ([0-9a-f]{8})", out)[1]
    assert (
        main(
            ["research", "tables", "extract", str(v), "--confirm", code, "--mapping", str(out_file)]
        )
        == 0
    )
    assert "stored, 9 figures" in capsys.readouterr().out
    monkeypatch.setattr("sys.stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr("nzstats.research.cli._stdout_is_terminal", lambda: True)
    assert main(["research", "tables", "show", str(v)]) == 0
    assert "NOT CURRENT" not in capsys.readouterr().out


def test_tables_extract_refuses_a_missing_mapping_file(env, tmp_path, monkeypatch, capsys):  # noqa: F811
    v = _cli_import(env, tmp_path, monkeypatch)
    capsys.readouterr()
    assert main(["research", "tables", "extract", str(v), "--dry-run", "--mapping", str(tmp_path / "none.json")]) == 2  # fmt: skip
    assert "mapping" in capsys.readouterr().out
