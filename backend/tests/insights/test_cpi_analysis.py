import re

import pytest

from nzstats.insights.cpi import build_cpi_analysis, build_cpi_overview_kpi
from tests.cpi_support import ingest_cpi

FORECAST = re.compile(r"will (cut|raise|lower|increase)|expects?|forecast|reserve bank|official cash rate|interest rate", re.I)


def texts(insights):
    return {i.id: i.text for i in insights}


@pytest.fixture()
def analysis(rt, site):
    ids = ingest_cpi(rt, site, "2026-03", "2026-06")
    return build_cpi_analysis(rt.conn, ids["2026-06"])


def test_executive_summary_answers_the_release_questions_in_order(analysis):
    ids = [i.id for i in analysis.executive_summary]
    assert ids == ["headline", "quarter", "annual-vs-prior", "tradability", "drivers"]
    t = texts(analysis.executive_summary)
    assert "1.5%" in t["headline"] and "4.1%" in t["headline"] and "June 2026" in t["headline"]
    assert "0.9%" in t["quarter"] and "March 2026" in t["quarter"]
    assert "3.1%" in t["annual-vs-prior"] and "percentage point" in t["annual-vs-prior"]
    assert "4.9%" in t["tradability"] and "3.4%" in t["tradability"]
    assert "not published" in t["tradability"].lower()  # no tradable/non-tradable contributions exist
    assert "Transport" in t["drivers"] and "percentage points" in t["drivers"] and "0.82" in t["drivers"]
    assert all(i.evidence and i.kind == "observation" for i in analysis.executive_summary)
    assert all(e.release_key.startswith("consumers-price-index") for i in analysis.executive_summary for e in i.evidence)


def test_no_prediction_or_policy_claims(analysis):
    everything = [i.text for i in (*analysis.executive_summary, *analysis.context, *analysis.interpretation)]
    everything += analysis.methodology.definitions + analysis.methodology.notes
    offenders = [t for t in everything if FORECAST.search(t) and "does not" not in t and "no " not in t.lower()]
    assert offenders == []


def test_revisions_and_previous_release_comparison(analysis):
    assert analysis.revisions.available and analysis.revisions.series_key == "cpi.index.sa.all_groups"
    assert analysis.revisions.n_revised >= 10 and analysis.revisions.n_common > 300
    assert "seasonally adjusted" in analysis.revisions.note.lower()
    assert any("unadjusted" in i.text.lower() and "no previously published" in i.text.lower() for i in analysis.context)
    d = analysis.previous_comparison.decompositions[0]
    assert analysis.previous_comparison.available
    assert round(d.previous_published_value, 1) == 3.1 and round(d.new_value, 1) == 4.1
    assert abs(d.revision_component) < 1e-9
    assert d.total_change == pytest.approx(d.new_value - d.previous_published_value)


def test_first_release_has_no_comparison_and_says_so(rt, site):
    ids = ingest_cpi(rt, site, "2026-06")
    a = build_cpi_analysis(rt.conn, ids["2026-06"])
    assert not a.revisions.available and not a.previous_comparison.available
    assert "no earlier publication" in texts(a.executive_summary)["annual-vs-prior"].lower()


def test_methodology_carries_the_caveats_that_matter(analysis):
    notes = " ".join(analysis.methodology.definitions + analysis.methodology.notes)
    for needle in ("June 2017", "Selected Price Indexes", "percentage-point", "tradables", "relicensing"):
        assert needle in notes or needle.lower() in notes.lower()
    assert analysis.methodology.source_url.startswith("https://www.stats.govt.nz/information-releases/")


def test_overview_kpi_is_the_verified_annual_rate(rt, site):
    assert build_cpi_overview_kpi(rt.conn) is None
    ingest_cpi(rt, site, "2026-06")
    kpi, captured_at = build_cpi_overview_kpi(rt.conn)
    assert kpi.metric.series_key.startswith("cpi.") and round(kpi.metric.value, 1) == 4.1
    assert kpi.metric.unit == "percent" and kpi.metric.period == "2026-06"
    assert kpi.published_at.startswith("2026-07-21T10:45") and captured_at
