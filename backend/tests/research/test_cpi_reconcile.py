"""Phase 3F: reconcile stored CPI vintages and outcomes against the official files (real Stats NZ fixtures)."""

from __future__ import annotations

from nzstats.research.cpi_reconcile import expected_value, parse_official, reconcile
from tests.cpi_support import ingest_cpi

from .test_outcomes_oracle import FIXTURES, RELEASES


def test_every_stored_vintage_and_outcome_reconciles_with_the_official_files(rt, site):
    ingest_cpi(rt, site, *RELEASES)
    result = reconcile(rt.conn, rt.settings.raw_dir)
    assert result.discrepancies == [], result.discrepancies
    assert result.official_files >= len(RELEASES) * 2
    assert len(result.vintages) == len(RELEASES) * 2 and all(v.file_sha256 for v in result.vintages)
    assert result.outcomes and all(o.ok for o in result.outcomes)
    genuine = {(o.measure, o.quarter) for o in result.outcomes if o.genuine_first_release}
    assert {q for _, q in genuine} == set(RELEASES)  # only the four quarters with their own release


def test_with_only_the_newest_release_no_earlier_quarter_is_a_genuine_first(rt, site):
    ingest_cpi(rt, site, "2026-09")
    result = reconcile(rt.conn, rt.settings.raw_dir)
    assert result.ok and {o.quarter for o in result.outcomes if o.genuine_first_release} == {
        "2026-09"
    }


def test_a_backfill_in_any_order_reconciles_the_same(rt, site):
    ingest_cpi(rt, site, "2026-09", "2025-12", "2026-03", "2026-06")
    assert reconcile(rt.conn, rt.settings.raw_dir).ok


def test_a_stored_value_that_differs_from_the_official_file_is_reported(rt, site):
    ingest_cpi(rt, site, "2026-06", "2026-09")
    rt.conn.execute(
        "UPDATE observation SET value = value + 0.1 WHERE period = '2026-03' AND vintage_id IN"
        " (SELECT v.id FROM vintage v JOIN series s ON s.id = v.series_id WHERE s.key = 'cpi.index.nsa.all_groups')"
    )
    result = reconcile(rt.conn, rt.settings.raw_dir)
    assert not result.ok and any(
        "no kept official file reproduces it" in d for d in result.discrepancies
    )


def test_a_missing_official_file_is_reported_not_silently_skipped(rt, site):
    ingest_cpi(rt, site, "2026-09")
    for p in rt.settings.raw_dir.rglob("*/*"):
        if p.is_file():
            p.unlink()
    result = reconcile(rt.conn, rt.settings.raw_dir)
    assert not result.ok and result.official_files == 0 and len(result.discrepancies) >= 2


def test_a_file_that_is_not_a_stats_nz_series_file_is_ignored():
    assert parse_official(b"<html>not csv</html>") is None
    assert parse_official(b"Series_reference,Period\nX,2026.09\n") is None
    assert parse_official((FIXTURES / "cpi_2026-09_index_numbers.csv").read_bytes()) is not None


def test_expected_values_follow_the_official_definitions_and_run_short_safely():
    from decimal import Decimal

    index = {f"{2024 + (i // 4)}-{(i % 4 + 1) * 3:02d}": Decimal(1000 + 10 * i) for i in range(12)}
    assert expected_value("quarterly_change_nsa", index, "2026-09") == round(
        (1110 / 1100 - 1) * 100, 1
    )
    assert expected_value("annual_change", index, "2024-12") is None


def test_cli_cpi_reconcile_reports_success_and_failure_by_exit_status(
    rt, site, capsys, monkeypatch
):
    from nzstats.cli import main

    ingest_cpi(rt, site, "2026-06", "2026-09")
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(rt.settings.data_dir))
    assert main(["research", "cpi-reconcile"]) == 0
    out = capsys.readouterr().out
    assert (
        "reconciled: no discrepancies" in out
        and "genuine first release only for: 2026-06, 2026-09" in out
    )
    for p in rt.settings.raw_dir.rglob("*/*"):
        p.unlink()
    assert main(["research", "cpi-reconcile"]) == 1
    assert "DISCREPANCY" in capsys.readouterr().out


def test_nothing_to_check_is_not_a_pass(rt):
    result = reconcile(rt.conn, rt.settings.raw_dir)
    assert not result.ok and any("no CPI vintages" in d for d in result.discrepancies)
