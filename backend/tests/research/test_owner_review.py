"""The consolidated owner-review package (Phase 4R). SYNTHETIC FIXTURE: invented text and files; no real report is read."""

import json
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import quote, unquote

import pytest

from nzstats.research import owner_review
from nzstats.research.gold_extension import GoldExtensionError
from nzstats.research.owner_review import GROUPS, build_package, gold_status

from .llm_support import seed_version
from .test_gold_extension import PAGE, extension

SHEET_TEXT = "SYNTHETIC sheet text that must never be shown"


@pytest.fixture(autouse=True)
def _about_the_seeded_version(monkeypatch):
    """Here the package is about the seeded document; the tests that run as shipped patch it back (see `shipped_document`)."""
    monkeypatch.setattr(owner_review, "REVIEW_DOCUMENT_VERSION", 1)


@pytest.fixture()
def stored(conn):
    return conn, seed_version(conn, (PAGE,), published_on="2026-11-02")


def _build(stored, tmp_path, make_sheets=True):
    conn, version = stored
    data = tmp_path / "data"
    if make_sheets:
        for rel, _ in (*owner_review.EXISTING_SHEETS.values(), *owner_review.AI_WRITTEN.values()):
            target = data / rel
            target.parent.mkdir(parents=True, exist_ok=True)
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
    _with_gold(stored, tmp_path)
    _, report, page = _build(stored, tmp_path)
    assert SHEET_TEXT not in page
    assert report["sheets_found"] == report["sheets_expected"] == 5
    assert "<code>" in page and "bytes" in page


def test_a_missing_sheet_is_reported_not_invented(stored, tmp_path):
    _with_gold(stored, tmp_path)
    _, report, page = _build(stored, tmp_path, make_sheets=False)
    assert report["sheets_found"] == 1 and report["sheets_expected"] == 5
    assert page.count("not found at") == 4


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
    _with_gold(stored, tmp_path)
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


def test_model_output_is_linked_only_after_the_gold_sheet_and_gold_comes_first(stored, tmp_path):
    _with_gold(stored, tmp_path)
    _, _, page = _build(stored, tmp_path)
    after = page.index("Open only after your own marks are finished")
    assert page.index("human-review.html") > after
    assert "href='file://" not in page[after:] or "human-review.html</a>" in page[after:]
    assert page.index("A. Treasury version 3 gold") < page.index("B. Phase 4O Treasury output")


def test_the_package_must_stay_under_the_data_directory(stored, tmp_path):
    conn, version = stored
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    elsewhere.chmod(0o755)
    with pytest.raises(GoldExtensionError):
        build_package(conn, tmp_path / "data", elsewhere, version)
    assert elsewhere.stat().st_mode & 0o777 == 0o755 and not list(elsewhere.iterdir())


def test_an_existing_directory_is_not_re_moded_and_a_symlinked_file_is_refused(stored, tmp_path):
    conn, version = stored
    data = tmp_path / "data"
    out = data / "mine"
    out.mkdir(parents=True)
    out.chmod(0o755)
    (out / "index.html").symlink_to(tmp_path / "target.html")
    with pytest.raises(GoldExtensionError):
        build_package(conn, data, out, version)
    (out / "index.html").unlink()
    build_package(conn, data, out, version)
    assert out.stat().st_mode & 0o777 == 0o755
    assert not (tmp_path / "target.html").exists()


# Review of PR 46 (Codex, P2): the Phase 4O packet needs a usable link once, and only once, the owner's own gold is saved.
PACKET = "phase-4n/run-treasury-20261102/human-review.html"
PERIODS = "phase-4q/period-review-worksheet.html"


def _with_gold(stored, tmp_path, valid=True):
    conn, version = stored
    saved = tmp_path / "data" / "annotations" / f"gold-extension-v{version}.json"
    saved.parent.mkdir(parents=True, exist_ok=True)
    body = extension(version=version)
    if not valid:
        body = {**body, "text_sha256": "0" * 64}
    saved.write_text(json.dumps(body))


def _after_gold(page):
    return page[page.index("Open only after your own marks are finished") :]


def _links(page):
    return re.findall(r"<a href='([^']*)'", page)


def test_the_constants_that_decide_the_link_are_safe_relative_paths():
    allowed = {
        rel
        for rel, _ in (*owner_review.EXISTING_SHEETS.values(), *owner_review.AI_WRITTEN.values())
    }
    assert owner_review.LINKED_AFTER_GOLD == {PACKET, PERIODS}
    for rel in owner_review.LINKED_AFTER_GOLD:
        assert rel in allowed and not rel.startswith("/") and ".." not in Path(rel).parts


def test_the_packet_is_linked_after_the_owners_gold_is_saved_and_valid(stored, tmp_path):
    _with_gold(stored, tmp_path)
    data, report, page = _build(stored, tmp_path)
    after = _after_gold(page)
    href = f"file://{quote(str((data / PACKET).resolve()))}"
    assert f"<a href='{href}'>human-review.html</a>" in after
    assert report["gold_status"].startswith("saved and valid")
    assert SHEET_TEXT not in page and "human-review.html" not in page[: page.index(after)]


def test_the_packet_is_not_linked_before_the_owners_gold_is_saved(stored, tmp_path):
    _, _, page = _build(stored, tmp_path)
    assert (
        "human-review" not in page and "phase-4n" not in page
    )  # not even listed: see test_owner_review_blind.py


@pytest.mark.parametrize("state", ["invalid", "unbound", "unreadable"])
def test_a_gold_file_that_is_not_valid_and_bound_unlocks_nothing(stored, tmp_path, state):
    conn, version = stored
    if state == "unbound":
        _with_gold(stored, tmp_path, valid=False)
    else:
        saved = tmp_path / "data" / "annotations" / f"gold-extension-v{version}.json"
        saved.parent.mkdir(parents=True)
        saved.write_text("{not json" if state == "invalid" else "")
    _, _, page = _build(stored, tmp_path)
    assert not any("phase-4n" in link for link in _links(page))


def test_a_gold_file_for_another_version_unlocks_nothing(stored, tmp_path):
    conn, version = stored
    other = tmp_path / "data" / "annotations" / f"gold-extension-v{version + 1}.json"
    other.parent.mkdir(parents=True)
    other.write_text(json.dumps(extension(version=version + 1)))
    _, _, page = _build(stored, tmp_path)
    assert not any("phase-4n" in link for link in _links(page))


def test_only_the_packet_and_period_worksheet_are_linked_and_the_ai_pack_and_comparison_never_are(
    stored, tmp_path
):
    _with_gold(stored, tmp_path)
    data, _, page = _build(stored, tmp_path)
    after = _after_gold(page)
    assert sorted(Path(unquote(link)).name for link in _links(after)) == [
        "human-review.html",
        "period-review-worksheet.html",
    ]
    for rel in ("annotations/phase-4q-feu-2026-10-29.json", "phase-4q/feu-comparison.md"):
        name = Path(rel).name
        assert name in after and f">{name}</a>" not in after


def test_a_missing_packet_is_reported_even_after_gold_and_gets_no_link(stored, tmp_path):
    _with_gold(stored, tmp_path)
    data, _, page = _build(stored, tmp_path, make_sheets=False)
    after = _after_gold(page)
    assert "not found at" in after and not _links(after)


def test_a_packet_that_is_a_symlink_out_of_the_data_directory_is_not_linked(stored, tmp_path):
    _with_gold(stored, tmp_path)
    data = tmp_path / "data"
    outside = tmp_path / "outside.html"
    outside.write_text(SHEET_TEXT)
    target = data / PACKET
    target.parent.mkdir(parents=True)
    target.symlink_to(outside)
    _, _, page = _build(stored, tmp_path, make_sheets=False)
    assert not _links(_after_gold(page)) and SHEET_TEXT not in page


def test_the_packet_link_is_escaped_for_an_awkward_data_directory(stored, tmp_path):
    conn, version = stored
    data = tmp_path / "d'a<t>a&\"x y"
    saved = data / "annotations" / f"gold-extension-v{version}.json"
    saved.parent.mkdir(parents=True)
    saved.write_text(json.dumps(extension(version=version)))
    target = data / PACKET
    target.parent.mkdir(parents=True)
    target.write_text(SHEET_TEXT)
    build_package(conn, data, data / "phase-4r" / "owner-review", version)
    page = (data / "phase-4r" / "owner-review" / "index.html").read_text()
    (link,) = _links(_after_gold(page))
    assert link.startswith("file:///") and not set(link) & set("'<>\" ")
    assert unquote(link[len("file://") :]) == str(target.resolve())
    assert "d'a<t>a" not in page and SHEET_TEXT not in page


def test_the_page_stays_local_with_the_link_enabled(stored, tmp_path):
    _with_gold(stored, tmp_path)
    _, _, page = _build(stored, tmp_path)
    assert "http://" not in page and "https://" not in page and "<form" not in page
    assert all(link.startswith("file:///") for link in _links(page))
    assert "default-src 'none'" in page and "form-action 'none'" in page
