"""Phase 4AG: a successful build unlocks nothing. ANZ stays exactly as the owner's recorded evidence leaves it, the PDF
reader stays inside one module and one child process, and reading a held PDF touches no network (SYNTHETIC FIXTURE)."""

import re
import socket

import pytest

from nzstats.research.extract import ExtractionLimits
from nzstats.research.registry import (
    ContentPolicy,
    LlmProcessing,
    ManualImport,
    PrivateDisplay,
    PublicDisplay,
    ReviewStatus,
    load_registry,
)
from nzstats.research.table_words import extract_words

from .pdf_stream_support import raw_pdf, row
from .test_bank_isolation import SRC, imports

REAL_BANKS = ("anz", "asb", "bnz", "westpac", "kiwibank")


@pytest.mark.parametrize("key", REAL_BANKS)
def test_every_real_bank_permission_field_is_unchanged_and_nothing_is_permitted(key):
    inst = load_registry()[key]
    assert inst.review_status is ReviewStatus.NEEDS_REVIEW
    assert inst.manual_import is ManualImport.DENIED and inst.manual_import_approved_by is None
    assert inst.llm_processing is LlmProcessing.DENIED
    assert inst.public_display is PublicDisplay.NONE
    assert inst.private_display is PrivateDisplay.NONE
    assert inst.content_policy in (ContentPolicy.METADATA_ONLY, ContentPolicy.NONE)
    assert not inst.source_permitted and not inst.manual_import_allowed


def test_anz_records_no_approval_of_any_kind():
    inst = load_registry()["anz"]
    assert (inst.approved_by, inst.approved_on, inst.approval_note) == (None, None, None)
    assert (inst.manual_import_approved_on, inst.manual_import_note) == (None, None)
    assert (inst.public_display_approved_by, inst.private_display_approved_by) == (None, None)


def test_the_pdf_reader_library_is_imported_by_the_words_module_alone():
    users = {
        p.relative_to(SRC).as_posix()
        for p in SRC.rglob("*.py")
        if any(n == "pdfminer" or n.startswith("pdfminer.") for n in imports(p))
    }
    # `imports` reads module-level imports; the library is imported inside the function, in the child process only.
    source = (SRC / "research" / "table_words.py").read_text()
    assert "from pdfminer" in source
    assert users <= {"research/table_words.py"}
    others = [
        p.relative_to(SRC).as_posix()
        for p in SRC.rglob("*.py")
        if p.name != "table_words.py"
        and re.search(r"^\s*(?:from|import) pdfminer", p.read_text(), re.M)
    ]
    assert others == []


def test_the_installed_pdf_reader_is_at_or_above_the_fixed_security_floor():
    import pdfminer

    assert (
        int(pdfminer.__version__) >= 20251230
    )  # CVE-2025-64512 and its incomplete-fix follow-up CVE-2025-70559


def test_reading_a_held_pdf_opens_no_connection(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("reading a held PDF must not use the network")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    pdf = raw_pdf([row(700, [(72, "OCR"), (252, "3.25")])])
    assert [w.text for w in extract_words(pdf, ExtractionLimits(), isolate=False)] == [
        "OCR",
        "3.25",
    ]


def test_the_child_process_is_the_default_and_bounded():
    from nzstats.research import table_words

    assert "_apply_child_limits(limits)" in (SRC / "research" / "table_words.py").read_text()
    assert table_words._reply_cap() < 64 * 1024 * 1024
