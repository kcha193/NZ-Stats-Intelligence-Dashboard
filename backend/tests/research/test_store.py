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
    vid, _ = _version(conn, p1, "same")  # idempotent: the same version is reused
    assert store.find_text_elsewhere(conn, "same", exclude_publication_id=p1) is None
    assert store.find_text_elsewhere(conn, "same", exclude_publication_id=p2) == (p1, vid)


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


def _dates(conn, pub):
    row = conn.execute(
        "SELECT published_on, published_at, published_precision FROM research_publication WHERE id=?",
        (pub,),
    ).fetchone()
    return tuple(row)


def test_a_day_only_replacement_clears_the_old_timestamp(conn):
    inst = _inst(conn)
    pub, _ = _pub(conn, inst, published_on="2026-08-13", published_at="2026-08-12T20:00:00Z",
                  precision="instant")  # fmt: skip
    _pub(conn, inst, published_on="2026-08-14", published_at=None, precision="day")
    assert _dates(conn, pub) == ("2026-08-14", None, "day")


def test_a_replacement_instant_replaces_the_whole_date_group(conn):
    inst = _inst(conn)
    pub, _ = _pub(conn, inst, published_on="2026-08-13", published_at=None, precision="day")
    _pub(conn, inst, published_on="2026-08-14", published_at="2026-08-13T20:30:00Z",
         precision="instant")  # fmt: skip
    assert _dates(conn, pub) == ("2026-08-14", "2026-08-13T20:30:00Z", "instant")


def test_no_replacement_date_keeps_the_existing_group(conn):
    inst = _inst(conn)
    pub, _ = _pub(conn, inst, published_on="2026-08-13", published_at="2026-08-12T20:00:00Z",
                  precision="instant")  # fmt: skip
    _pub(conn, inst, published_on=None, published_at=None, precision=None)
    assert _dates(conn, pub) == ("2026-08-13", "2026-08-12T20:00:00Z", "instant")


def test_a_new_publication_may_have_no_date_and_a_later_date_fills_it(conn):
    inst = _inst(conn)
    pub, _ = _pub(conn, inst, published_on=None, published_at=None, precision=None)
    assert _dates(conn, pub) == (None, None, None)
    _pub(conn, inst, published_on="2026-08-14", published_at=None, precision="day")
    assert _dates(conn, pub) == ("2026-08-14", None, "day")


def test_independent_content_clears_a_stale_duplicate_attribution(conn):
    inst = _inst(conn)
    original, _ = _pub(conn, inst, doc_key="anz:www.anz.co.nz/a")
    original_version_id, _ = _version(conn, original, "same-text")
    copy, _ = _pub(conn, inst, doc_key="anz:www.anz.co.nz/b", url="https://www.anz.co.nz/b")
    store.mark_duplicate(conn, copy, original, original_version_id)
    assert conn.execute("SELECT duplicate_of_id FROM research_publication WHERE id=?",
                        (copy,)).fetchone()[0] == original  # fmt: skip
    _version(conn, copy, "different-text")
    assert conn.execute("SELECT duplicate_of_id FROM research_publication WHERE id=?",
                        (copy,)).fetchone()[0] is None  # fmt: skip
    # The original is untouched and still current.
    assert store.current_version(conn, original) is not None


def test_a_duplicate_without_its_own_version_keeps_its_attribution(conn):
    inst = _inst(conn)
    original, _ = _pub(conn, inst, doc_key="anz:www.anz.co.nz/a")
    original_version_id, _ = _version(conn, original, "same-text")
    copy, _ = _pub(conn, inst, doc_key="anz:www.anz.co.nz/b", url="https://www.anz.co.nz/b")
    store.mark_duplicate(conn, copy, original, original_version_id)
    _pub(conn, inst, doc_key="anz:www.anz.co.nz/b", url="https://www.anz.co.nz/b", title="Renamed")
    assert conn.execute("SELECT duplicate_of_id FROM research_publication WHERE id=?",
                        (copy,)).fetchone()[0] == original  # fmt: skip


def test_reactivating_an_old_version_of_an_independent_publication_stays_independent(conn):
    inst = _inst(conn)
    pub, _ = _pub(conn, inst)
    _version(conn, pub, "t1")
    _version(conn, pub, "t2")
    _version(conn, pub, "t1")  # revert
    assert conn.execute("SELECT duplicate_of_id FROM research_publication WHERE id=?",
                        (pub,)).fetchone()[0] is None  # fmt: skip


def _dup_row(conn, pub):
    row = conn.execute(
        "SELECT duplicate_of_id, duplicate_of_version_id FROM research_publication WHERE id=?",
        (pub,),
    ).fetchone()
    return tuple(row)


def test_a_duplicate_keeps_the_exact_version_it_matched_after_the_original_is_revised(conn):
    inst = _inst(conn)
    a, _ = _pub(conn, inst, doc_key="anz:www.anz.co.nz/a")
    x_version, _ = _version(conn, a, "text-x")
    b, _ = _pub(conn, inst, doc_key="anz:www.anz.co.nz/b", url="https://www.anz.co.nz/b")
    assert store.find_text_elsewhere(conn, "text-x", exclude_publication_id=b) == (a, x_version)
    store.mark_duplicate(conn, b, a, x_version)
    y_version, _ = _version(conn, a, "text-y")  # the original is revised afterwards
    assert y_version != x_version and store.current_version(conn, a)["id"] == y_version
    assert _dup_row(conn, b) == (a, x_version)  # still attributed to the text it actually matched
    assert conn.execute("SELECT text_sha256 FROM research_document_version WHERE id=?",
                        (x_version,)).fetchone()[0] == "text-x"  # fmt: skip


def test_a_new_publication_matching_a_historical_version_records_that_exact_version(conn):
    inst = _inst(conn)
    a, _ = _pub(conn, inst, doc_key="anz:www.anz.co.nz/a")
    x_version, _ = _version(conn, a, "text-x")
    _version(conn, a, "text-y")  # revised before B appears
    b, _ = _pub(conn, inst, doc_key="anz:www.anz.co.nz/b", url="https://www.anz.co.nz/b")
    assert store.find_text_elsewhere(conn, "text-x", exclude_publication_id=b) == (a, x_version)


def test_a_current_match_is_preferred_over_an_older_version_elsewhere(conn):
    inst = _inst(conn)
    a, _ = _pub(conn, inst, doc_key="anz:www.anz.co.nz/a")
    _version(conn, a, "shared")
    _version(conn, a, "other")  # A no longer serves "shared"
    c, _ = _pub(conn, inst, doc_key="anz:www.anz.co.nz/c", url="https://www.anz.co.nz/c")
    c_version, _ = _version(conn, c, "shared")  # C serves it now
    b, _ = _pub(conn, inst, doc_key="anz:www.anz.co.nz/b", url="https://www.anz.co.nz/b")
    assert store.find_text_elsewhere(conn, "shared", exclude_publication_id=b) == (c, c_version)


def test_becoming_independent_clears_the_exact_version_too(conn):
    inst = _inst(conn)
    a, _ = _pub(conn, inst, doc_key="anz:www.anz.co.nz/a")
    x_version, _ = _version(conn, a, "text-x")
    b, _ = _pub(conn, inst, doc_key="anz:www.anz.co.nz/b", url="https://www.anz.co.nz/b")
    store.mark_duplicate(conn, b, a, x_version)
    _version(conn, b, "b-own-text")
    assert _dup_row(conn, b) == (None, None)
