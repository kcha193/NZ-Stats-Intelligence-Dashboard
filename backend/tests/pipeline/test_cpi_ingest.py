from datetime import UTC, datetime, timedelta

import pytest

from nzstats.clock import to_akl_iso
from nzstats.insights.cpi import build_cpi_dashboard
from nzstats.pipeline.ingest import ingest_release
from nzstats.store import repo
from tests.cpi_support import NOW, XLSX, ingest_cpi, seed_cpi, workbook_with_cell

CORE = "cpi.index.nsa.all_groups"
MEDIAN = 0.4  # official weighted median, quarter ended June 2026


def counts(rt):
    tables = ("series", "vintage", "observation", "vintage_series_definition")
    return {t: rt.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}


def ingest(rt, key):
    return ingest_release(rt, key, now_fn=lambda: NOW)


def test_cpi_registered_ingests_once_and_is_idempotent(rt, site):
    assert "consumers-price-index" in rt.adapters
    rid, key, _, _ = seed_cpi(rt, site)
    outcome = ingest(rt, key)
    assert outcome.outcome == "ingested", outcome.detail
    assert repo.get_release(rt.conn, key)["status"] == "published"
    assert len(site.requests) == 5  # release page, three required CSVs and the optional workbook
    first = counts(rt)
    assert first["vintage"] >= 22 + 3 + 11  # contributions, headline, groups
    assert repo.latest_points(rt.conn, CORE)["2026-06"].value == 1359.0
    assert repo.latest_points(rt.conn, "cpi.contrib.q.transport")["2026-06"].value == 0.824
    assert ingest(rt, key).outcome == "unchanged"
    assert counts(rt) == first
    assert rt.conn.execute("SELECT COUNT(*) FROM raw_artifact").fetchone()[0] == 5


def test_march_then_june_keep_distinct_vintages_and_report_sa_revisions(rt, site):
    _, march, _, _ = seed_cpi(rt, site, "2026-03")
    assert ingest(rt, march).outcome == "ingested"
    _, june, _, _ = seed_cpi(rt, site, "2026-06")
    outcome = ingest(rt, june)
    assert outcome.outcome == "ingested", outcome.detail
    assert any("cpi.index.sa.all_groups" in w for w in outcome.warnings)  # genuine SA revisions
    assert not any(
        "cpi.index.nsa.all_groups" in w for w in outcome.warnings
    )  # unadjusted never revised
    vintages = repo.list_vintages(rt.conn, CORE)
    assert [v.release_key for v in vintages] == [march, june]
    assert max(repo.vintage_points(rt.conn, vintages[0].vintage_id)) == "2026-03"
    assert max(repo.vintage_points(rt.conn, vintages[1].vintage_id)) == "2026-06"
    assert len(repo.list_vintages(rt.conn, "cpi.contrib.q.transport")) == 2


def _page_without_tradables_link(page_html: bytes) -> bytes:
    return page_html.replace(b"-tradeables-and-non-tradeables.csv", b"-something-else.csv")


@pytest.mark.parametrize(
    ("mutate", "error_class"),
    [
        ("link", "layout_changed"),
        ("header", "layout_changed"),
        ("missing_latest", "validation_failed"),
        ("rebased", "validation_failed"),
        ("inconsistent_level", "validation_failed"),
    ],
)
def test_failed_ingestion_changes_nothing_and_keeps_last_known_good(rt, site, mutate, error_class):
    _, march, _, _ = seed_cpi(rt, site, "2026-03")
    assert ingest(rt, march).outcome == "ingested"
    before = counts(rt)
    _, june, page_url, downloads = seed_cpi(rt, site, "2026-06")
    index_url, tradables_url = downloads["cpi_index_numbers"], downloads["cpi_tradables"]
    index = site.routes[index_url][1].decode()
    row = '"CPIQ.SE9A","2026.06","1359"'
    if mutate == "link":
        status, body, ctype = site.routes[page_url]
        site.routes[page_url] = (status, _page_without_tradables_link(body), ctype)
    elif mutate == "header":
        site.override(
            index_url, body=index.replace('"STATUS"', '"Status"').encode(), ctype="text/csv"
        )
    elif mutate == "missing_latest":
        lines = [ln for ln in index.splitlines() if not ln.startswith(row)]
        site.override(index_url, body="\n".join(lines).encode(), ctype="text/csv")
    elif mutate == "rebased":
        site.override(
            index_url,
            body=index.replace(
                '"CPIQ.SE907","2017.06","1000"', '"CPIQ.SE907","2017.06","1001"'
            ).encode(),
            ctype="text/csv",
        )
    else:
        for url in (index_url, tradables_url):
            text = site.routes[url][1].decode().replace(row, '"CPIQ.SE9A","2026.06","1400"')
            site.override(url, body=text.encode(), ctype="text/csv")
    outcome = ingest(rt, june)
    assert outcome.outcome == "failed" and outcome.error_class.value == error_class
    assert "Traceback" not in (outcome.detail or "") and ".py" not in (outcome.detail or "")
    assert counts(rt) == before
    assert repo.get_release(rt.conn, june)["status"] == "published"  # calendar status unchanged
    assert max(repo.latest_points(rt.conn, CORE)) == "2026-03"  # March data still the latest
    assert (
        rt.conn.execute(
            "SELECT state FROM source_health WHERE source='release:consumers-price-index'"
        ).fetchone()[0]
        == "degraded"
    )


def test_workbook_adds_underlying_measures_and_its_absence_only_warns(rt, site):
    _, june, _, _ = seed_cpi(rt, site)
    assert ingest(rt, june).outcome == "ingested"
    assert repo.latest_points(rt.conn, "cpi.underlying.median")["2026-06"].value is not None
    _, march, _, downloads = seed_cpi(
        rt, site, "2026-03"
    )  # no workbook fixture is served for March
    outcome = ingest(rt, march)
    assert outcome.outcome == "ingested", outcome.detail
    assert any("underlying" in w for w in outcome.warnings)


def test_a_blocked_workbook_request_fails_the_ingestion(rt, site):
    _, june, _, downloads = seed_cpi(rt, site)
    site.override(downloads["cpi_workbook"], 200, b"<html>Incapsula incident</html>", "text/html")
    outcome = ingest(rt, june)
    assert outcome.outcome == "failed" and outcome.error_class.value == "blocked"
    assert counts(rt)["vintage"] == 0


def test_a_flaky_optional_workbook_never_creates_a_correction(rt, site):
    _, june, _, downloads = seed_cpi(rt, site)
    assert ingest(rt, june).outcome == "ingested"
    first = counts(rt)
    site.override(downloads["cpi_workbook"], 503, b"", "text/html")  # transient failure
    outcome = ingest(rt, june)
    assert outcome.outcome == "unchanged" and any("underlying" in w for w in outcome.warnings)
    assert counts(rt) == first
    assert repo.get_release(rt.conn, june)["status"] == "published"  # not "corrected"
    assert repo.latest_points(rt.conn, "cpi.underlying.median")  # the stored measures survive


def test_a_real_correction_still_lands_when_the_workbook_is_unavailable(rt, site):
    _, june, _, downloads = seed_cpi(rt, site)
    assert ingest(rt, june).outcome == "ingested"
    site.override(downloads["cpi_workbook"], 503, b"", "text/html")
    index_url = downloads["cpi_index_numbers"]
    text = (
        site.routes[index_url][1]
        .decode()
        .replace('"CPIQ.SE9011","2026.06"', '"CPIQ.SE9011","2026.06"', 1)
    )
    row = next(line for line in text.splitlines() if line.startswith('"CPIQ.SE9013","2026.06"'))
    value = row.split(",")[2]
    site.override(
        index_url, body=text.replace(row, row.replace(value, '"1387.5"')).encode(), ctype="text/csv"
    )
    outcome = ingest(rt, june)
    assert (
        outcome.outcome == "ingested" and repo.get_release(rt.conn, june)["status"] == "corrected"
    )


# --- optional-workbook recovery, loss and corrections (review #4312128553, #4312128556) ----------

UNDERLYING = "cpi.underlying."
BROKEN = {
    "http_503": lambda: (503, b"", "text/html"),
    "nan_cell": lambda: (200, workbook_with_cell("NaN"), XLSX),
    "inf_cell": lambda: (200, workbook_with_cell("inf"), XLSX),
    "junk": lambda: (200, b"junk", XLSX),
}


def vintage_counts(rt, release_id):
    rows = rt.conn.execute(
        "SELECT s.key, COUNT(*) FROM vintage v JOIN series s ON s.id = v.series_id"
        " WHERE v.release_id = ? GROUP BY s.key",
        (release_id,),
    ).fetchall()
    return {key: n for key, n in rows}


def core_values(rt, release_id):
    """Latest values of every required (non-optional) series: the statistics Stats NZ published."""
    keys = [k for k in vintage_counts(rt, release_id) if not k.startswith(UNDERLYING)]
    return {k: {p: pt.value for p, pt in repo.latest_points(rt.conn, k).items()} for k in keys}


def underlying(counts):
    return {k: n for k, n in counts.items() if k.startswith(UNDERLYING)}


def assert_core_unduplicated(counts, expected=1):
    assert {n for k, n in counts.items() if not k.startswith(UNDERLYING)} == {expected}


def corrected_index(site, downloads):
    """A genuine official correction: one required index value differs."""
    url = downloads["cpi_index_numbers"]
    text = site.routes[url][1].decode()
    row = next(ln for ln in text.splitlines() if ln.startswith('"CPIQ.SE9013","2026.06"'))
    value = row.split(",")[2]
    return (200, text.replace(row, row.replace(value, '"1387.5"')).encode(), "text/csv")


@pytest.mark.parametrize("broken", BROKEN)
def test_workbook_arriving_later_enriches_without_a_false_correction(rt, site, broken):
    rid, june, _, downloads = seed_cpi(rt, site)
    url = downloads["cpi_workbook"]
    good = site.routes[url]
    site.routes[url] = BROKEN[broken]()
    assert ingest(rt, june).outcome == "ingested"
    assert not underlying(vintage_counts(rt, rid))
    core, bundle = core_values(rt, rid), repo.release_bundle(rt.conn, rid)

    site.routes[url] = good  # the safe repeat/backfill finds the workbook
    outcome = ingest(rt, june)
    counts = vintage_counts(rt, rid)
    assert outcome.outcome == "ingested", outcome.detail
    assert repo.get_release(rt.conn, june)["status"] == "published"  # nothing was corrected
    assert_core_unduplicated(counts)
    assert len(underlying(counts)) == 11 and set(underlying(counts).values()) == {1}
    assert core_values(rt, rid) == core  # required statistics untouched
    assert repo.release_bundle(rt.conn, rid) == bundle  # one bundle: no new publication snapshot
    active = repo.release_bundle(rt.conn, rid)
    assert {d.key for d, _ in repo.bundle_series(rt.conn, rid, active)} >= set(underlying(counts))
    assert repo.latest_points(rt.conn, "cpi.underlying.median")["2026-06"].value == MEDIAN
    superseded = [
        repo.vintage_superseded(rt.conn, v.vintage_id)
        for k in counts
        for v in repo.list_vintages(rt.conn, k)
    ]
    assert not any(superseded)

    before = counts_all = counts_of(rt)
    assert ingest(rt, june).outcome == "unchanged"  # idempotent
    assert counts_of(rt) == before == counts_all

    site.routes[url] = BROKEN[broken]()  # and the recovered measures survive a later failure
    outcome = ingest(rt, june)
    assert outcome.outcome == "unchanged"
    # The enriched bundle keeps its required-only identity, so this repeat takes the digest fast
    # path: it must still report the optional failure instead of recording a clean success.
    assert any("underlying" in w for w in outcome.warnings)
    detail = rt.conn.execute(
        "SELECT detail FROM ingest_run WHERE release_key=? ORDER BY id DESC LIMIT 1", (june,)
    ).fetchone()[0]
    assert "warnings:" in detail and "underlying" in detail
    assert counts_of(rt) == before
    assert repo.get_release(rt.conn, june)["status"] == "published"
    assert repo.latest_points(rt.conn, "cpi.underlying.median")["2026-06"].value == MEDIAN


def counts_of(rt):
    return counts(rt)


@pytest.mark.parametrize("broken", BROKEN)
def test_a_bad_optional_workbook_never_corrects_or_removes_stored_measures(rt, site, broken):
    rid, june, _, downloads = seed_cpi(rt, site)
    url = downloads["cpi_workbook"]
    assert ingest(rt, june).outcome == "ingested"
    before, core = counts(rt), core_values(rt, rid)
    site.routes[url] = BROKEN[broken]()
    outcome = ingest(rt, june)
    assert outcome.outcome == "unchanged" and any("underlying" in w for w in outcome.warnings)
    assert counts(rt) == before and core_values(rt, rid) == core
    assert repo.get_release(rt.conn, june)["status"] == "published"
    assert repo.latest_points(rt.conn, "cpi.underlying.median")["2026-06"].value == MEDIAN


@pytest.mark.parametrize("broken", ["nan_cell", "junk"])
def test_a_bad_workbook_never_blocks_the_first_ingestion(rt, site, broken):
    rid, june, _, downloads = seed_cpi(rt, site)
    site.routes[downloads["cpi_workbook"]] = BROKEN[broken]()
    outcome = ingest(rt, june)
    assert outcome.outcome == "ingested", outcome.detail
    assert any("underlying" in w for w in outcome.warnings)
    assert repo.latest_points(rt.conn, CORE)["2026-06"].value == 1359.0
    assert not underlying(vintage_counts(rt, rid))


def test_a_true_correction_with_the_workbook_present_keeps_the_full_history(rt, site):
    rid, june, _, downloads = seed_cpi(rt, site)
    index_url = downloads["cpi_index_numbers"]
    original = site.routes[index_url]
    assert ingest(rt, june).outcome == "ingested"
    first_bundle = repo.release_bundle(rt.conn, rid)
    site.routes[index_url] = corrected_index(site, downloads)
    assert ingest(rt, june).outcome == "ingested"
    assert repo.get_release(rt.conn, june)["status"] == "corrected"
    assert set(vintage_counts(rt, rid).values()) == {2}  # every series snapshotted per bundle
    corrected_bundle = repo.release_bundle(rt.conn, rid)
    assert corrected_bundle != first_bundle
    assert ingest(rt, june).outcome == "unchanged"

    site.routes[index_url] = original  # the correction is reverted: reactivate, never duplicate
    assert ingest(rt, june).outcome == "ingested"
    assert repo.release_bundle(rt.conn, rid) == first_bundle
    assert set(vintage_counts(rt, rid).values()) == {2}
    assert repo.latest_points(rt.conn, "cpi.underlying.median")["2026-06"].value == MEDIAN
    assert ingest(rt, june).outcome == "unchanged"


def test_enrichment_after_a_true_correction_does_not_duplicate_or_recorrect(rt, site):
    rid, june, _, downloads = seed_cpi(rt, site)
    url, index_url = downloads["cpi_workbook"], downloads["cpi_index_numbers"]
    good = site.routes[url]
    site.routes[url] = BROKEN["http_503"]()
    assert ingest(rt, june).outcome == "ingested"
    site.routes[index_url] = corrected_index(site, downloads)
    assert ingest(rt, june).outcome == "ingested"
    assert repo.get_release(rt.conn, june)["status"] == "corrected"
    corrected_bundle, core = repo.release_bundle(rt.conn, rid), core_values(rt, rid)

    site.routes[url] = good  # the workbook finally arrives for the corrected release
    assert ingest(rt, june).outcome == "ingested"
    counts_ = vintage_counts(rt, rid)
    assert_core_unduplicated(counts_, 2)  # original + correction, nothing more
    assert set(underlying(counts_).values()) == {1}
    assert repo.get_release(rt.conn, june)["status"] == "corrected"
    assert repo.release_bundle(rt.conn, rid) == corrected_bundle
    assert core_values(rt, rid) == core
    assert ingest(rt, june).outcome == "unchanged"


def test_reverting_a_correction_enriches_the_original_bundle_in_place(rt, site):
    rid, june, _, downloads = seed_cpi(rt, site)
    url, index_url = downloads["cpi_workbook"], downloads["cpi_index_numbers"]
    good, original = site.routes[url], site.routes[index_url]
    site.routes[url] = BROKEN["http_503"]()
    assert ingest(rt, june).outcome == "ingested"
    first_bundle, first_core = repo.release_bundle(rt.conn, rid), core_values(rt, rid)
    site.routes[index_url] = corrected_index(site, downloads)
    assert ingest(rt, june).outcome == "ingested"

    site.routes[index_url], site.routes[url] = original, good  # reverted, and workbook present
    assert ingest(rt, june).outcome == "ingested"
    counts_ = vintage_counts(rt, rid)
    assert_core_unduplicated(counts_, 2)
    assert set(underlying(counts_).values()) == {1}
    assert repo.release_bundle(rt.conn, rid) == first_bundle
    assert core_values(rt, rid) == first_core
    assert repo.latest_points(rt.conn, "cpi.underlying.median")["2026-06"].value == MEDIAN
    assert ingest(rt, june).outcome == "unchanged"


def test_a_revision_to_published_optional_measures_is_a_correction_of_the_whole_bundle(rt, site):
    """Explicit rule: changed official optional statistics are a new bundle, like any correction."""
    rid, june, _, downloads = seed_cpi(rt, site)
    url = downloads["cpi_workbook"]
    good = site.routes[url]
    assert ingest(rt, june).outcome == "ingested"
    core = core_values(rt, rid)
    site.routes[url] = (200, workbook_with_cell("1.1"), XLSX)  # Stats NZ revised the median
    assert ingest(rt, june).outcome == "ingested"
    assert repo.get_release(rt.conn, june)["status"] == "corrected"
    assert set(vintage_counts(rt, rid).values()) == {2}
    assert core_values(rt, rid) == core
    assert repo.latest_points(rt.conn, "cpi.underlying.median")["2026-06"].value == 1.1
    first = repo.list_vintages(rt.conn, "cpi.underlying.median")[0]
    assert repo.vintage_points(rt.conn, first.vintage_id)["2026-06"].value == MEDIAN  # kept
    site.routes[url] = good
    assert ingest(rt, june).outcome == "ingested"
    assert repo.latest_points(rt.conn, "cpi.underlying.median")["2026-06"].value == MEDIAN
    assert set(vintage_counts(rt, rid).values()) == {2}
    assert ingest(rt, june).outcome == "unchanged"


def test_a_concurrent_enrichment_is_not_applied_twice(rt, site, monkeypatch):
    import contextlib

    import nzstats.pipeline.ingest as ingest_module

    rid, june, _, downloads = seed_cpi(rt, site)
    url = downloads["cpi_workbook"]
    good = site.routes[url]
    site.routes[url] = BROKEN["http_503"]()
    assert ingest(rt, june).outcome == "ingested"
    site.routes[url] = good
    real, raced = ingest_module.transaction, []

    @contextlib.contextmanager
    def other_process_commits_first(conn):
        if not raced:
            raced.append(None)  # claim the slot first: the rival itself passes through here
            raced[0] = ingest(rt, june)  # the rival enriches and commits before we lock
        with real(conn) as c:
            yield c

    monkeypatch.setattr(ingest_module, "transaction", other_process_commits_first)
    outcome = ingest(rt, june)
    assert raced[0].outcome == "ingested" and outcome.outcome == "unchanged"
    counts_ = vintage_counts(rt, rid)
    assert_core_unduplicated(counts_) and set(underlying(counts_).values()) == {1}
    assert repo.get_release(rt.conn, june)["status"] == "published"


def test_a_release_that_never_had_the_workbook_keeps_reporting_it_is_missing(rt, site):
    _, june, _, downloads = seed_cpi(rt, site)
    site.routes[downloads["cpi_workbook"]] = BROKEN["http_503"]()
    assert ingest(rt, june).outcome == "ingested"
    repeat = ingest(rt, june)
    assert repeat.outcome == "unchanged" and any("underlying" in w for w in repeat.warnings)


# --- validation warnings survive unchanged repeats (review #4334641065) --------------------------


def _without_contribution_charts(site, page_url):
    status, body, ctype = site.routes[page_url]
    assert b"percentage point contribution" in body
    site.routes[page_url] = (status, body.replace(b"percentage point contribution", b"pp x"), ctype)


def _last_detail(rt, key):
    return rt.conn.execute(
        "SELECT detail FROM ingest_run WHERE release_key=? ORDER BY id DESC LIMIT 1", (key,)
    ).fetchone()[0]


def test_absent_contribution_charts_keep_warning_on_unchanged_repeats(rt, site):
    rid, june, page_url, _ = seed_cpi(rt, site)
    _without_contribution_charts(site, page_url)
    first = ingest(rt, june)
    assert first.outcome == "ingested", first.detail
    note = "quarterly contributions were not published in this release"
    assert any(note in w for w in first.warnings)
    before, bundle = counts(rt), repo.release_bundle(rt.conn, rid)

    for _ in range(2):  # every repeat, not just the first
        repeat = ingest(rt, june)
        assert repeat.outcome == "unchanged"
        assert any(note in w for w in repeat.warnings)
        assert note in _last_detail(rt, june)
    assert counts(rt) == before and repo.release_bundle(rt.conn, rid) == bundle
    assert repo.get_release(rt.conn, june)["status"] == "published"


@pytest.mark.parametrize("month", ["2025-12", "2026-03", "2026-06"])
def test_an_unchanged_repeat_reports_the_warnings_of_the_ingest_that_stored_it(rt, site, month):
    ingest_cpi(rt, site, *(["2026-03"] if month == "2026-06" else []))
    _, key, _, _ = seed_cpi(rt, site, month)
    first = ingest(rt, key)
    assert first.outcome == "ingested" and first.warnings
    repeat = ingest(rt, key)
    assert repeat.outcome == "unchanged"
    # Same findings, same order, nothing hidden or doubled. "Historical revisions" is the one
    # event-like warning: a repeat compares the release with its own stored vintages, so it is
    # reported by the ingest that captured the revision and not again.
    persistent = tuple(w for w in first.warnings if "Historical revisions" not in w)
    assert repeat.warnings == persistent
    assert len(set(repeat.warnings)) == len(repeat.warnings)


def test_simultaneous_warnings_are_all_kept_and_not_duplicated_on_repeat(rt, site):
    _, june, page_url, downloads = seed_cpi(rt, site)
    _without_contribution_charts(site, page_url)
    site.routes[downloads["cpi_workbook"]] = BROKEN["http_503"]()  # optional input also missing
    first = ingest(rt, june)
    repeat = ingest(rt, june)
    assert repeat.outcome == "unchanged"
    text = " | ".join(repeat.warnings)
    assert "contributions were not published" in text  # validation warning
    assert "underlying" in text  # optional workbook warning
    assert "stale or discontinued" in text  # a second validation warning
    assert repeat.warnings == first.warnings
    assert len(set(repeat.warnings)) == len(repeat.warnings)


def test_validation_errors_still_block_an_unchanged_looking_release(rt, site):
    rid, june, _, downloads = seed_cpi(rt, site)
    assert ingest(rt, june).outcome == "ingested"
    before = counts(rt)
    index_url = downloads["cpi_index_numbers"]
    text = site.routes[index_url][1].decode()
    row = '"CPIQ.SE9A","2026.06","1359"'
    site.override(
        index_url,
        body="\n".join(ln for ln in text.splitlines() if not ln.startswith(row)).encode(),
        ctype="text/csv",
    )
    outcome = ingest(rt, june)
    assert outcome.outcome == "failed" and outcome.error_class.value == "validation_failed"
    assert counts(rt) == before


# --- active optional revisions survive a missing workbook (review #4343298257) -------------------
#
# Lineage under test: A required-only -> B workbook enriches A in place (A keeps its required-only
# digest) -> C workbook measures revised, a new full bundle -> D workbook gone -> E workbook back.
# D parses to exactly A's digest, so an exact-digest lookup would reactivate A and silently restore
# the pre-revision measures as a false correction.

T0 = datetime(2026, 10, 20, 9, tzinfo=UTC)
REVISED = 1.1
REVISED_AGAIN = 1.2


def at(rt, key, hours):
    return ingest_release(rt, key, now_fn=lambda: T0 + timedelta(hours=hours))


def ledger(rt):
    """Everything an ingest can write: every vintage's identity, capture time and activation."""
    return rt.conn.execute(
        "SELECT id, series_id, captured_at, bundle_sha256, activation FROM vintage ORDER BY id"
    ).fetchall()


def release_row(rt, key):
    return dict(repo.get_release(rt.conn, key))


def dashboard_median(rt):
    dash = build_cpi_dashboard(rt.conn)
    median = next(u for u in dash.underlying if u.key == "cpi.underlying.median")
    return {p.period: p.value for p in median.points}["2026-06"], dash.captured_at


def revised_workbook(value=REVISED):
    return (200, workbook_with_cell(str(value)), XLSX)


def lineage_to_c(rt, site):
    """A -> B -> C. Returns the release id/key, the workbook url and the original workbook route."""
    rid, june, _, downloads = seed_cpi(rt, site)
    url = downloads["cpi_workbook"]
    good = site.routes[url]
    site.routes[url] = BROKEN["http_503"]()
    assert at(rt, june, 0).outcome == "ingested"  # A: required-only
    bundle_a = repo.release_bundle(rt.conn, rid)
    site.routes[url] = good
    assert at(rt, june, 1).outcome == "ingested"  # B: workbook enriches A in place
    assert repo.release_bundle(rt.conn, rid) == bundle_a
    assert repo.get_release(rt.conn, june)["status"] == "published"
    site.routes[url] = revised_workbook()
    assert at(rt, june, 2).outcome == "ingested"  # C: revised measures, a new full bundle
    bundle_c = repo.release_bundle(rt.conn, rid)
    assert bundle_c != bundle_a and repo.get_release(rt.conn, june)["status"] == "corrected"
    return rid, june, url, good, bundle_a, bundle_c


def test_a_missing_workbook_keeps_the_active_revised_bundle(rt, site):
    rid, june, url, good, bundle_a, bundle_c = lineage_to_c(rt, site)
    revised = site.routes[url]
    snapshot_ledger, snapshot_row, snapshot_counts = ledger(rt), release_row(rt, june), counts(rt)
    assert dashboard_median(rt)[0] == REVISED

    site.routes[url] = BROKEN["http_503"]()  # D: the workbook is unavailable
    d = at(rt, june, 3)
    assert d.outcome == "unchanged", d.detail
    assert any("underlying" in w for w in d.warnings)  # the missing workbook is still reported
    assert "underlying" in _last_detail(rt, june)
    assert repo.release_bundle(rt.conn, rid) == bundle_c  # A was not reactivated
    assert ledger(rt) == snapshot_ledger  # no vintage, activation or capture time moved
    assert counts(rt) == snapshot_counts  # and no new core vintages
    assert release_row(rt, june) == snapshot_row  # status, headline and timestamps untouched
    assert repo.get_release(rt.conn, june)["status"] == "corrected"
    assert repo.latest_points(rt.conn, "cpi.underlying.median")["2026-06"].value == REVISED
    value, captured_at = dashboard_median(rt)
    assert value == REVISED  # last-known-good dashboard values
    assert captured_at == to_akl_iso(T0 + timedelta(hours=2))  # freshness is C's capture, not B's

    for hours in (4, 5):  # repeated failed ingests are idempotent
        again = at(rt, june, hours)
        assert again.outcome == "unchanged" and any("underlying" in w for w in again.warnings)
        assert ledger(rt) == snapshot_ledger

    site.routes[url] = revised  # E: the same revised workbook comes back
    assert at(rt, june, 6).outcome == "unchanged"
    assert ledger(rt) == snapshot_ledger and release_row(rt, june) == snapshot_row
    assert at(rt, june, 7).outcome == "unchanged"
    assert dashboard_median(rt)[0] == REVISED
    assert repo.release_bundle(rt.conn, rid) == bundle_c


@pytest.mark.parametrize("broken", BROKEN)
def test_every_kind_of_missing_or_invalid_workbook_keeps_the_revised_bundle(rt, site, broken):
    rid, june, url, _, _, bundle_c = lineage_to_c(rt, site)
    snapshot = ledger(rt)
    site.routes[url] = BROKEN[broken]()
    outcome = at(rt, june, 3)
    assert outcome.outcome == "unchanged" and any("underlying" in w for w in outcome.warnings)
    assert repo.release_bundle(rt.conn, rid) == bundle_c and ledger(rt) == snapshot
    assert repo.get_release(rt.conn, june)["status"] == "corrected"
    assert dashboard_median(rt)[0] == REVISED


def test_a_workbook_that_has_gone_missing_keeps_the_revised_bundle(rt, site):
    rid, june, url, _, _, bundle_c = lineage_to_c(rt, site)
    snapshot = ledger(rt)
    del site.routes[url]  # the link is still on the page but the file is gone: a 404
    outcome = at(rt, june, 3)
    assert outcome.outcome == "unchanged" and any("underlying" in w for w in outcome.warnings)
    assert repo.release_bundle(rt.conn, rid) == bundle_c and ledger(rt) == snapshot


def test_a_required_correction_while_the_workbook_is_missing_is_a_new_bundle(rt, site):
    rid, june, url, _, bundle_a, bundle_c = lineage_to_c(rt, site)
    revised = site.routes[url]
    site.routes[url] = BROKEN["http_503"]()
    index_url = downloads_of(site, "cpi_index_numbers")
    site.routes[index_url] = corrected_index(site, {"cpi_index_numbers": index_url})
    outcome = at(rt, june, 3)
    assert outcome.outcome == "ingested", outcome.detail
    assert repo.get_release(rt.conn, june)["status"] == "corrected"
    corrected = repo.release_bundle(rt.conn, rid)
    assert corrected not in (bundle_a, bundle_c)
    assert core_values(rt, rid)["cpi.index.nsa.all_groups"]  # the corrected statistics are active
    # Optional measures were reconciled against the earlier required statistics, so they are not
    # carried onto a bundle with different ones: the workbook must re-validate them when it
    # returns. What was published stays in the history.
    active = {d.key for d, _ in repo.bundle_series(rt.conn, rid, corrected)}
    assert not {k for k in active if k.startswith(UNDERLYING)}
    assert len(repo.list_vintages(rt.conn, "cpi.underlying.median")) == 2
    assert at(rt, june, 4).outcome == "unchanged"

    site.routes[url] = revised  # the workbook returns: it enriches the corrected bundle in place
    assert at(rt, june, 5).outcome == "ingested"
    assert repo.release_bundle(rt.conn, rid) == corrected
    assert repo.latest_points(rt.conn, "cpi.underlying.median")["2026-06"].value == REVISED
    assert at(rt, june, 6).outcome == "unchanged"


def downloads_of(site, kind):
    from nzstats.sources.release_page import classify_download

    return next(u for u in site.routes if classify_download(u) == kind)


def test_official_reversion_with_complete_data_restores_the_earlier_bundle(rt, site):
    rid, june, url, good, bundle_a, bundle_c = lineage_to_c(rt, site)
    site.routes[url] = good  # Stats NZ restores the original measures: complete evidence
    outcome = at(rt, june, 3)
    assert outcome.outcome == "ingested", outcome.detail
    assert repo.release_bundle(rt.conn, rid) == bundle_a
    assert repo.latest_points(rt.conn, "cpi.underlying.median")["2026-06"].value == MEDIAN
    assert dashboard_median(rt)[0] == MEDIAN
    assert at(rt, june, 4).outcome == "unchanged"
    assert set(underlying(vintage_counts(rt, rid)).values()) == {2}  # nothing duplicated


def test_required_reversion_without_a_workbook_restores_the_earlier_bundle(rt, site):
    rid, june, url, good, bundle_a, bundle_c = lineage_to_c(rt, site)
    index_url = downloads_of(site, "cpi_index_numbers")
    original = site.routes[index_url]
    site.routes[url] = BROKEN["http_503"]()
    site.routes[index_url] = corrected_index(site, {"cpi_index_numbers": index_url})
    assert at(rt, june, 3).outcome == "ingested"  # a required correction, workbook missing
    corrected = repo.release_bundle(rt.conn, rid)
    assert corrected not in (bundle_a, bundle_c)

    site.routes[index_url] = original  # the required statistics revert; workbook still missing
    outcome = at(rt, june, 4)
    assert outcome.outcome == "ingested", outcome.detail
    # The newest earlier bundle holding exactly these required statistics wins: C, which is the
    # latest validated optional state for them, not the older A.
    assert repo.release_bundle(rt.conn, rid) == bundle_c
    assert repo.latest_points(rt.conn, "cpi.underlying.median")["2026-06"].value == REVISED
    assert at(rt, june, 5).outcome == "unchanged"


def test_legacy_digest_labels_do_not_resurrect_an_older_bundle(rt, site):
    rid, june, url, _, bundle_a, bundle_c = lineage_to_c(rt, site)
    rt.conn.execute(
        "UPDATE vintage SET bundle_sha256='legacy-a' WHERE bundle_sha256=?", (bundle_a,)
    )
    rt.conn.execute(
        "UPDATE vintage SET bundle_sha256='legacy-c' WHERE bundle_sha256=?", (bundle_c,)
    )
    rt.conn.commit()
    snapshot = ledger(rt)
    site.routes[url] = BROKEN["http_503"]()
    outcome = at(rt, june, 3)
    assert outcome.outcome == "unchanged" and any("underlying" in w for w in outcome.warnings)
    assert repo.release_bundle(rt.conn, rid) == "legacy-c" and ledger(rt) == snapshot
    assert dashboard_median(rt)[0] == REVISED


def test_a_workbook_revised_by_a_rival_before_we_lock_is_not_rolled_back(rt, site, monkeypatch):
    import contextlib

    import nzstats.pipeline.ingest as ingest_module

    rid, june, url, _, bundle_a, bundle_c = lineage_to_c(rt, site)
    site.routes[url] = BROKEN["http_503"]()  # this process saw no workbook ...
    real, raced = ingest_module.transaction, []

    @contextlib.contextmanager
    def rival_publishes_first(conn):
        if not raced:
            raced.append(None)
            site.routes[url] = revised_workbook(REVISED_AGAIN)  # ... a rival saw a newer one
            raced[0] = at(rt, june, 3)
            site.routes[url] = BROKEN["http_503"]()
        with real(conn) as c:
            yield c

    monkeypatch.setattr(ingest_module, "transaction", rival_publishes_first)
    outcome = at(rt, june, 4)
    assert raced[0].outcome == "ingested" and outcome.outcome == "unchanged"
    newest = repo.release_bundle(rt.conn, rid)
    assert newest not in (bundle_a, bundle_c)  # the rival's bundle stays active
    assert repo.latest_points(rt.conn, "cpi.underlying.median")["2026-06"].value == REVISED_AGAIN
    assert dashboard_median(rt)[0] == REVISED_AGAIN
