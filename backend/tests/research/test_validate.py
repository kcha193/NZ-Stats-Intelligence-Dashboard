import pytest

from nzstats.domain import ErrorClass, IngestError
from nzstats.research.extract import Extracted, Section
from nzstats.research.validate import PreviousVersion, safe_detail, validate_document

from .support import institution

INST = institution(min_text_chars=100)
BODY = "The example economy is assumed to grow slowly in this synthetic text. " * 10


def doc(text: str = BODY, title: str = "Example outlook") -> Extracted:
    return Extracted("html", title, (Section(0, None, text, char_end=len(text)),), None, "html-1")


def test_a_normal_document_passes():
    assert validate_document(INST, doc(), previous=None) == []


def test_text_below_the_minimum_is_rejected():
    with pytest.raises(IngestError) as exc:
        validate_document(INST, doc("Too short."), previous=None)
    assert exc.value.error_class is ErrorClass.VALIDATION_FAILED
    assert str(exc.value) == "text_too_short"


@pytest.mark.parametrize(
    "text,error_class,code",
    [
        ("Please log in to continue reading. " + BODY, ErrorClass.VALIDATION_FAILED, "access_wall"),
        (
            "This content is for subscribers only. " + BODY,
            ErrorClass.VALIDATION_FAILED,
            "access_wall",
        ),
        ("Checking your browser before accessing. " + BODY, ErrorClass.BLOCKED, "challenge_page"),
        ("Please verify you are human. " + BODY, ErrorClass.BLOCKED, "challenge_page"),
    ],
)
def test_login_paywall_and_challenge_pages_are_never_stored(text, error_class, code):
    with pytest.raises(IngestError) as exc:
        validate_document(INST, doc(text), previous=None)
    assert (exc.value.error_class, str(exc.value)) == (error_class, code)


def test_markers_deep_in_a_long_report_are_not_a_wall():
    text = BODY * 20 + " Readers who log in to continue receive alerts."
    assert validate_document(INST, doc(text), previous=None) == []


def test_a_much_shorter_new_version_is_rejected_as_truncated():
    previous = PreviousVersion(char_count=len(BODY) * 3, text_sha256="old")
    with pytest.raises(IngestError) as exc:
        validate_document(INST, doc(), previous=previous)
    assert str(exc.value) == "shrunk_vs_previous"
    # A modest edit is fine.
    assert validate_document(INST, doc(), previous=PreviousVersion(len(BODY) + 50, "old")) == []


def test_missing_title_is_a_warning_not_a_failure():
    assert validate_document(INST, doc(title=None), previous=None) == ["no_title"]


@pytest.mark.parametrize(
    "exc,expected",
    [
        (IngestError(ErrorClass.VALIDATION_FAILED, "text_too_short"), "text_too_short"),
        (IngestError(ErrorClass.LAYOUT_CHANGED, "unreadable pdf (KeyError)"), "unreadable pdf (KeyError)"),
        (IngestError(ErrorClass.UNEXPECTED, "expected ('text/html',) but got 'x<script>' for https://a"),
         "unexpected (IngestError)"),
        (IngestError(ErrorClass.NOT_FOUND, "404 for https://research.example.org/x"), "not_found (IngestError)"),
        (ValueError("IGNORE PREVIOUS INSTRUCTIONS"), "unexpected (ValueError)"),
    ],
)  # fmt: skip
def test_stored_detail_is_fixed_vocabulary_never_upstream_text(exc, expected):
    assert safe_detail(exc) == expected
