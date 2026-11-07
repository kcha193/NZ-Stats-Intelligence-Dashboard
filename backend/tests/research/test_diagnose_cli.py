"""Phase 4V: `nzstats research diagnose`. Read-only, calls no model, prints codes and counts and no source text (SYNTHETIC FIXTURE)."""

import json
import os
import stat

import pytest

from nzstats.cli import main
from nzstats.store.db import connect, migrate

from .diag_support import SECRET, SECTIONS, store_verify_4_summary


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.delenv("NZSTATS_RESEARCH_SOURCES_FILE", raising=False)
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr("nzstats.research.cli.build_llm_provider", pytest.fail)
    monkeypatch.setattr("nzstats.research.cli.build_fetcher", pytest.fail)
    conn = connect(tmp_path / "data" / "nzstats.db")
    migrate(conn)
    _, sid, _ = store_verify_4_summary(conn)
    conn.close()
    return tmp_path, sid


def test_diagnose_prints_counts_and_codes_but_no_source_text(env, capsys):
    _, sid = env
    assert main(["research", "diagnose", str(sid)]) == 0
    out = capsys.readouterr().out
    assert (
        "verify-4" in out
        and "verify-5" in out
        and "vote_not_in_evidence" in out
        and "cascade" in out
    )
    assert "newly accepted" in out and "decisions[0]" in out
    for needle in (SECRET, "Brent crude", "Monetary Policy Committee", SECTIONS[1][:30]):
        assert needle not in out


def test_diagnose_json_has_no_text_and_names_the_baseline_and_proposal(env, capsys):
    _, sid = env
    assert main(["research", "diagnose", str(sid), "--json"]) == 0
    body = json.loads(capsys.readouterr().out)
    assert (body["baseline"]["version"], body["proposed"]["version"]) == ("verify-4", "verify-5")
    assert body["stored_reproduced"] is True and "Brent" not in json.dumps(body)


def test_diagnose_writes_an_owner_only_report_and_never_prints_its_text(env, capsys):
    tmp_path, sid = env
    out = tmp_path / "data" / "diag" / "report.html"
    assert main(["research", "diagnose", str(sid), "--out", str(out), "--include-text"]) == 0
    printed = capsys.readouterr().out
    assert "Brent" not in printed and str(out) in printed
    assert stat.S_IMODE(os.stat(out).st_mode) == 0o600
    assert "Brent crude averaged" in out.read_text()


def test_the_report_without_include_text_holds_no_source_text(env, capsys):
    tmp_path, sid = env
    out = tmp_path / "data" / "diag" / "plain.html"
    assert main(["research", "diagnose", str(sid), "--out", str(out)]) == 0
    assert SECRET not in out.read_text() and "Brent crude" not in out.read_text()


def test_diagnose_changes_nothing_in_the_database(env, capsys):
    tmp_path, sid = env
    db = tmp_path / "data" / "nzstats.db"
    before = db.read_bytes()
    assert main(["research", "diagnose", str(sid)]) == 0
    assert db.read_bytes() == before


def test_diagnose_refuses_an_unknown_summary_and_an_unknown_verifier_without_text(env, capsys):
    _, sid = env
    assert main(["research", "diagnose", str(sid + 50)]) == 2
    assert "no stored summary" in capsys.readouterr().out
    assert main(["research", "diagnose", str(sid), "--proposed", "verify-99"]) == 2
    assert "unknown verifier" in capsys.readouterr().out


def test_diagnose_does_not_create_a_database_that_is_not_there(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("NZSTATS_RESEARCH_SOURCES_FILE", raising=False)
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(tmp_path / "empty"))
    assert main(["research", "diagnose", "1"]) == 2
    assert not (tmp_path / "empty" / "nzstats.db").exists()


def test_diagnose_refuses_a_report_path_that_would_overwrite_the_database_or_leave_the_data_directory(
    env, capsys, tmp_path
):
    tmp, sid = env
    db = tmp / "data" / "nzstats.db"
    before = db.read_bytes()
    assert main(["research", "diagnose", str(sid), "--out", str(db)]) == 2
    assert "refused" in capsys.readouterr().out and db.read_bytes() == before
    outside = tmp / "outside.html"
    assert main(["research", "diagnose", str(sid), "--out", str(outside)]) == 2
    assert not outside.exists()
