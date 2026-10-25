from datetime import timedelta

import pytest

from nzstats.research import store
from tests.research.conftest import NOW


def _inst(conn, key="anz"):
    return store.upsert_institution(
        conn,
        key=key,
        name=key.upper(),
        review_status="approved",
        content_policy="full_text",
        now=NOW,
    )


def _pub(conn, inst, doc_key="anz:www.anz.co.nz/a", **kw):
    args = dict(
        doc_key=doc_key, url="https://www.anz.co.nz/a", title="Outlook", series="outlook",
        categories=["economic_outlook"], published_on="2026-08-13", published_at=None,
        precision="day", content_status="extracted", now=NOW,
    )  # fmt: skip
    args.update(kw)
    return store.upsert_publication(conn, inst, **args)


def _version(conn, pub, text_sha, *, content_sha="c", now=NOW, sections=None):
    return store.add_version(
        conn, pub, content_sha256=content_sha, text_sha256=text_sha, fmt="html", fetched_at=now,
        extractor_version="html-1", raw_artifact_id=None, title="Outlook",
        sections=sections or [store.SectionRow(0, "Intro", "Hello world", None, None, 0, 11)],
        page_count=None, licence_snapshot='{"licence":"x"}', now=now,
    )  # fmt: skip


def test_upsert_institution_is_idempotent_and_updates_policy(conn):
    a = _inst(conn)
    b = store.upsert_institution(
        conn, key="anz", name="ANZ", review_status="restricted", content_policy="none", now=NOW
    )
    assert a == b
    row = conn.execute("SELECT review_status, content_policy FROM research_institution").fetchone()
    assert tuple(row) == ("restricted", "none")


def test_upsert_publication_keeps_first_seen_and_reports_created(conn):
    inst = _inst(conn)
    pub, created = _pub(conn, inst)
    assert created
    later = NOW + timedelta(days=1)
    pub2, created2 = _pub(conn, inst, title="Outlook (updated)", now=later)
    assert (pub2, created2) == (pub, False)
    row = conn.execute("SELECT title, first_seen_at, last_seen_at, reference_period"
                       " FROM research_publication").fetchone()  # fmt: skip
    assert row["title"] == "Outlook (updated)"
    assert row["first_seen_at"] == "2026-10-25T01:00:00Z"
    assert row["last_seen_at"] == "2026-10-26T01:00:00Z"
    assert row["reference_period"] is None  # never derived from the publication date


def test_first_version_becomes_current_with_sections(conn):
    pub, _ = _pub(conn, _inst(conn))
    vid, outcome = _version(conn, pub, "t1")
    assert outcome == "new"
    assert store.current_version(conn, pub)["id"] == vid
    sec = conn.execute(
        "SELECT heading, text, char_start, char_end FROM research_section"
    ).fetchall()
    assert [tuple(s) for s in sec] == [("Intro", "Hello world", 0, 11)]


def test_same_text_again_is_unchanged(conn):
    pub, _ = _pub(conn, _inst(conn))
    v1, _ = _version(conn, pub, "t1")
    v2, outcome = _version(conn, pub, "t1", content_sha="different-bytes")
    assert (v2, outcome) == (v1, "unchanged")
    assert conn.execute("SELECT COUNT(*) FROM research_document_version").fetchone()[0] == 1


def test_changed_text_adds_version_and_supersedes_previous(conn):
    pub, _ = _pub(conn, _inst(conn))
    v1, _ = _version(conn, pub, "t1")
    later = NOW + timedelta(days=2)
    v2, outcome = _version(conn, pub, "t2", now=later)
    assert outcome == "new" and v2 != v1
    assert store.current_version(conn, pub)["id"] == v2
    old = conn.execute("SELECT superseded_at, version_no FROM research_document_version WHERE id=?",
                       (v1,)).fetchone()  # fmt: skip
    assert old["superseded_at"] == "2026-10-27T01:00:00Z" and old["version_no"] == 1
    assert conn.execute("SELECT version_no FROM research_document_version WHERE id=?", (v2,)
                        ).fetchone()[0] == 2  # fmt: skip


def test_revert_reuses_version_and_repoints_current(conn):
    pub, _ = _pub(conn, _inst(conn))
    v1, _ = _version(conn, pub, "t1")
    v2, _ = _version(conn, pub, "t2", now=NOW + timedelta(days=1))
    v3, outcome = _version(conn, pub, "t1", now=NOW + timedelta(days=2))
    assert (v3, outcome) == (v1, "reactivated")
    assert store.current_version(conn, pub)["id"] == v1
    rows = {r["id"]: r["superseded_at"] for r in conn.execute(
        "SELECT id, superseded_at FROM research_document_version")}  # fmt: skip
    assert rows[v1] is None and rows[v2] is not None
    assert len(rows) == 2


def test_section_ordinals_unique_per_version(conn):
    pub, _ = _pub(conn, _inst(conn))
    sections = [
        store.SectionRow(0, "A", "x", None, None, 0, 1),
        store.SectionRow(0, "B", "y", None, None, 1, 2),
    ]
    with pytest.raises(Exception, match="UNIQUE"):
        _version(conn, pub, "t1", sections=sections)


def test_find_text_elsewhere_ignores_own_publication(conn):
    inst = _inst(conn)
    p1, _ = _pub(conn, inst)
    p2, _ = _pub(conn, inst, doc_key="anz:www.anz.co.nz/b", url="https://www.anz.co.nz/b")
    _version(conn, p1, "same")
    assert store.find_text_elsewhere(conn, "same", exclude_publication_id=p1) is None
    assert store.find_text_elsewhere(conn, "same", exclude_publication_id=p2) == p1


def test_run_items_and_health(conn):
    inst = _inst(conn)
    run = store.record_run(conn, inst, started_at=NOW, finished_at=NOW, outcome="partial",
                           dry_run=False, counts={"new": 1, "failed": 1},
                           error_class=None, detail=None)  # fmt: skip
    store.record_item(conn, run, url="https://www.anz.co.nz/a", outcome="failed",
                      error_class="validation_failed", detail="extracted_too_short",
                      publication_id=None, version_id=None)  # fmt: skip
    store.set_health(
        conn, inst, state="degraded", now=NOW, success=False, detail="validation_failed"
    )
    store.set_health(
        conn, inst, state="degraded", now=NOW, success=False, detail="validation_failed"
    )
    h = conn.execute(
        "SELECT state, consecutive_failures, last_success_at FROM research_source_health"
    ).fetchone()
    assert (h["state"], h["consecutive_failures"], h["last_success_at"]) == ("degraded", 2, None)
    store.set_health(conn, inst, state="ok", now=NOW, success=True, detail=None)
    h = conn.execute(
        "SELECT state, consecutive_failures, last_success_at FROM research_source_health"
    ).fetchone()
    assert (h["state"], h["consecutive_failures"], h["last_success_at"]) == (
        "ok",
        0,
        "2026-10-25T01:00:00Z",
    )
