from datetime import UTC, datetime

from nzstats.insights.overview import build_overview
from tests.macro_support import ingest_gdp, ingest_labour

NOW = datetime(2026, 10, 28, tzinfo=UTC)
SLUGS = {"gross-domestic-product", "labour-market-statistics"}


def inactive(o):
    return [c.name for c in o.inactive_categories]


def test_categories_stay_inactive_until_data_is_stored(rt):
    o = build_overview(rt.conn, analysable_slugs=SLUGS, now=NOW)
    assert {"Economic growth", "Labour market"} <= set(inactive(o))
    assert not [k for k in o.kpis if k.metric.series_key.startswith(("gdp.", "hlfs."))]


def test_gdp_and_unemployment_kpis_appear_once_ingested(rt, site):
    ingest_gdp(rt, site, "2026-06")
    ingest_labour(rt, site, "2026-06")
    o = build_overview(rt.conn, analysable_slugs=SLUGS, now=NOW)
    kpis = {k.metric.series_key: k for k in o.kpis}
    assert kpis["gdp.production.cv.sa.pct_qoq"].metric.value == 0.2
    assert kpis["hlfs.rate.unemployment.sa"].metric.value == 5.6
    assert kpis["gdp.production.cv.sa.pct_qoq"].published_at.startswith("2026-09-17")
    assert "Economic growth" not in inactive(o) and "Labour market" not in inactive(o)
