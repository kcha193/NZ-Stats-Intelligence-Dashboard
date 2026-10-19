import pytest

from nzstats.pipeline.ingest import ingest_release
from nzstats.store import repo
from tests.cpi_support import NOW, seed_cpi

CORE = "cpi.index.nsa.all_groups"


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
