"""The consolidated owner-review package (Phase 4R). SYNTHETIC FIXTURE: invented text and files; no real report is read."""

import json
import re
import shutil
import subprocess

import pytest

from nzstats.research import owner_review
from nzstats.research.owner_review import GROUPS, build_package, gold_status

from .llm_support import seed_version
from .test_gold_extension import PAGE, extension

SHEET_TEXT = "SYNTHETIC sheet text that must never be shown"


@pytest.fixture()
def stored(conn):
    return conn, seed_version(conn, (PAGE,), published_on="2026-11-02")


def _build(stored, tmp_path, make_sheets=True):
    conn, version = stored
    data = tmp_path / "data"
    if make_sheets:
        for rel, _ in owner_review.EXISTING_SHEETS.values():
            target = data / rel
            target.parent.mkdir(parents=True)
            target.write_text(SHEET_TEXT)
    report = build_package(conn, data, data / "phase-4r" / "owner-review", version)
    return data, report, (data / "phase-4r" / "owner-review" / "index.html").read_text()


def _node(tmp_path, source):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = tmp_path / "run.js"
    script.write_text(source)
    out = subprocess.run(
        [node, str(script)], capture_output=True, text=True, check=True, timeout=30
    )
    return json.loads(out.stdout)


def test_the_package_lists_the_sheets_by_size_and_hash_and_never_shows_their_text(stored, tmp_path):
    _, report, page = _build(stored, tmp_path)
    assert SHEET_TEXT not in page
    assert report["sheets_found"] == report["sheets_expected"] == 2
    assert "<code>" in page and "bytes" in page


def test_a_missing_sheet_is_reported_not_invented(stored, tmp_path):
    _, report, page = _build(stored, tmp_path, make_sheets=False)
    assert report["sheets_found"] == 0 and "not found at" in page


def test_the_package_is_private(stored, tmp_path):
    data, _, _ = _build(stored, tmp_path)
    out = data / "phase-4r" / "owner-review"
    assert out.stat().st_mode & 0o777 == 0o700
    assert (out / "index.html").stat().st_mode & 0o777 == 0o600
    assert (out / f"gold-worksheet-v{stored[1]}.html").stat().st_mode & 0o777 == 0o600


def test_the_page_prefills_no_answer_no_name_and_no_approval(stored, tmp_path):
    _, _, page = _build(stored, tmp_path)
    assert not re.search(r"<input[^>]* checked", page) and "value=''" not in page
    assert "id=reviewer autocomplete=off>" in page and "id=reviewed_on placeholder" in page
    assert "approves no hosted run" in page
    assert "http://" not in page and "https://" not in page
    assert "default-src 'none'" in page


def test_every_open_decision_the_record_names_is_asked_with_a_default_that_keeps_the_rules(
    stored, tmp_path
):
    _, report, page = _build(stored, tmp_path)
    ids = [d.id for _, _, _, decisions in GROUPS for d in decisions]
    assert len(ids) == len(set(ids)) == report["decisions"]
    for must in (
        "ocr-decision-date",
        "imf-label-1",
        "year-fact-2",
        "third-party-in-scope",
        "next-experiment",
        "treasury-page-checked",
    ):
        assert f"data-d='{must}'" in page
    assert "Keep rejecting" in page


def test_the_gold_status_follows_the_saved_file(stored, tmp_path):
    conn, version = stored
    data = tmp_path / "data"
    (data / "annotations").mkdir(parents=True)
    assert gold_status(conn, data, version).startswith("not saved yet")
    path = data / "annotations" / f"gold-extension-v{version}.json"
    path.write_text("{not json")
    assert "not a valid gold extension" in gold_status(conn, data, version)
    path.write_text(json.dumps(extension(version=version)))
    assert gold_status(conn, data, version).startswith("saved and valid: 5 items")
    path.write_text(json.dumps({**extension(version=version), "text_sha256": "0" * 64}))
    assert "not bound to this document version" in gold_status(conn, data, version)
    path.write_text(json.dumps(extension(version=version, reviewed_by="Claude Code")))
    assert "not a valid gold extension" in gold_status(conn, data, version)


def test_the_status_never_repeats_what_the_file_contains(stored, tmp_path):
    conn, version = stored
    data = tmp_path / "data"
    (data / "annotations").mkdir(parents=True)
    ext = extension(version=version)
    ext["items"][0]["terms"] = ["SECRET-TERM-xyz"]
    ext["reviewed_by"] = "Claude"
    (data / "annotations" / f"gold-extension-v{version}.json").write_text(json.dumps(ext))
    assert "SECRET-TERM" not in gold_status(conn, data, version)


def test_the_exported_decisions_carry_the_typed_name_and_only_the_answers_given(tmp_path):
    meta = {"reviewer": "Test Person", "reviewed_on": "2026-11-04", "package_version": 1}
    answers = {
        "ocr-decision-date": {"choice": "Drop the item", "note": ""},
        "gold-done": {"choice": "", "note": ""},
    }
    call = f"collect({json.dumps(meta)}, {json.dumps(answers)})"
    result = _node(tmp_path, owner_review.EXPORT_JS + f"console.log(JSON.stringify({call}));")
    assert result["errors"] == []
    assert result["file"]["reviewer"] == "Test Person"
    assert result["file"]["decisions"] == {
        "ocr-decision-date": {"choice": "Drop the item", "note": None}
    }


def test_the_export_needs_a_typed_name_a_date_and_an_answer(tmp_path):
    call = 'collect({reviewer: "", reviewed_on: "soon"}, {})'
    empty = _node(tmp_path, owner_review.EXPORT_JS + f"console.log(JSON.stringify({call}));")
    assert len(empty["errors"]) == 3


def test_the_command_writes_the_package_and_prints_statuses_only(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(tmp_path / "data"))
    from nzstats.cli import main
    from nzstats.store.db import connect, migrate

    conn = connect(tmp_path / "data" / "nzstats.db")
    migrate(conn)
    version = seed_version(conn, (PAGE,), published_on="2026-11-02")
    conn.close()
    assert main(["research", "owner-review-package", "--version", str(version)]) == 0
    out = capsys.readouterr().out
    assert "decisions:" in out and "gold_status: not saved yet" in out and "IMF expects" not in out
    assert (tmp_path / "data" / "phase-4r" / "owner-review" / "index.html").is_file()
    assert main(["research", "owner-review-package", "--version", "99"]) == 2
    assert "refused" in capsys.readouterr().out
