"""Phase 3E: permission-compliant manual document import. Every document body is SYNTHETIC FIXTURE text.

Manual import is a separate, recorded permission from automated fetching: a source can allow an owner-supplied copy
to be stored while the crawler stays refused. It never requests anything, and every later gate (LLM processing,
public display, per-summary review and publication) still applies.
"""

import json
import sqlite3
from datetime import date

import pytest

from nzstats.research.ingest import refusal_for
from nzstats.research.manual_import import ImportRefused, import_document
from nzstats.research.registry import RegistryError
from nzstats.research.summarise import eligible_versions
from nzstats.sources.artifacts import ArtifactStore

from .conftest import NOW
from .pdf_support import text_pdf
from .support import BASE, institution

PARA = "The example economy is assumed to grow slowly in this synthetic fixture text. "
URL = f"{BASE}/research/outlook-2026"
MANUAL = {
    "review_status": "needs_review",
    "approved_by": None,
    "approved_on": None,
    "approval_note": None,
    "manual_import": "approved",
    "manual_import_approved_by": "Test Owner",
    "manual_import_approved_on": "2026-10-28",
    "manual_import_note": "synthetic: terms read directly permit storing a downloaded copy",
}


def manual(**overrides):
    return institution(**{**MANUAL, **overrides})


def html(title: str = "Synthetic outlook", words: str = PARA * 8) -> bytes:
    return (
        f"<html><head><title>{title}</title></head><body><main><h1>{title}</h1><p>{words}</p>"
        f"<h2>Risks</h2><p>{PARA * 2}</p></main></body></html>"
    ).encode()


@pytest.fixture()
def artifacts(tmp_path):
    return ArtifactStore(tmp_path / "raw")


def do_import(conn, inst, body=None, *, url=URL, fmt="html", importer="Test Owner", **kw):
    return import_document(
        conn, inst, body=html() if body is None else body, file_format=fmt, url=url,
        importer=importer, note=kw.pop("note", "downloaded in a browser on 2026-10-28"), now=NOW, **kw,
    )  # fmt: skip


# --- registry ---------------------------------------------------------------------------------------------------


def test_manual_import_is_denied_by_default_and_refused():
    inst = institution(review_status="needs_review", approved_by=None, approved_on=None,
                       approval_note=None)  # fmt: skip
    assert not inst.manual_import_allowed
    assert inst.import_refusal() == "manual import not approved for this source"


@pytest.mark.parametrize("field", ["manual_import_approved_by", "manual_import_approved_on",
                                   "manual_import_note"])  # fmt: skip
def test_manual_import_approval_needs_all_three_fields(field):
    with pytest.raises(RegistryError, match=field):
        manual(**{field: None})


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"content_policy": "metadata_only"}, "content_policy 'full_text'"),
        ({"terms_evidence": "search"}, "terms_evidence = 'direct'"),
        ({"review_status": "restricted", "content_policy": "full_text"}, "restricted"),
        ({"manual_import": "maybe"}, "invalid manual_import"),
    ],
)
def test_manual_import_approval_is_refused_without_its_preconditions(overrides, message):
    with pytest.raises(RegistryError, match=message):
        manual(**overrides)


def test_manual_import_does_not_grant_automated_access():
    inst = manual()
    assert inst.manual_import_allowed and inst.source_permitted
    assert not inst.automated_access_allowed
    assert refusal_for(inst, dry_run=False) == "needs review: no recorded approval"


def test_llm_and_display_permissions_are_accepted_for_a_manual_import_source():
    inst = manual(llm_processing="local_only", llm_processing_note="synthetic",
                  public_display="link_only", public_display_approved_by="Test Owner",
                  public_display_approved_on="2026-10-28", public_display_note="synthetic")  # fmt: skip
    assert inst.llm_refusal(hosted=False) is None
    assert inst.display_level().value == "link_only"


def test_licence_snapshot_records_the_manual_import_permission():
    assert manual().licence_snapshot()["manual_import"] == "approved"
    assert institution().licence_snapshot()["manual_import"] == "denied"


# --- import ----------------------------------------------------------------------------------------------------


def test_import_stores_a_new_version_with_provenance_and_an_audit_record(conn, artifacts):
    result = do_import(conn, manual(), artifacts=artifacts)
    assert result.outcome == "new" and result.version_id is not None
    version = conn.execute("SELECT * FROM research_document_version WHERE id=?",
                           (result.version_id,)).fetchone()  # fmt: skip
    assert version["acquisition"] == "manual"
    assert json.loads(version["licence_snapshot"])["manual_import"] == "approved"
    assert len(version["content_sha256"]) == 64
    sections = conn.execute("SELECT COUNT(*) FROM research_section WHERE version_id=?",
                            (result.version_id,)).fetchone()[0]  # fmt: skip
    assert sections >= 2
    audit = conn.execute("SELECT * FROM research_manual_import").fetchall()
    assert len(audit) == 1
    row = audit[0]
    assert (row["outcome"], row["imported_by"], row["version_id"]) == (
        "new",
        "Test Owner",
        result.version_id,
    )
    assert row["content_sha256"] == version["content_sha256"]
    assert row["url"] == URL and row["file_format"] == "html"
    assert json.loads(row["licence_snapshot"])["manual_import_approved_by"] == "Test Owner"
    raw = conn.execute(
        "SELECT * FROM raw_artifact WHERE id=?", (version["raw_artifact_id"],)
    ).fetchone()
    assert raw["http_status"] == 0  # not fetched over HTTP
    assert (artifacts._dir / raw["path"]).read_bytes() == html()


def test_crawled_versions_default_to_crawler_acquisition(conn):
    from .llm_support import seed_version

    version = seed_version(conn)
    assert conn.execute("SELECT acquisition FROM research_document_version WHERE id=?",
                        (version,)).fetchone()[0] == "crawler"  # fmt: skip


def test_reimport_of_the_same_text_is_unchanged_and_still_audited(conn, artifacts):
    first = do_import(conn, manual(), artifacts=artifacts)
    again = do_import(conn, manual(), artifacts=artifacts, importer="Second Person")
    assert again.outcome == "unchanged" and again.version_id == first.version_id
    outcomes = [
        r[0] for r in conn.execute("SELECT outcome FROM research_manual_import ORDER BY id")
    ]
    assert outcomes == ["new", "unchanged"]


def test_a_revised_copy_becomes_a_new_version_and_the_old_one_is_kept(conn, artifacts):
    first = do_import(conn, manual(), artifacts=artifacts)
    second = do_import(conn, manual(), html(words=PARA * 9 + "Revised. "), artifacts=artifacts)
    assert second.outcome == "updated" and second.version_id != first.version_id
    rows = conn.execute("SELECT id, version_no, superseded_at FROM research_document_version"
                        " ORDER BY id").fetchall()  # fmt: skip
    assert [(r["version_no"], r["superseded_at"] is not None) for r in rows] == [
        (1, True),
        (2, False),
    ]


def test_import_refuses_when_not_approved_and_writes_nothing(conn, artifacts):
    inst = institution(
        review_status="needs_review", approved_by=None, approved_on=None, approval_note=None
    )
    with pytest.raises(ImportRefused, match="manual import not approved"):
        do_import(conn, inst, artifacts=artifacts)
    assert conn.execute("SELECT COUNT(*) FROM research_document_version").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM research_manual_import").fetchone()[0] == 0
    assert not (artifacts._dir).exists()


@pytest.mark.parametrize(
    "url",
    [
        "http://research.example.org/research/outlook",  # not https
        "https://elsewhere.example.com/research/outlook",  # not an allowed host
        "https://user@research.example.org/research/outlook",
        "",
    ],
)
def test_import_refuses_an_address_outside_the_institutions_url_policy(conn, artifacts, url):
    with pytest.raises(ImportRefused, match="address"):
        do_import(conn, manual(), url=url, artifacts=artifacts)
    assert conn.execute("SELECT COUNT(*) FROM research_publication").fetchone()[0] == 0


def test_import_refuses_a_blocked_path(conn, artifacts):
    inst = manual(blocked_path_prefixes=["/members/"])
    with pytest.raises(ImportRefused, match="address"):
        do_import(conn, inst, url=f"{BASE}/members/report", artifacts=artifacts)


@pytest.mark.parametrize("importer", ["", "   "])
def test_import_needs_a_named_importer_and_a_note(conn, artifacts, importer):
    with pytest.raises(ImportRefused, match="importer"):
        do_import(conn, manual(), importer=importer, artifacts=artifacts)
    with pytest.raises(ImportRefused, match="note"):
        do_import(conn, manual(), note=" ", artifacts=artifacts)


def test_import_rejects_a_login_wall_like_the_crawler(conn, artifacts):
    wall = html("Sign in", "Please sign in to continue reading this report. " + PARA * 6)
    with pytest.raises(ImportRefused, match="access_wall"):
        do_import(conn, manual(), wall, artifacts=artifacts)
    assert conn.execute("SELECT COUNT(*) FROM research_document_version").fetchone()[0] == 0


def test_import_rejects_a_file_whose_bytes_do_not_match_the_format(conn, artifacts):
    with pytest.raises(ImportRefused, match="not a PDF"):
        do_import(conn, manual(), html(), fmt="pdf", artifacts=artifacts)
    with pytest.raises(ImportRefused, match="format"):
        do_import(conn, manual(), html(), fmt="docx", artifacts=artifacts)


def test_import_rejects_an_oversized_file(conn, artifacts):
    with pytest.raises(ImportRefused, match="larger than"):
        do_import(conn, manual(), b"x" * 21, artifacts=artifacts, max_bytes=20)


def test_import_of_a_pdf_keeps_page_numbers(conn, artifacts):
    body = text_pdf([[f"Synthetic outlook page {i} (SYNTHETIC FIXTURE)", PARA * 3] for i in (1, 2)])
    result = do_import(
        conn, manual(), body, fmt="pdf", url=f"{BASE}/research/outlook.pdf", artifacts=artifacts
    )
    pages = [r[0] for r in conn.execute("SELECT page_start FROM research_section WHERE version_id=?"
                                        " ORDER BY ordinal", (result.version_id,))]  # fmt: skip
    assert pages == [1, 2]


def test_the_audit_table_is_append_only(conn, artifacts):
    do_import(conn, manual(), artifacts=artifacts)
    with pytest.raises(sqlite3.DatabaseError, match="immutable"):
        conn.execute("UPDATE research_manual_import SET imported_by='x'")
    with pytest.raises(sqlite3.DatabaseError, match="immutable"):
        conn.execute("DELETE FROM research_manual_import")


def test_an_imported_version_is_eligible_for_a_permitted_model_and_refused_after_revocation(
    conn, artifacts
):
    allowed = manual(llm_processing="local_only", llm_processing_note="synthetic")
    result = do_import(conn, allowed, artifacts=artifacts)
    found, refusals = eligible_versions(conn, {"example": allowed}, hosted=False)
    assert [c.version_id for c in found] == [result.version_id] and refusals == []
    revoked = manual(manual_import="denied", manual_import_approved_by=None, manual_import_approved_on=None,
                     manual_import_note=None, llm_processing="denied", llm_processing_note=None)  # fmt: skip
    found, refusals = eligible_versions(conn, {"example": revoked}, hosted=False)
    assert found == [] and refusals == [("example", "llm processing denied for this source")]


# --- revocation: an imported document passes every later gate, and each revocation takes effect at once -----------


def _imported_and_published(conn, artifacts):
    from .llm_support import SECTIONS
    from .public_support import store_summary

    body = text_pdf([[SECTIONS[0]], [SECTIONS[1]]])
    inst = _displayable_manual()
    result = do_import(conn, inst, body, fmt="pdf", url=f"{BASE}/research/outlook.pdf", artifacts=artifacts,
                       published_on=date(2026, 8, 13))  # fmt: skip
    return result.version_id, store_summary(conn, result.version_id)


def _displayable_manual(**overrides):
    raw = {"min_text_chars": 50, "llm_processing": "local_only", "llm_processing_note": "synthetic",
           "public_display": "excerpt", "public_display_approved_by": "Test Owner",
           "public_display_approved_on": "2026-10-28", "public_display_note": "synthetic"}  # fmt: skip
    return manual(**{**raw, **overrides})


NO_DISPLAY = {"public_display": "none", "public_display_approved_by": None, "public_display_approved_on": None,
              "public_display_note": None}  # fmt: skip
REVOKED = {
    "manual import": {"manual_import": "denied", "manual_import_approved_by": None, "manual_import_approved_on": None,
                      "manual_import_note": None, "llm_processing": "denied", "llm_processing_note": None,
                      **NO_DISPLAY},
    "public display": NO_DISPLAY,
}  # fmt: skip


@pytest.mark.parametrize("revoked", sorted(REVOKED))
def test_an_imported_published_summary_disappears_when_a_permission_is_revoked(
    conn, artifacts, revoked
):
    from nzstats.research.public import public_summaries, why_not_public

    _, sid = _imported_and_published(conn, artifacts)
    assert [p.id for p in public_summaries(conn, {"example": _displayable_manual()})] == [sid]
    reg = {"example": _displayable_manual(**REVOKED[revoked])}
    assert public_summaries(conn, reg) == []
    assert "displays nothing" in why_not_public(conn, reg, sid)


def test_revoking_llm_processing_withholds_the_ai_text_of_an_imported_document(conn, artifacts):
    from nzstats.research.public import public_summaries

    _, sid = _imported_and_published(conn, artifacts)
    reg = {"example": _displayable_manual(llm_processing="denied", llm_processing_note=None)}
    assert [(p.id, p.display.value) for p in public_summaries(conn, reg)] == [(sid, "link_only")]


def test_the_api_applies_a_revocation_on_the_next_request(make, tmp_path):
    build, conn = make
    _, sid = _imported_and_published(conn, ArtifactStore(tmp_path / "raw"))
    current = {"example": _displayable_manual()}
    client = build(reg=lambda: current)
    assert client.get(f"/api/research/summaries/{sid}").status_code == 200
    current = {"example": _displayable_manual(**REVOKED["manual import"])}
    assert client.get(f"/api/research/summaries/{sid}").status_code == 404
    assert client.get("/api/research/feed").json()["total"] == 0


# --- review finding: each permission covers only what was obtained under it ---------------------------------------


def test_a_manual_import_approval_does_not_revive_crawled_versions_after_crawler_approval_is_revoked(
    conn, artifacts
):
    from .llm_support import seed_version
    from .public_support import store_summary

    crawled = seed_version(conn)  # stored by the crawler while the source was approved
    sid = store_summary(conn, crawled)
    from nzstats.research.public import public_summaries

    both = _displayable_manual(review_status="approved", approved_by="Owner", approved_on="2026-10-25",
                               approval_note="synthetic")  # fmt: skip
    assert [p.id for p in public_summaries(conn, {"example": both})] == [sid]
    manual_only = _displayable_manual()  # crawler approval revoked; manual import still approved
    assert public_summaries(conn, {"example": manual_only}) == []
    found, refusals = eligible_versions(conn, {"example": manual_only}, hosted=False)
    assert found == [] and refusals == [("example", "llm processing denied for this source")]


def test_a_crawler_approval_does_not_cover_imported_versions_after_manual_import_is_revoked(
    conn, artifacts
):
    from nzstats.research.public import public_summaries

    _, sid = _imported_and_published(conn, artifacts)
    crawler_only = _displayable_manual(review_status="approved", approved_by="Owner", approved_on="2026-10-25",
                                       approval_note="synthetic", manual_import="denied",
                                       manual_import_approved_by=None, manual_import_approved_on=None,
                                       manual_import_note=None)  # fmt: skip
    assert public_summaries(conn, {"example": crawler_only}) == []
    found, _ = eligible_versions(conn, {"example": crawler_only}, hosted=False)
    assert found == []
