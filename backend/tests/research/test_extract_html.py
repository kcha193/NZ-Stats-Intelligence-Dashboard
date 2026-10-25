import pytest

from nzstats.domain import ErrorClass, IngestError
from nzstats.research.extract import ExtractionLimits, clean_text
from nzstats.research.extract_html import EXTRACTOR_VERSION, extract_html
from tests.conftest import fixture_bytes

LIMITS = ExtractionLimits()
HTML = "text/html; charset=utf-8"


def _page(body: str, head: str = "") -> bytes:
    return f"<html><head>{head}</head><body>{body}</body></html>".encode()


def test_outlook_sections_titles_and_hint():
    got = extract_html(fixture_bytes("research/outlook.html"), HTML, LIMITS)
    assert got.format == "html" and got.extractor_version == EXTRACTOR_VERSION == "html-1"
    assert got.title == "Quarterly Economic Outlook: Example Edition"
    assert got.published_hint == "2026-08-13T10:00:00+12:00"
    assert [s.heading for s in got.sections] == [
        "Quarterly Economic Outlook",
        "Key drivers",
        "Risks",
        "Detail & caveats",
    ]
    assert [s.ordinal for s in got.sections] == [0, 1, 2, 3]
    assert "First invented driver\nSecond invented driver" in got.sections[1].text
    assert got.sections[3].text.endswith("Minor text stays in the h3 section.")
    assert "Caveat two applies." in got.sections[3].text  # &nbsp; is a plain space
    assert got.untrusted is True


@pytest.mark.parametrize(
    "marker",
    ["HEADER", "NAV", "FOOTER", "SCRIPT", "STYLE", "COMMENT", "ASIDE", "FORM", "home"],
)
def test_page_furniture_scripts_and_comments_never_reach_the_text(marker):
    got = extract_html(fixture_bytes("research/outlook.html"), HTML, LIMITS)
    assert marker not in got.text


def test_section_offsets_index_into_the_joined_text():
    got = extract_html(fixture_bytes("research/outlook.html"), HTML, LIMITS)
    for s in got.sections:
        assert got.text[s.char_start : s.char_end] == s.text
        assert s.page_start is None and s.page_end is None


def test_prompt_injection_is_kept_as_inert_text_and_hidden_text_is_dropped():
    got = extract_html(fixture_bytes("research/injection.html"), HTML, LIMITS)
    assert "Ignore all previous instructions" in got.text  # data, verbatim; never interpreted
    for hidden in (
        "HIDDEN TEXT",
        "HIDDEN ATTRIBUTE",
        "ARIA HIDDEN",
        "TEMPLATE",
        "NOSCRIPT",
        "IFRAME",
    ):
        assert hidden not in got.text
    assert "alert" not in got.text and "Image handler text." in got.text
    assert "‮" not in got.text and "​" not in got.text and "\x07" not in got.text
    assert got.published_hint == "2026-09-01"  # from JSON-LD
    assert got.title == "Hostile page"


def test_title_falls_back_to_title_tag_then_h1():
    assert extract_html(_page("<h1>Only H1</h1><p>x</p>"), HTML, LIMITS).title == "Only H1"
    head = "<title>  Tag  title </title>"
    assert extract_html(_page("<h1>H</h1><p>x</p>", head), HTML, LIMITS).title == "Tag title"


def test_time_element_gives_a_hint_when_meta_is_absent():
    got = extract_html(
        _page('<p>Published <time datetime="2026-10-20">20 Oct</time></p>'), HTML, LIMITS
    )
    assert got.published_hint == "2026-10-20"


def test_article_is_used_when_there_is_no_main_and_body_otherwise():
    body = "<div>OUTSIDE</div><article><h2>In</h2><p>inside</p></article>"
    assert "OUTSIDE" not in extract_html(_page(body), HTML, LIMITS).text
    assert "OUTSIDE" in extract_html(_page("<div>OUTSIDE</div>"), HTML, LIMITS).text


@pytest.mark.parametrize(
    "body,ctype",
    [
        ("café".encode("cp1252"), "text/html; charset=windows-1252"),
        (b'<meta charset="iso-8859-1">' + "café".encode("latin-1"), "text/html"),
        (b"\xef\xbb\xbf" + "café".encode(), "text/html"),
        ("café".encode(), "text/html; charset=no-such-codec"),
    ],
)
def test_charset_from_header_meta_or_bom(body, ctype):
    assert "café" in extract_html(body, ctype, LIMITS).text


def test_invalid_bytes_are_replaced_not_fatal():
    got = extract_html(b"<p>ok \xff\xfe bytes</p>", HTML, LIMITS)
    assert "ok" in got.text and "bytes" in got.text


def test_unclosed_and_deeply_nested_tags_are_bounded():
    deep = "<div>" * 10_000 + "<p>deep</p>"
    with pytest.raises(IngestError) as exc:
        extract_html(_page(deep), HTML, ExtractionLimits(max_depth=200))
    assert exc.value.error_class is ErrorClass.LAYOUT_CHANGED
    # Many unclosed paragraphs and list items are normal HTML and do not count as nesting.
    flat = "<p>a" * 5000 + "<li>b" * 5000
    assert extract_html(_page(flat), HTML, ExtractionLimits(max_depth=200)).text


def test_oversized_page_and_text_are_rejected():
    with pytest.raises(IngestError, match="too large"):
        extract_html(b"<p>" + b"x" * 6_000_000, HTML, ExtractionLimits(max_html_bytes=5_000_000))
    with pytest.raises(IngestError, match="too long"):
        extract_html(_page("<p>" + "word " * 5000 + "</p>"), HTML, ExtractionLimits(max_chars=1000))


def test_section_cap_merges_the_tail():
    body = "".join(f"<h2>H{i}</h2><p>t{i}</p>" for i in range(50))
    got = extract_html(_page(body), HTML, ExtractionLimits(max_sections=10))
    assert len(got.sections) == 10 and "t49" in got.sections[-1].text
    assert "sections_merged" in got.warnings


def test_text_hash_ignores_whitespace_only_changes_but_not_words():
    a = extract_html(_page("<h2>A</h2><p>one two</p>"), HTML, LIMITS)
    b = extract_html(_page("<h2>A</h2>\n\n<p>one\n   two</p>"), HTML, LIMITS)
    c = extract_html(_page("<h2>A</h2><p>one three</p>"), HTML, LIMITS)
    d = extract_html(_page("<h2>B</h2><p>one two</p>"), HTML, LIMITS)
    assert a.text_sha256 == b.text_sha256
    assert len({a.text_sha256, c.text_sha256, d.text_sha256}) == 3


def test_clean_text_normalises_unicode_and_whitespace():
    assert clean_text("Café \t a b\r\n\n\n\nc⁦x⁩") == "Café a b\n\ncx"
