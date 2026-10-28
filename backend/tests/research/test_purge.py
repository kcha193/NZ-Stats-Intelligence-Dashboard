"""Targeted purge of stored source content (Phase 3F). Every document body is SYNTHETIC FIXTURE text.

When a permission is withdrawn the licensed text, the model output derived from it and the raw files must be
removable, while the audit trail (who imported what, when, with which hashes; who reviewed and published; what
was spent) stays append-only. A purge is two steps because files cannot join a database transaction: the database
step makes the content unavailable and records what is to be destroyed; the file step removes it and can be resumed.
"""

import hashlib
import os
import sqlite3
import time

import pytest

from nzstats.research import purge, store
from nzstats.research import summary_store as ss
from nzstats.research.manual_import import ImportRefused, import_document
from nzstats.research.public import public_summaries
from nzstats.sources.artifacts import ArtifactStore
from nzstats.store.db import transaction

from .conftest import NOW
from .llm_support import seed_version
from .public_support import DISPLAY, store_summary
from .support import BASE, institution

SENTINEL = "ZEBRAFISH-QUOKKA-7731"
PARA = f"The example economy is assumed to grow slowly in this synthetic fixture text {SENTINEL}. "
URL = f"{BASE}/research/outlook-2026"
APPROVALS = {
    "review_status": "needs_review", "approved_by": None, "approved_on": None, "approval_note": None,
    "manual_import": "approved", "manual_import_approved_by": "Test Owner",
    "manual_import_approved_on": "2026-10-28", "manual_import_note": "synthetic: terms permit a stored copy",
    "llm_processing": "local_only", "llm_processing_note": "synthetic", "public_display": "excerpt", **DISPLAY,
}  # fmt: skip


def inst(**kw):
    return institution(**{**APPROVALS, **kw})


def html(words: str = PARA * 8) -> bytes:
    return (f"<html><head><title>Outlook</title></head><body><main><h1>Outlook</h1><p>{words}</p>"
            f"<h2>Risks</h2><p>{PARA * 2}</p></main></body></html>").encode()  # fmt: skip


@pytest.fixture()
def artifacts(tmp_path):
    return ArtifactStore(tmp_path / "raw")


def do_import(conn, artifacts, body=None, *, url=URL, **kw):
    return import_document(conn, kw.pop("registry", inst()), body=html() if body is None else body,
                           file_format="html", url=url, importer="Test Owner",
                           note="downloaded in a browser", now=NOW, artifacts=artifacts, **kw)  # fmt: skip


def raw_files(artifacts):
    return sorted(p for p in artifacts.root.rglob("*") if p.is_file())


def count(conn, table, where="1=1"):
    return conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}").fetchone()[0]


def imported_and_published(conn, artifacts):
    """A manual import, a summary of it, approved and published; the version id and the summary id."""
    result = do_import(conn, artifacts)
    sections = conn.execute("SELECT ordinal, text FROM research_section WHERE version_id=?",
                            (result.version_id,)).fetchall()  # fmt: skip
    quote = "The example economy is assumed to grow slowly in this synthetic fixture text"
    ordinal = next(r["ordinal"] for r in sections if quote in r["text"])
    data = {
        "outlook": {"text": "Growth is assumed to be slow.", "evidence": [
            {"version_id": result.version_id, "section_ordinal": ordinal, "page": None, "quote": quote}]},
        "indicators": [], "forecasts": [],
    }  # fmt: skip
    sid = store_summary(conn, result.version_id, output=data)
    return result.version_id, sid


REG = {"example": inst()}


def plan(conn, **kw):
    kw.setdefault("acquisition", "manual")
    return purge.plan_purge(conn, "example", **kw)


def apply(conn, artifacts, **kw):
    p = kw.pop("plan", None) or plan(conn)
    return purge.apply_purge(conn, p, artifacts, reason="permission_withdrawn", purged_by="Test Owner",
                             note="licence withdrawn", now=NOW, **kw)  # fmt: skip


# --- planning is read-only ----------------------------------------------------------------------------------------


def test_a_plan_describes_the_purge_and_changes_nothing(conn, artifacts):
    version, sid = imported_and_published(conn, artifacts)
    before = {t: count(conn, t) for t in ("research_section", "research_summary", "research_forecast_claim",
                                          "raw_artifact", "research_summary_publication")}  # fmt: skip
    files = raw_files(artifacts)
    p = plan(conn)
    assert p.version_ids == (version,) and p.summaries == 1 and p.published == 1
    assert p.sections == before["research_section"] and len(p.artifacts) == 1
    assert {t: count(conn, t) for t in before} == before and raw_files(artifacts) == files
    assert count(conn, "research_purge") == 0


def test_nothing_matching_gives_an_empty_plan_and_an_unknown_source_is_an_error(conn, artifacts):
    seed_version(conn)  # a crawler version: not selected by acquisition=manual
    assert plan(conn).version_ids == ()
    with pytest.raises(purge.PurgeError, match="unknown"):
        purge.plan_purge(conn, "nobody", acquisition="manual")
    with pytest.raises(purge.PurgeError, match="select"):
        purge.plan_purge(conn, "example")  # neither an acquisition nor version ids


# --- the purge ----------------------------------------------------------------------------------------------------


def test_a_purge_removes_the_content_and_keeps_the_audit_trail(conn, artifacts):
    version, sid = imported_and_published(conn, artifacts)
    imports = [tuple(r) for r in conn.execute("SELECT * FROM research_manual_import")]
    reviews = [tuple(r) for r in conn.execute("SELECT * FROM research_summary_review")]
    usage = [tuple(r) for r in conn.execute("SELECT * FROM research_llm_usage")]
    ver = dict(
        conn.execute("SELECT * FROM research_document_version WHERE id=?", (version,)).fetchone()
    )
    assert [p.id for p in public_summaries(conn, {"example": inst()})] == [sid]

    result = apply(conn, artifacts)

    assert result.versions == 1 and result.artifacts_removed == 1 and not result.pending
    assert count(conn, "research_section", f"version_id={version}") == 0
    assert count(conn, "research_forecast_claim") == 0 and raw_files(artifacts) == []
    assert count(conn, "raw_artifact") == 0
    # The version stays as a tombstone with its hashes; only what was removed has changed.
    after = dict(
        conn.execute("SELECT * FROM research_document_version WHERE id=?", (version,)).fetchone()
    )
    assert (
        after["purged_at"]
        and after["purge_id"] == result.purge_id
        and after["raw_artifact_id"] is None
    )
    kept = (
        "content_sha256",
        "text_sha256",
        "format",
        "title",
        "acquisition",
        "fetched_at",
        "licence_snapshot",
    )
    assert {k: after[k] for k in kept} == {k: ver[k] for k in kept}
    row = conn.execute("SELECT * FROM research_summary WHERE id=?", (sid,)).fetchone()
    assert row["raw_output"] is None and row["output_json"] == '{"redacted":true}'
    assert row["verification"] == '{"redacted":true}'
    assert (row["status"], row["review_status"], row["output_sha256"]) == (
        "verified",
        "approved",
        row["output_sha256"],
    )
    # Append-only history is exactly as it was, plus one automatic withdrawal.
    assert [tuple(r) for r in conn.execute("SELECT * FROM research_manual_import")] == imports
    assert [tuple(r) for r in conn.execute("SELECT * FROM research_summary_review")] == reviews
    assert [tuple(r) for r in conn.execute("SELECT * FROM research_llm_usage")] == usage
    decisions = [(d["decision"], d["approver"]) for d in conn.execute(
        "SELECT * FROM research_summary_publication ORDER BY id")]  # fmt: skip
    assert decisions == [("publish", "Private Approver"), ("withdraw", "Test Owner")]
    assert public_summaries(conn, {"example": inst()}) == []
    record = conn.execute("SELECT * FROM research_purge").fetchone()
    assert (record["reason"], record["purged_by"], record["versions"], record["claims"]) == (
        "permission_withdrawn",
        "Test Owner",
        1,
        0,
    )
    art = conn.execute("SELECT * FROM research_purge_artifact").fetchone()
    assert art["outcome"] == "removed" and art["removed_at"] and len(art["sha256"]) == 64


def test_the_purged_text_cannot_be_found_in_the_database_files(conn, artifacts, tmp_path):
    imported_and_published(conn, artifacts)
    db = tmp_path / "t.db"
    assert (
        SENTINEL.encode() in db.read_bytes()
        or SENTINEL.encode() in (tmp_path / "t.db-wal").read_bytes()
    )
    apply(conn, artifacts)
    conn.close()
    leftovers = [
        p for p in tmp_path.glob("t.db*") if p.is_file() and SENTINEL.encode() in p.read_bytes()
    ]
    assert leftovers == [], "purged text is still readable in the database or its journal"


def test_a_purge_leaves_other_versions_of_the_source_alone(conn, artifacts):
    other = seed_version(
        conn, key="example", doc="crawled"
    )  # a crawler version of the same institution
    version, _ = imported_and_published(conn, artifacts)
    apply(conn, artifacts)
    assert count(conn, "research_section", f"version_id={other}") == 2
    assert (
        conn.execute(
            "SELECT purged_at FROM research_document_version WHERE id=?", (other,)
        ).fetchone()[0]
        is None
    )
    assert conn.execute("SELECT purged_at FROM research_document_version WHERE id=?",
                        (version,)).fetchone()[0]  # fmt: skip


def test_versions_can_be_selected_by_id(conn, artifacts):
    crawled = seed_version(conn, key="example", doc="crawled")
    p = purge.plan_purge(conn, "example", version_ids=(crawled,))
    assert p.version_ids == (crawled,)
    purge.apply_purge(
        conn, p, artifacts, reason="takedown", purged_by="Owner", note="requested", now=NOW
    )
    assert count(conn, "research_section", f"version_id={crawled}") == 0
    with pytest.raises(purge.PurgeError, match="not a version of"):
        purge.plan_purge(conn, "example", version_ids=(9999,))


def test_a_purge_needs_a_name_a_note_and_a_known_reason(conn, artifacts):
    imported_and_published(conn, artifacts)
    for kw in ({"purged_by": " "}, {"note": ""}, {"reason": "because"}):
        args = {"reason": "takedown", "purged_by": "Owner", "note": "why", **kw}
        with pytest.raises(purge.PurgeError):
            purge.apply_purge(conn, plan(conn), artifacts, now=NOW, **args)
    assert count(conn, "research_purge") == 0 and count(conn, "research_section") > 0


def test_a_purge_is_final_and_its_records_are_immutable(conn, artifacts):
    version, sid = imported_and_published(conn, artifacts)
    apply(conn, artifacts)
    for sql in (
        "UPDATE research_document_version SET purged_at = NULL",
        "UPDATE research_purge SET note = 'x'",
        "DELETE FROM research_purge",
        "DELETE FROM research_purge_artifact",
        "UPDATE research_purge_artifact SET url = 'x'",
        "UPDATE research_purge_artifact SET outcome = 'file_missing'",
        f"INSERT INTO research_section(version_id, ordinal, text, char_start, char_end) VALUES ({version}, 9, 't', 0, 1)",
    ):
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute(sql)
    with pytest.raises(ss.PublicationError):
        ss.record_publication(conn, sid, decision="publish", approver="A", note="n", now=NOW)


def test_redaction_is_possible_only_for_a_purged_version_and_only_to_placeholders(conn, artifacts):
    version, sid = imported_and_published(conn, artifacts)
    other = seed_version(conn, key="example", doc="crawled")
    other_sid = store_summary(conn, other, publish=False)
    for sql in (
        f"UPDATE research_summary SET raw_output = NULL WHERE id = {other_sid}",
        f"UPDATE research_summary SET output_json = '{{\"redacted\":true}}' WHERE id = {other_sid}",
        f"DELETE FROM research_forecast_claim WHERE summary_id = {other_sid}",
        # not even for a version about to be purged, until it is
        f"UPDATE research_summary SET raw_output = NULL WHERE id = {sid}",
    ):
        with pytest.raises(sqlite3.DatabaseError, match="immutable"):
            conn.execute(sql)
    apply(conn, artifacts)
    with pytest.raises(
        sqlite3.DatabaseError, match="immutable"
    ):  # arbitrary new content is still refused
        conn.execute(
            "UPDATE research_summary SET raw_output = NULL, output_json = '{}' WHERE id = ?", (sid,)
        )
    with pytest.raises(
        sqlite3.DatabaseError, match="immutable"
    ):  # and so is changing any other fact
        conn.execute(
            "UPDATE research_summary SET raw_output = NULL, status = 'provider_error' WHERE id = ?",
            (sid,),
        )


def test_a_failure_in_the_database_step_changes_nothing(conn, artifacts, monkeypatch):
    version, sid = imported_and_published(conn, artifacts)

    def boom(*a, **kw):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(purge, "_redact_summaries", boom)
    before = (count(conn, "research_section"), count(conn, "raw_artifact"), raw_files(artifacts))
    with pytest.raises(sqlite3.OperationalError):
        apply(conn, artifacts)
    assert (
        count(conn, "research_section"),
        count(conn, "raw_artifact"),
        raw_files(artifacts),
    ) == before
    assert count(conn, "research_purge") == 0
    assert (
        conn.execute(
            "SELECT purged_at FROM research_document_version WHERE id=?", (version,)
        ).fetchone()[0]
        is None
    )


# --- the file step is resumable -----------------------------------------------------------------------------------


def test_a_crash_between_the_steps_leaves_a_pending_purge_that_finishes_idempotently(
    conn, artifacts, monkeypatch
):
    version, sid = imported_and_published(conn, artifacts)
    real = ArtifactStore.remove
    monkeypatch.setattr(
        ArtifactStore, "remove", lambda self, rel: (_ for _ in ()).throw(OSError("EIO"))
    )
    result = apply(conn, artifacts)
    # The content is already unavailable; the file and its row remain, listed as pending.
    assert result.pending == 1 and result.artifacts_removed == 0
    assert count(conn, "research_section") == 0 and public_summaries(conn, REG) == []
    assert count(conn, "raw_artifact") == 1 and len(raw_files(artifacts)) == 1
    assert purge.pending_artifacts(conn) and purge.integrity_problems(conn, artifacts)
    monkeypatch.setattr(ArtifactStore, "remove", real)
    done = purge.finish_pending(conn, artifacts, now=NOW)
    assert done == 1 and raw_files(artifacts) == [] and count(conn, "raw_artifact") == 0
    assert purge.pending_artifacts(conn) == [] and purge.integrity_problems(conn, artifacts) == []
    assert purge.finish_pending(conn, artifacts, now=NOW) == 0  # nothing left; safe to repeat


def test_a_file_already_missing_is_recorded_not_an_error(conn, artifacts):
    imported_and_published(conn, artifacts)
    (raw_files(artifacts)[0]).unlink()
    result = apply(conn, artifacts)
    assert result.pending == 0
    assert (
        conn.execute("SELECT outcome FROM research_purge_artifact").fetchone()[0] == "file_missing"
    )


def test_a_file_shared_by_another_record_is_kept_until_the_last_one_goes(conn, artifacts):
    imported_and_published(conn, artifacts)
    (path,) = raw_files(artifacts)
    sha = path.name
    conn.execute("INSERT INTO raw_artifact(url, sha256, fetched_at, http_status, content_type, size_bytes, path)"
                 " VALUES ('https://elsewhere.example/other', ?, '2026-10-28T00:00:00Z', 200, 'text/html', 1, ?)",
                 (sha, f"{sha[:2]}/{sha}"))  # fmt: skip
    apply(conn, artifacts)
    assert path.exists(), "a file another record still points at was deleted"
    assert (
        conn.execute("SELECT outcome FROM research_purge_artifact").fetchone()[0]
        == "file_kept_shared"
    )
    assert count(conn, "raw_artifact") == 1


def test_a_tampered_path_is_never_followed_outside_the_raw_directory(conn, artifacts, tmp_path):
    imported_and_published(conn, artifacts)
    victim = tmp_path / "precious.txt"
    victim.write_text("keep me")
    conn.execute("UPDATE raw_artifact SET path = ?", ("../precious.txt",))
    result = apply(conn, artifacts)
    assert victim.read_text() == "keep me"
    assert (
        conn.execute("SELECT outcome FROM research_purge_artifact").fetchone()[0] == "unsafe_path"
    )
    assert result.pending == 0


def test_unlinked_byte_variants_of_the_document_are_purged_too(conn, artifacts):
    """The crawler keeps each fetch's bytes even when the text is unchanged; those copies are source content as well."""
    from nzstats.sources.fetcher import FetchResult

    imported_and_published(conn, artifacts)
    variant = artifacts.save(
        FetchResult(URL, 200, "text/html", html(PARA * 8 + "<!-- build 2 -->"), NOW)
    )
    with transaction(conn):
        from nzstats.store.repo import record_artifact

        record_artifact(conn, variant)
    assert len(raw_files(artifacts)) == 2
    result = apply(conn, artifacts)
    assert (
        result.artifacts_removed == 2
        and raw_files(artifacts) == []
        and count(conn, "raw_artifact") == 0
    )


def test_another_documents_files_are_not_touched(conn, artifacts):
    imported_and_published(conn, artifacts)
    do_import(conn, artifacts, html(PARA * 9), url=f"{BASE}/research/other-report")
    keep = conn.execute(
        "SELECT v.id FROM research_document_version v JOIN research_publication p ON"
        " p.id = v.publication_id WHERE p.canonical_url LIKE '%other-report'"
    ).fetchone()[0]
    p = purge.plan_purge(conn, "example", version_ids=(1,))
    purge.apply_purge(conn, p, artifacts, reason="takedown", purged_by="Owner", note="n", now=NOW)
    assert (
        len(raw_files(artifacts)) == 1 and count(conn, "research_section", f"version_id={keep}") > 0
    )


# --- no way back in -----------------------------------------------------------------------------------------------


def test_purged_text_cannot_be_imported_again_but_other_text_can(conn, artifacts):
    imported_and_published(conn, artifacts)
    apply(conn, artifacts)
    for url in (URL, f"{BASE}/research/same-text-new-address"):
        with pytest.raises(ImportRefused, match="purged"):
            do_import(conn, artifacts, url=url)
    assert raw_files(artifacts) == [] and count(conn, "research_section") == 0
    ok = do_import(
        conn, artifacts, html(PARA * 10)
    )  # a revised document at the same address is a new text
    assert ok.outcome == "updated"


def test_a_purged_version_is_not_offered_for_summarising(conn, artifacts):
    from nzstats.research.summarise import eligible_versions

    version, _ = imported_and_published(conn, artifacts)
    apply(conn, artifacts)
    found, refusals = eligible_versions(conn, REG, hosted=False, version_ids=(version,))
    assert found == [] and refusals and "purged" in refusals[0][1]
    found, _ = eligible_versions(conn, REG, hosted=False)
    assert found == []


# --- orphans ------------------------------------------------------------------------------------------------------


def test_a_duplicate_import_leaves_no_unreferenced_file(conn, artifacts):
    do_import(conn, artifacts)
    do_import(conn, artifacts, url=f"{BASE}/research/mirror")  # same text at another address
    assert (
        len(raw_files(artifacts)) == 1
        and purge.find_orphan_files(conn, artifacts, older_than_seconds=0) == []
    )


def test_an_import_whose_transaction_fails_leaves_no_file(conn, artifacts, monkeypatch):
    def boom(*a, **kw):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(store, "add_version", boom)
    with pytest.raises(sqlite3.OperationalError):
        do_import(conn, artifacts)
    assert raw_files(artifacts) == [] and count(conn, "raw_artifact") == 0


def test_re_importing_the_same_text_with_different_bytes_keeps_no_unlinked_copy(conn, artifacts):
    first = do_import(conn, artifacts)
    again = do_import(
        conn, artifacts, html(PARA * 8).replace(b"</body>", b"<!-- saved again --></body>")
    )
    assert again.outcome == "unchanged" and again.version_id == first.version_id
    assert len(raw_files(artifacts)) == 1 and count(conn, "raw_artifact") == 1
    assert purge.find_orphan_files(conn, artifacts, older_than_seconds=0) == []


def test_a_file_without_a_record_is_an_orphan_once_old_enough_and_can_be_swept(conn, artifacts):
    do_import(conn, artifacts)
    stray = artifacts.root / "ab" / ("ab" + "0" * 62)
    stray.parent.mkdir(parents=True)
    stray.write_bytes(b"left by a crash")
    young = purge.find_orphan_files(conn, artifacts, older_than_seconds=3600)
    assert young == [], "a file this young may belong to an import still in progress"
    old = time.time() - 7200
    os.utime(stray, (old, old))
    assert purge.find_orphan_files(conn, artifacts, older_than_seconds=3600) == [stray]
    assert purge.remove_orphan_files(conn, artifacts, older_than_seconds=3600) == 1
    assert not stray.exists() and len(raw_files(artifacts)) == 1  # the referenced file stays


def test_the_integrity_check_reports_missing_files_and_unfinished_purges(conn, artifacts):
    imported_and_published(conn, artifacts)
    assert purge.integrity_problems(conn, artifacts) == []
    raw_files(artifacts)[0].unlink()
    assert any("missing" in p for p in purge.integrity_problems(conn, artifacts))


def test_a_stats_nz_style_artifact_is_never_treated_as_research(conn, artifacts):
    from nzstats.sources.fetcher import FetchResult
    from nzstats.store.repo import record_artifact

    rec = artifacts.save(
        FetchResult("https://www.stats.govt.nz/x.csv", 200, "text/csv", b"a,b\n1,2\n", NOW)
    )
    with transaction(conn):
        record_artifact(conn, rec)
    imported_and_published(conn, artifacts)
    apply(conn, artifacts)
    assert [p.name for p in raw_files(artifacts)] == [hashlib.sha256(b"a,b\n1,2\n").hexdigest()]
    assert count(conn, "raw_artifact") == 1
    assert purge.find_orphan_files(conn, artifacts, older_than_seconds=0) == []


# --- health -------------------------------------------------------------------------------------------------------


def test_health_flags_an_unfinished_purge_and_does_not_mistake_a_purged_version_for_a_poor_extraction(
    conn, artifacts, monkeypatch
):
    from nzstats.research.contract import LlmLimits
    from nzstats.research.health import research_health

    imported_and_published(conn, artifacts)
    monkeypatch.setattr(
        ArtifactStore, "remove", lambda self, rel: (_ for _ in ()).throw(OSError("EIO"))
    )
    apply(conn, artifacts)
    report = research_health(conn, REG, now=NOW, limits=LlmLimits(), env={}, artifacts=artifacts)
    codes = {f.code for f in [*report.findings, *report.source("example").findings]}
    assert "purge_incomplete" in codes and "poor_extraction" not in codes and report.needs_attention
    assert report.source("example").unsummarised == 0
    assert (
        "published_but_withheld" not in codes
    )  # the purge withdrew it, so nothing is published but hidden
    monkeypatch.undo()
    purge.finish_pending(conn, artifacts, now=NOW)
    clean = research_health(conn, REG, now=NOW, limits=LlmLimits(), env={}, artifacts=artifacts)
    assert "purge_incomplete" not in {f.code for f in clean.findings}
