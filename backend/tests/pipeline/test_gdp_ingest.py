from nzstats.store import repo
from tests.macro_support import gdp_files, ingest, ingest_gdp, seed

HEADLINE = "gdp.production.cv.sa"
QOQ = "gdp.production.cv.sa.pct_qoq"


def counts(rt):
    tables = ("series", "vintage", "observation", "vintage_series_definition")
    return {t: rt.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}


def test_gdp_is_registered_and_ingests_once(rt, site):
    assert "gross-domestic-product" in rt.adapters
    key = ingest_gdp(rt, site, "2026-06")["2026-06"]
    assert len(site.requests) == 2  # release page and the one CSV
    assert repo.get_release(rt.conn, key)["status"] == "published"
    assert repo.latest_points(rt.conn, HEADLINE)["2026-06"].value == 71805
    assert repo.latest_points(rt.conn, QOQ)["2026-06"].value == 0.2
    first = counts(rt)
    assert first["vintage"] == 12
    assert ingest(rt, key).outcome == "unchanged"
    assert counts(rt) == first


def test_definitions_are_snapshotted_with_the_source_file(rt, site):
    ingest_gdp(rt, site, "2026-06")
    row = rt.conn.execute(
        "SELECT d.unit, d.seasonal_adjustment, d.source_url FROM vintage_series_definition d"
        " JOIN vintage v ON v.id = d.vintage_id JOIN series s ON s.id = v.series_id WHERE s.key = ?",
        (HEADLINE,),
    ).fetchone()
    assert row["unit"] == "NZD million (2009/10 prices)"
    assert row["source_url"].endswith("gross-domestic-product-june-2026-quarter.csv")


def test_march_then_june_keep_both_vintages_and_report_revisions(rt, site):
    keys = ingest_gdp(rt, site, "2026-03")
    june = seed(rt, site, "gdp_2026-06_page.html", gdp_files("2026-06"))
    outcome = ingest(rt, june)
    assert outcome.outcome == "ingested", outcome.detail
    assert any(QOQ in w for w in outcome.warnings)
    vintages = repo.list_vintages(rt.conn, QOQ)
    assert [v.release_key for v in vintages] == [keys["2026-03"], june]
    first, latest = (repo.vintage_points(rt.conn, v.vintage_id)["2026-03"].value for v in vintages)
    assert (first, latest) == (0.8, 0.9)


def test_a_failed_release_keeps_the_last_known_good_vintage(rt, site):
    ingest_gdp(rt, site, "2026-03")
    before = counts(rt)
    broken = gdp_files("2026-06")["gdp_csv"].replace(b"SNEQ.SG01RSC00B01,", b"SNEQ.SG01RSC00B0X,")
    june = seed(rt, site, "gdp_2026-06_page.html", {"gdp_csv": broken})
    outcome = ingest(rt, june)
    assert outcome.outcome == "failed"
    assert "coverage" in (outcome.detail or "")
    assert counts(rt) == before
    assert max(repo.latest_points(rt.conn, HEADLINE)) == "2026-03"


def test_a_missing_csv_is_not_available_and_stores_nothing(rt, site):
    june = seed(rt, site, "gdp_2026-06_page.html", {})
    site.routes = {
        u: r
        for u, r in site.routes.items()
        if not u.endswith("gross-domestic-product-june-2026-quarter.csv")
    }
    outcome = ingest(rt, june)
    assert outcome.outcome == "not_available"
    assert counts(rt)["vintage"] == 0
