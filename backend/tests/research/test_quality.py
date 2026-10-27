"""Phase 3D-A: extraction quality of a stored version (SYNTHETIC FIXTURE text throughout)."""

from __future__ import annotations

from nzstats.research.contract import SectionText
from nzstats.research.quality import assess_extraction, version_quality

from .llm_support import seed_version

PROSE = (
    "SYNTHETIC FIXTURE. Growth in the example economy is expected to recover gradually over the coming year,"
    " supported by lower interest rates and steady population growth. Inflation is projected to return to the"
    " middle of the target band by the end of the forecast period."
)


def pages(*texts: str) -> dict[int, SectionText]:
    return {i: SectionText(t, i + 1, i + 1) for i, t in enumerate(texts)}


def codes(report) -> set[str]:
    return {f.code for f in report.findings}


def test_clean_prose_is_ok():
    report = assess_extraction(pages(PROSE, PROSE + " More text follows here."), page_count=2)
    assert report.grade == "ok" and report.findings == ()
    assert report.metrics["sections"] == 2 and report.metrics["missing_pages"] == 0


def test_missing_and_empty_pages_need_review():
    report = assess_extraction(pages(PROSE, "  ", PROSE), page_count=4)
    assert {"empty_sections", "missing_pages"} <= codes(report)
    assert report.metrics["missing_pages"] == 1  # page 4 has no section at all
    assert report.grade == "review"


def test_replacement_and_private_use_characters_make_extraction_poor():
    garbled = "Gr�wth  is f�recast " * 20
    report = assess_extraction(pages(garbled), page_count=1)
    assert "undecodable_characters" in codes(report) and report.grade == "poor"


def test_glued_and_spaced_out_words_are_flagged():
    glued = PROSE + " " + "inflationisexpectedtofallsharplyoverthecomingyear " * 4
    assert "glued_words" in codes(assess_extraction(pages(glued), page_count=1))
    spaced = PROSE + " " + "G r o w t h i s e x p e c t e d t o r i s e " * 6
    assert "spaced_letters" in codes(assess_extraction(pages(spaced), page_count=1))


def test_repeated_running_headers_are_reported_once():
    header = "Synthetic Economic Outlook | October 2026"
    report = assess_extraction(pages(*(f"{header}\n{PROSE}" for _ in range(4))), page_count=4)
    assert "repeated_lines" in codes(report)
    finding = next(f for f in report.findings if f.code == "repeated_lines")
    assert "4 of 4" in finding.message


def test_mostly_numbers_is_informational_not_poor():
    table = "2024 2025 2026 2027\n1.2 2.3 3.4 4.5\n" * 30
    report = assess_extraction(pages(PROSE, table), page_count=2)
    assert "numeric_heavy" in codes(report)
    assert report.grade != "poor"


def test_a_stored_version_is_assessed_from_its_sections(conn):
    version = seed_version(conn, (PROSE, PROSE))
    report = version_quality(conn, version)
    assert report.version_id == version and report.grade == "ok"
    assert version_quality(conn, 999_999) is None
