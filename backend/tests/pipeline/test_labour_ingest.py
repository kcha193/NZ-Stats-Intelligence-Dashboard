from nzstats.store import repo
from tests.macro_support import ingest, ingest_labour, labour_files, seed

RATE = "hlfs.rate.unemployment.sa"


def counts(rt):
    tables = ("series", "vintage", "observation")
    return {t: rt.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}


def test_labour_market_is_registered_and_ingests_once(rt, site):
    assert "labour-market-statistics" in rt.adapters
    key = ingest_labour(rt, site, "2026-06")["2026-06"]
    assert len(site.requests) == 2  # release page and the zip
    assert repo.latest_points(rt.conn, RATE)["2026-06"].value == 5.6
    assert repo.latest_points(rt.conn, "lci.all_wages.pct_yoy")["2026-06"].value == 2.0
    first = counts(rt)
    assert first["vintage"] == 11
    assert ingest(rt, key).outcome == "unchanged"
    assert counts(rt) == first


def test_the_revised_march_release_then_june_keep_both_vintages(rt, site):
    keys = ingest_labour(rt, site, "2026-03")
    june = seed(rt, site, "labour_2026-06_page.html", labour_files("2026-06"))
    outcome = ingest(rt, june)
    assert outcome.outcome == "ingested", outcome.detail
    assert any(RATE in w for w in outcome.warnings)
    vintages = repo.list_vintages(rt.conn, RATE)
    assert [v.release_key for v in vintages] == [keys["2026-03"], june]
    first, latest = (repo.vintage_points(rt.conn, v.vintage_id)["2026-03"].value for v in vintages)
    assert (first, latest) == (5.3, 5.4)


def test_a_failed_release_keeps_the_last_known_good_vintage(rt, site):
    ingest_labour(rt, site, "2026-03")
    before = counts(rt)
    june = seed(rt, site, "labour_2026-06_page.html", {"labour_zip": b"not a zip"})
    outcome = ingest(rt, june)
    assert outcome.outcome == "failed"
    assert counts(rt) == before
    assert max(repo.latest_points(rt.conn, RATE)) == "2026-03"
