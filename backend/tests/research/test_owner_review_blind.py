"""PR 46 review (Codex, P2): the owner-review index must be blind until the owner's own gold is saved, valid and bound.

SYNTHETIC FIXTURE: invented text and files; no real report or model output is read. These tests inspect the generated HTML
itself: before valid gold the page must not contain model-derived decision text, file names, descriptions, ids or links, whether
as visible text, hidden markup, script or metadata. They do not merely check that a link is disabled.
"""

import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest

from nzstats.research import owner_review
from nzstats.research.gold_extension import GoldExtensionError
from nzstats.research.owner_review import build_package, gold_status

from .llm_support import seed_version
from .test_gold_extension import PAGE, extension

SENTINEL = "SYNTHETIC-MODEL-OUTPUT-SENTINEL-93f1"
PACKET = "phase-4n/run-treasury-20261102/human-review.html"
PERIODS = "phase-4q/period-review-worksheet.html"
AI_PACK = "annotations/phase-4q-feu-2026-10-29.json"
COMPARISON = "phase-4q/feu-comparison.md"
MODEL_FILES = (PERIODS, PACKET, AI_PACK, COMPARISON)

# Written out by hand so that a change to the module's own constants cannot quietly shrink this list.
PROHIBITED_BEFORE_GOLD = (
    "Phase 4O",
    "human-review",
    "phase-4n",
    "phase-4q",
    "feu-comparison",
    "feu-2026",
    "period-review",
    "AI pack",
    "AI-written",
    "AI reading",
    "AI comparison",
    "MODEL OUTPUT",
    "OCR",
    "IMF",
    "RBNZ",
    "adjudicat",
    "28 October",
    "2.75",
    "rejected",
    "imf-label",
    "year-fact",
    "ocr-decision",
    "fr-period",
    "fr-forecast",
    "fr-second",
    "fr-unit",
    "economists-author",
    "wording-gaps",
    "missing-content",
    "third-party-pages",
    "next-experiment",
    "Nine true claims",
    "Keep rejecting",
)


@pytest.fixture()
def stored(conn):
    return conn, seed_version(conn, (PAGE,), published_on="2026-11-02")


def _make_model_files(data: Path, text: str = SENTINEL) -> None:
    for rel in MODEL_FILES:
        target = data / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)


def _save_gold(stored, data: Path, **over) -> Path:
    conn, version = stored
    saved = data / "annotations" / f"gold-extension-v{version}.json"
    saved.parent.mkdir(parents=True, exist_ok=True)
    saved.write_text(json.dumps(extension(version=version, **over)))
    return saved


def _build(stored, data: Path) -> tuple[dict, str]:
    conn, version = stored
    out = data / "phase-4r" / "owner-review"
    report = build_package(conn, data, out, version)
    return report, (out / "index.html").read_text()


def _stable(page: str) -> str:
    """The page without file times, which differ between two builds a minute apart."""
    return re.sub(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", "<time>", page)


def _gated_markers() -> list[str]:
    gated = owner_review.GROUPS[1:]
    markers = []
    for _, title, intro, decisions in gated:
        markers += [title, intro]
        for d in decisions:
            # "Yes", "No" and "Accept" are also the blind questions' own answers, so only distinctive options are markers.
            markers += [d.id, d.ask, *(o for o in d.options if len(o) > 12)]
    for rel, why in (*owner_review.EXISTING_SHEETS.values(), *owner_review.AI_WRITTEN.values()):
        markers += [rel, Path(rel).name, why]
    return markers


def _assert_blind(page: str) -> None:
    assert SENTINEL not in page
    # Case-sensitive on purpose: "MODEL OUTPUT" is the packet's tag, while the gold attestation legitimately says "without model output".
    for term in PROHIBITED_BEFORE_GOLD:
        assert term not in page, f"pre-gold page contains {term!r}"
    for marker in _gated_markers():
        assert marker not in page, f"pre-gold page contains {marker!r}"
    # Nothing in the page points at a model-output location, in a link, a comment, a script or metadata.
    assert "<!--" not in page
    markup = re.sub(r"<script\b.*?</script>", "<script></script>", page, flags=re.S)
    targets = re.findall(
        r"<[a-z][^>]*?\s(?:href|src|action|data|poster|srcset)\s*=\s*['\"]?([^'\" >]+)", markup
    )
    assert all("gold-worksheet-v" in target for target in targets), targets


def _assert_unlocked(page: str) -> None:
    for d in (d for _, _, _, ds in owner_review.GROUPS[1:] for d in ds):
        assert f"data-d='{d.id}'" in page
    assert "Open only after your own marks are finished" in page


# ---- the blind page ------------------------------------------------------------------------------------------------


def test_with_no_gold_the_page_holds_only_source_derived_gold_review_content(stored, tmp_path):
    data = tmp_path / "data"
    _make_model_files(data)
    report, page = _build(stored, data)
    _assert_blind(page)
    assert "gold-worksheet-v" in page and "Gold file status" in page
    assert "data-d='gold-done'" in page and "data-d='third-party-in-scope'" in page
    assert report["review_sections"] == "withheld until your gold file is saved and valid"


def test_the_blind_page_is_the_same_whatever_model_files_exist(stored, tmp_path):
    """Information flow, not wording: the blind page cannot depend on model output it never reads."""
    pages = []
    for case in ("absent", "present", "symlinks", "directories", "huge"):
        data = tmp_path / case / "data"
        data.mkdir(parents=True)
        if case == "present":
            _make_model_files(data)
        elif case == "symlinks":
            outside = tmp_path / case / "outside.txt"
            outside.write_text(SENTINEL)
            for rel in MODEL_FILES:
                (data / rel).parent.mkdir(parents=True, exist_ok=True)
                (data / rel).symlink_to(outside)
        elif case == "directories":
            for rel in MODEL_FILES:
                (data / rel).mkdir(parents=True)
        elif case == "huge":
            _make_model_files(data, SENTINEL * 50_000)
        pages.append(_stable(_build(stored, data)[1]).replace(str(data), "<data>"))
    assert len(set(pages)) == 1


def test_the_blind_report_does_not_count_model_files(stored, tmp_path):
    data = tmp_path / "data"
    _make_model_files(data)
    report, _ = _build(stored, data)
    assert report["sheets_found"] == report["sheets_expected"] == 1
    assert report["decisions"] == 2 and report["decision_groups"] == 1


def test_the_blind_page_prefills_nothing_and_stays_local(stored, tmp_path):
    data = tmp_path / "data"
    _, page = _build(stored, data)
    assert not re.search(r"<input[^>]* checked", page) and "value=''" not in page
    assert "id=reviewer autocomplete=off>" in page and "id=reviewed_on placeholder" in page
    assert "http://" not in page and "https://" not in page and "<form" not in page
    assert "default-src 'none'" in page and "form-action 'none'" in page
    assert "approves no hosted run" in page


def test_the_blind_page_still_requires_the_reviewers_own_name_date_and_an_answer(stored, tmp_path):
    _, page = _build(stored, tmp_path / "data")
    assert "function collect(" in page and "Type your own name." in page
    assert "Type the date as YYYY-MM-DD." in page and "Answer at least one question." in page


# ---- gold that does not unlock --------------------------------------------------------------------------------------


def _gold_missing(stored, data):
    pass


def _gold_not_json(stored, data):
    _save_gold(stored, data).write_text("{not json")


def _gold_empty_file(stored, data):
    _save_gold(stored, data).write_text("")


def _gold_wrong_hash(stored, data):
    _save_gold(stored, data, text_sha256="0" * 64)


def _gold_wrong_version_inside(stored, data):
    _save_gold(stored, data, version_id=stored[1] + 1)


def _gold_other_versions_file(stored, data):
    conn, version = stored
    other = data / "annotations" / f"gold-extension-v{version + 1}.json"
    other.parent.mkdir(parents=True, exist_ok=True)
    other.write_text(json.dumps(extension(version=version + 1)))


def _gold_ai_reviewer(stored, data):
    _save_gold(stored, data, reviewed_by="Claude Code")


def _gold_no_attestation(stored, data):
    _save_gold(stored, data, written_without_model_output=False)


def _gold_no_items(stored, data):
    _save_gold(stored, data, items=[])


def _gold_future_date(stored, data):
    _save_gold(stored, data, reviewed_on="2099-01-01")


def _gold_extra_field(stored, data):
    _save_gold(stored, data, model_hint="x")


def _gold_symlink_out(stored, data):
    conn, version = stored
    outside = data.parent / "elsewhere" / "gold.json"
    outside.parent.mkdir(parents=True)
    outside.write_text(json.dumps(extension(version=version)))
    link = data / "annotations" / f"gold-extension-v{version}.json"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(outside)


def _gold_dir_symlink_out(stored, data):
    conn, version = stored
    real = data.parent / "elsewhere" / "annotations"
    real.mkdir(parents=True)
    (real / f"gold-extension-v{version}.json").write_text(json.dumps(extension(version=version)))
    shutil.rmtree(
        data / "annotations", ignore_errors=True
    )  # the model-file fixture made a real one
    data.mkdir(parents=True, exist_ok=True)
    (data / "annotations").symlink_to(real, target_is_directory=True)


def _gold_is_a_directory(stored, data):
    (data / "annotations" / f"gold-extension-v{stored[1]}.json").mkdir(parents=True)


NOT_UNLOCKING = [
    _gold_missing,
    _gold_not_json,
    _gold_empty_file,
    _gold_wrong_hash,
    _gold_wrong_version_inside,
    _gold_other_versions_file,
    _gold_ai_reviewer,
    _gold_no_attestation,
    _gold_no_items,
    _gold_future_date,
    _gold_extra_field,
    _gold_symlink_out,
    _gold_dir_symlink_out,
    _gold_is_a_directory,
]


@pytest.mark.parametrize("setup", NOT_UNLOCKING, ids=lambda f: f.__name__.removeprefix("_gold_"))
def test_gold_that_is_missing_invalid_unbound_or_outside_the_data_directory_unlocks_nothing(
    stored, tmp_path, setup
):
    data = tmp_path / "data"
    data.mkdir()
    _make_model_files(data)
    setup(stored, data)
    report, page = _build(stored, data)
    assert not gold_status(stored[0], data, stored[1]).startswith("saved and valid")
    _assert_blind(page)
    assert report["review_sections"].startswith("withheld")


# ---- gold that does unlock ------------------------------------------------------------------------------------------


def test_valid_gold_bound_to_this_version_enables_every_section_and_both_worksheets(
    stored, tmp_path
):
    data = tmp_path / "data"
    _make_model_files(data)
    _save_gold(stored, data)
    report, page = _build(stored, data)
    _assert_unlocked(page)
    assert report["gold_status"].startswith("saved and valid")
    assert report["review_sections"] == "enabled"
    assert report["sheets_found"] == report["sheets_expected"] == 5
    assert SENTINEL not in page  # the files are listed by size and hash and are never displayed
    links = re.findall(r"<a href='([^']*)'", page)
    names = [Path(link).name for link in links]
    assert "period-review-worksheet.html" in names and "human-review.html" in names
    assert not {"phase-4q-feu-2026-10-29.json", "feu-comparison.md"} & set(names)


def test_after_gold_a_missing_model_file_is_reported_and_nothing_is_invented(stored, tmp_path):
    data = tmp_path / "data"
    _save_gold(stored, data)
    report, page = _build(stored, data)
    _assert_unlocked(page)
    assert page.count("not found at") == 4
    assert report["sheets_found"] == 1 and report["sheets_expected"] == 5
    assert [Path(link).name for link in re.findall(r"<a href='([^']*)'", page)] == [
        "gold-worksheet-v1.html"
    ]


@pytest.mark.parametrize("rel", [PERIODS, PACKET])
def test_after_gold_a_linked_file_that_escapes_the_data_directory_gets_no_link(
    stored, tmp_path, rel
):
    data = tmp_path / "data"
    _save_gold(stored, data)
    outside = tmp_path / "outside.html"
    outside.write_text(SENTINEL)
    (data / rel).parent.mkdir(parents=True, exist_ok=True)
    (data / rel).symlink_to(outside)
    _, page = _build(stored, data)
    assert Path(rel).name not in "".join(re.findall(r"<a href='([^']*)'", page))
    assert SENTINEL not in page


@pytest.mark.parametrize("rel", MODEL_FILES)
def test_after_gold_a_file_outside_the_data_directory_is_not_even_hashed_or_sized(
    stored, tmp_path, rel
):
    """A symlink out of the data directory is refused outright: no link, and no size, time or hash of the file it points at."""
    data = tmp_path / "data"
    _save_gold(stored, data)
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"x" * 4321)
    digest = hashlib.sha256(outside.read_bytes()).hexdigest()[:12]
    (data / rel).parent.mkdir(parents=True, exist_ok=True)
    (data / rel).symlink_to(outside)
    _, page = _build(stored, data)
    assert digest not in page and "4,321" not in page
    assert page.count("outside the data directory") == 1


def test_after_gold_the_page_prefills_nothing_and_keeps_the_manual_requirements(stored, tmp_path):
    data = tmp_path / "data"
    _make_model_files(data)
    _save_gold(stored, data)
    _, page = _build(stored, data)
    assert not re.search(r"<input[^>]* checked", page) and "value=''" not in page
    assert "id=reviewer autocomplete=off>" in page and "id=reviewed_on placeholder" in page
    assert "Type your own name." in page and "Type the date as YYYY-MM-DD." in page
    assert "http://" not in page and "https://" not in page and "<form" not in page
    assert "default-src 'none'" in page and "form-action 'none'" in page


def test_the_page_goes_blind_again_when_the_gold_file_is_removed_or_replaced(stored, tmp_path):
    data = tmp_path / "data"
    _make_model_files(data)
    saved = _save_gold(stored, data)
    _assert_unlocked(_build(stored, data)[1])
    saved.write_text("{not json")
    _assert_blind(_build(stored, data)[1])
    saved.unlink()
    _assert_blind(_build(stored, data)[1])


def test_the_decision_groups_are_partitioned_by_a_single_named_gate():
    blind = owner_review.BLIND_GROUPS
    gated = owner_review.GATED_GROUPS
    assert blind + gated == owner_review.GROUPS
    assert [d.id for _, _, _, ds in blind for d in ds] == ["gold-done", "third-party-in-scope"]


def test_a_refused_output_directory_writes_nothing_before_gold_either(stored, tmp_path):
    conn, version = stored
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    with pytest.raises(GoldExtensionError):
        build_package(conn, tmp_path / "data", elsewhere, version)
    assert not list(elsewhere.iterdir())
