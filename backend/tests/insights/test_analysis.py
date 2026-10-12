import csv
import io
from datetime import datetime

import pandas as pd
import pytest

from nzstats.insights.migration import build_release_analysis
from nzstats.sources.calendar import events_to_refs, parse_ics
from nzstats.sources.release_page import parse_release_page
from nzstats.store import repo
from tests.conftest import FIXTURES, fixture_text
from tests.support import BASE, NOW, ingest_months, release_ref_for

SLUGS = {"international-migration"}
DIRECTION_CHART = "Estimated migration by direction, rolling year"


def _rolling_net(month: str) -> dict[str, float]:
    """Independent reading of the published rolling-year net series from the page fixture."""
    page = parse_release_page(fixture_text(f"im_{month}_page.html"), BASE)
    rows = list(csv.reader(io.StringIO(page.chart_starting_with(DIRECTION_CHART).csv)))
    net = next(r for r in rows if r[0] == "Net migration")
    return {
        datetime.strptime(h, "%b-%Y").strftime("%Y-%m"): float(v)
        for h, v in zip(rows[0][1:], net[1:], strict=True)
    }


def _monthly_net(name: str) -> dict[str, int]:
    df = pd.read_csv(FIXTURES / name)
    t = df[(df.sex == "TOTAL") & (df.age == "TOTAL") & (df.direction == "Net")]
    return dict(zip(t.year_month, t.estimate, strict=True))


@pytest.fixture()
def both(rt):
    ids = ingest_months(rt, "2026-06", "2026-07")
    return rt, ids


def _analysis(rt, release_id):
    return build_release_analysis(rt.conn, release_id, analysable_slugs=SLUGS)


def _metric(analysis, key):
    return next(m for m in analysis.headline_metrics if m.series_key == key)


def test_headline_metrics_match_published_values(both) -> None:
    rt, ids = both
    a = _analysis(rt, ids["2026-07"])
    july = _rolling_net("2026-07")
    m = _metric(a, "mig.ry.net")
    assert (m.value, m.period, m.unit, m.status) == (
        july["2026-07"],
        "2026-07",
        "people",
        "provisional",
    )
    assert m.period_label == "Year ended July 2026"
    yago = m.change_year_ago
    assert yago.comparison_period == "2025-07"
    assert yago.absolute == pytest.approx(july["2026-07"] - july["2025-07"])
    assert yago.percent == pytest.approx(
        (july["2026-07"] - july["2025-07"]) / july["2025-07"] * 100
    )
    monthly = _metric(a, "mig.m.net")
    assert (
        monthly.value == 5170.0 and monthly.std_error == 545.0 and monthly.status == "provisional"
    )


def test_negative_base_gives_no_percentage(both) -> None:
    rt, ids = both
    nz = _metric(_analysis(rt, ids["2026-07"]), "mig.ry.net.nz")
    assert nz.value < 0
    assert nz.change_year_ago is not None and nz.change_year_ago.percent is None


def test_executive_summary_is_traceable_to_stored_observations(both) -> None:
    rt, ids = both
    a = _analysis(rt, ids["2026-07"])
    assert [i.id for i in a.executive_summary] == [
        "headline",
        "monthly",
        "drivers",
        "revisions",
        "provisional",
    ]
    assert 3 <= len(a.executive_summary) <= 5
    for insight in [*a.executive_summary, *a.context, *a.interpretation]:
        assert insight.kind in ("observation", "inference") and insight.text
        assert insight.evidence, f"{insight.id} has no evidence"
        for e in insight.evidence:
            release_id = repo.get_release(rt.conn, e.release_key)["id"]
            vintage = repo.release_vintage(rt.conn, e.series_key, release_id)
            stored = repo.vintage_observations(rt.conn, vintage.vintage_id)[e.period]
            assert stored.value == e.value, (insight.id, e)


def test_new_period_is_separated_from_revision_of_the_earlier_period(both) -> None:
    rt, ids = both
    a = _analysis(rt, ids["2026-07"])
    june, july = _rolling_net("2026-06"), _rolling_net("2026-07")
    d = next(x for x in a.previous_comparison.decompositions if x.series_key == "mig.ry.net")
    assert (d.previous_period, d.new_period) == ("2026-06", "2026-07")
    assert d.previous_published_value == june["2026-06"]
    assert d.same_period_now == july["2026-06"]
    assert d.new_value == july["2026-07"]
    assert d.revision_component == pytest.approx(july["2026-06"] - june["2026-06"])
    assert d.new_period_component == pytest.approx(july["2026-07"] - july["2026-06"])
    assert d.revision_component + d.new_period_component == pytest.approx(d.total_change)


def test_revision_block_matches_independent_calculation(both) -> None:
    rt, ids = both
    a = _analysis(rt, ids["2026-07"])
    old, new = _monthly_net("im_2026-06_age_sex.csv"), _monthly_net("im_2026-07_age_sex.csv")
    changed = {p: new[p] - old[p] for p in old.keys() & new.keys() if new[p] != old[p]}
    r = a.revisions
    assert (
        r.available and r.n_revised == len(changed) and r.n_common == len(old.keys() & new.keys())
    )
    top = max(changed, key=lambda p: abs(changed[p]))
    assert r.largest[0].period == top and r.largest[0].absolute == changed[top]
    assert [abs(x.absolute) for x in r.largest] == sorted(
        (abs(x.absolute) for x in r.largest), reverse=True
    )


def test_history_rank_matches_independent_ranking(both) -> None:
    rt, ids = both
    a = _analysis(rt, ids["2026-07"])
    series = _rolling_net("2026-07")
    latest = series["2026-07"]
    rank = 1 + sum(v > latest for v in series.values())
    history = next(i for i in a.context if i.id == "history")
    assert f"#{rank} highest of {len(series)}" in history.text
    assert "does not indicate economic significance" in (history.caveat or "")


def test_first_release_has_explicit_limitations_not_errors(rt) -> None:
    ids = ingest_months(rt, "2026-06")
    a = _analysis(rt, ids["2026-06"])
    assert a is not None
    assert a.revisions.available is False and "No earlier vintage" in a.revisions.note
    assert a.previous_comparison.available is False
    assert 3 <= len(a.executive_summary) <= 5


def test_none_when_no_vintage_or_other_series(rt) -> None:
    ref = release_ref_for("2026-07")
    release_id = repo.upsert_release(rt.conn, ref, NOW)
    assert _analysis(rt, release_id) is None  # known release, nothing ingested yet
    assert build_release_analysis(rt.conn, 99999, analysable_slugs=SLUGS) is None
    other = next(
        r
        for r in events_to_refs(parse_ics(fixture_text("calendar_export_excerpt.ics")))
        if r.series_slug != "international-migration"
    )
    assert _analysis(rt, repo.upsert_release(rt.conn, other, NOW)) is None


def test_inference_is_labelled_and_hedged(both) -> None:
    rt, ids = both
    a = _analysis(rt, ids["2026-07"])
    for insight in a.interpretation:
        if insight.kind == "inference":
            assert "not" in insight.text.lower() or "mechanical" in insight.text.lower()
    banned = ("because of", "caused by", "due to", "driven by policy", "as a result of")
    for insight in [*a.executive_summary, *a.context, *a.interpretation]:
        assert not any(b in insight.text.lower() for b in banned), insight.text


# --- regression from the final review: a release without the year-ended citizenship chart -----------


def _drop_citizenship_vintages(rt, release_id) -> None:
    """What the store holds after a release (e.g. Sept 2025) published no citizenship chart."""
    ids = [
        r[0]
        for r in rt.conn.execute(
            "SELECT v.id FROM vintage v JOIN series s ON s.id = v.series_id"
            " WHERE v.release_id = ? AND s.key IN ('mig.ry.net.nz', 'mig.ry.net.nonnz')",
            (release_id,),
        )
    ]
    assert ids, "fixture should contain citizenship vintages to remove"
    for vid in ids:
        rt.conn.execute("DELETE FROM observation WHERE vintage_id = ?", (vid,))
        rt.conn.execute("DELETE FROM vintage WHERE id = ?", (vid,))
    rt.conn.commit()


def test_release_without_citizenship_chart_still_has_an_analysis(both) -> None:
    rt, ids = both
    _drop_citizenship_vintages(rt, ids["2026-07"])
    analysis = _analysis(rt, ids["2026-07"])
    assert analysis is not None
    keys = [m.series_key for m in analysis.headline_metrics]
    assert "mig.ry.net" in keys and "mig.ry.net.nz" not in keys and "mig.ry.net.nonnz" not in keys
    assert "citizenship" not in [i.id for i in analysis.context]


def test_overview_still_shows_kpis_for_a_release_without_citizenship_chart(both) -> None:
    from nzstats.insights.overview import build_overview

    rt, ids = both
    _drop_citizenship_vintages(rt, ids["2026-07"])
    overview = build_overview(rt.conn, analysable_slugs=SLUGS, now=NOW)
    assert overview.kpis and overview.featured is not None


def test_unavailable_reason_never_calls_a_successful_ingest_the_reason(both) -> None:
    from nzstats.api.routes import _unavailable_reason
    from nzstats.models import ReleaseSummary  # noqa: F401  (type only)

    rt, ids = both
    # Required series missing for the release: ingest succeeded but no analysis can be built.
    vid = rt.conn.execute(
        "SELECT v.id FROM vintage v JOIN series s ON s.id = v.series_id"
        " WHERE v.release_id = ? AND s.key = 'mig.m.net'",
        (ids["2026-07"],),
    ).fetchone()[0]
    rt.conn.execute("DELETE FROM observation WHERE vintage_id = ?", (vid,))
    rt.conn.execute("DELETE FROM vintage WHERE id = ?", (vid,))
    rt.conn.commit()
    row = repo.get_release_by_id(rt.conn, ids["2026-07"])
    summary = None  # only used for scheduled/delayed wording
    reason = _unavailable_reason(rt.conn, row, summary, SLUGS)
    assert "ingestion attempt ingested" not in reason.lower()
    assert "stored data" in reason.lower()
