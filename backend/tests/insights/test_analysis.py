import csv
import io
from datetime import datetime

import pandas as pd
import pytest

from nzstats.insights.migration import (
    _streak,
    build_release_analysis,
    describe_provisional,
    driver_share_text,
)
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
    assert a.revisions.available is False and "No earlier publication" in a.revisions.note
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
        rt.conn.execute("DELETE FROM vintage_series_definition WHERE vintage_id = ?", (vid,))
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
    rt.conn.execute("DELETE FROM vintage_series_definition WHERE vintage_id = ?", (vid,))
    rt.conn.execute("DELETE FROM vintage WHERE id = ?", (vid,))
    rt.conn.commit()
    row = repo.get_release_by_id(rt.conn, ids["2026-07"])
    summary = None  # only used for scheduled/delayed wording
    reason = _unavailable_reason(rt.conn, row, summary, SLUGS)
    assert "ingestion attempt ingested" not in reason.lower()
    assert "stored data" in reason.lower()


# --- driver-share statement keeps the signs (review #4246208518) --------------------------------


@pytest.mark.parametrize(("d_arr", "d_dep"), [(100, 90), (-100, -90), (1, 1000)])
def test_no_driver_share_when_arrivals_and_departures_move_the_same_way(d_arr, d_dep) -> None:
    """Net = arrivals - departures, so same-direction moves offset: a share of 'combined movement'
    (100 up, 90 down in net terms) would credit 53% to arrivals for a 10-person net change."""
    assert driver_share_text(d_arr, d_dep) is None


def test_driver_share_for_opposite_moves_is_a_share_of_the_net_change() -> None:
    text = driver_share_text(6585, -4172)  # the real July 2026 year-on-year changes
    assert text is not None and text.startswith(
        "Arrivals account for 61% of the year-on-year change"
    )
    assert "combined movement" not in text
    assert driver_share_text(-300, 100).startswith("Arrivals account for 75%")
    assert driver_share_text(50, -150).startswith("Departures account for 75%")


@pytest.mark.parametrize(("d_arr", "d_dep", "lead"), [(0, -50, "Departures"), (50, 0, "Arrivals")])
def test_driver_share_when_only_one_side_moved(d_arr, d_dep, lead) -> None:
    text = driver_share_text(d_arr, d_dep)
    assert text is not None and text.startswith(f"{lead} account for 100%")


def test_no_driver_share_when_nothing_moved() -> None:
    assert driver_share_text(0, 0) is None


# --- a release's analysis reads one bundle (review #4253628351) ---------------------------------


def test_corrected_release_without_the_optional_chart_shows_no_stale_citizenship_series(
    rt, site
) -> None:
    """The corrected bundle has no citizenship series, so none may be borrowed from the old one."""
    from nzstats.pipeline.ingest import ingest_release
    from tests.pipeline.test_ingest import _CITIZENSHIP_CHART, _drop_chart, _edit_page

    ref = release_ref_for("2026-07")
    repo.upsert_release(rt.conn, ref, NOW)
    assert ingest_release(rt, ref.release_key, now_fn=lambda: NOW).outcome == "ingested"
    release_id = repo.get_release(rt.conn, ref.release_key)["id"]
    before = build_release_analysis(rt.conn, release_id, analysable_slugs=SLUGS)
    assert any(i.id == "citizenship" for i in before.context)

    _edit_page(site, "2026-07", _drop_chart(_CITIZENSHIP_CHART))  # page-only correction
    assert ingest_release(rt, ref.release_key, now_fn=lambda: NOW).outcome == "ingested"
    after = build_release_analysis(rt.conn, release_id, analysable_slugs=SLUGS)
    assert after is not None and after.headline_metrics
    assert not any(i.id == "citizenship" for i in after.context)
    assert "mig.ry.net.nz" not in [m.series_key for m in after.headline_metrics]
    assert not any(e.series_key == "mig.ry.net.nz" for i in after.context for e in i.evidence)
    # Its withdrawal remains visible as historical correction evidence, never a current metric.
    withdrawn = next(s for s in after.corrections.series if s.series_key == "mig.ry.net.nz")
    assert all(r.original is not None and r.revised is None for r in withdrawn.changes)


# --- a streak never bridges a missing month (review #4253711094) --------------------------------


def test_streak_counts_consecutive_months_only() -> None:
    contiguous = {"2026-01": 1.0, "2026-02": 2.0, "2026-03": 3.0, "2026-04": 4.0}
    assert _streak(contiguous) == (3, "rose")
    gapped = {"2026-01": 1.0, "2026-02": 2.0, "2026-04": 4.0, "2026-05": 5.0, "2026-06": 6.0}
    assert _streak(gapped) == (2, "rose")  # 04 -> 05 -> 06; the 02 -> 04 step spans a missing month


def test_streak_at_a_gap_directly_before_the_latest_period_is_zero() -> None:
    assert _streak({"2026-01": 1.0, "2026-02": 2.0, "2026-04": 3.0}) == (0, "")


# --- provisional wording follows the months that really are provisional (review #4253748554) ----


def test_one_provisional_month_is_named_not_ranged() -> None:
    text, evidence = describe_provisional(["2026-07"])
    assert text.startswith("The estimate for July 2026 is provisional")
    assert evidence == ["2026-07"]


def test_consecutive_provisional_months_are_one_range() -> None:
    text, evidence = describe_provisional(["2026-05", "2026-06", "2026-07"])
    assert text.startswith("Estimates from May 2026 to July 2026 are provisional")
    assert evidence == ["2026-05", "2026-07"]


def test_a_range_may_cross_a_year_boundary() -> None:
    text, _ = describe_provisional(["2025-12", "2026-01"])
    assert "from December 2025 to January 2026" in text


def test_non_consecutive_provisional_months_are_never_joined_into_one_range() -> None:
    """January and March provisional with February final must not read as January to March."""
    text, evidence = describe_provisional(["2026-01", "2026-03"])
    assert "January 2026 and March 2026" in text
    assert "January 2026 to March 2026" not in text
    assert "February" not in text
    assert evidence == ["2026-01", "2026-03"]


def test_mixed_runs_and_single_months_are_each_described() -> None:
    text, evidence = describe_provisional(["2026-01", "2026-03", "2026-04", "2026-05", "2026-07"])
    assert "January 2026, March 2026 to May 2026 and July 2026" in text
    assert evidence == ["2026-01", "2026-03", "2026-05", "2026-07"]


def test_provisional_months_are_sorted_before_grouping() -> None:
    assert describe_provisional(["2026-03", "2026-01", "2026-02"])[1] == ["2026-01", "2026-03"]


def test_irregular_provisional_months_in_a_release_are_reported_accurately(rt, site) -> None:
    """A real release whose September 2025 is marked final amid provisional months still ingests
    (validation only warns) and the summary must not call September provisional."""
    from nzstats.pipeline.ingest import ingest_release
    from tests.conftest import fixture_bytes

    ref = release_ref_for("2026-07")
    repo.upsert_release(rt.conn, ref, NOW)
    df = pd.read_csv(io.BytesIO(fixture_bytes("im_2026-07_age_sex.csv")))
    df.loc[df.year_month == "2025-09", "status"] = "Final"
    site.override(
        site.file_url("2026-07", "age_sex"), 200, df.to_csv(index=False, quoting=1).encode()
    )
    out = ingest_release(rt, ref.release_key, now_fn=lambda: NOW)
    assert out.outcome == "ingested", out.detail
    assert any("provisional months are not" in w for w in out.warnings)  # warning kept
    release_id = repo.get_release(rt.conn, ref.release_key)["id"]
    analysis = build_release_analysis(rt.conn, release_id, analysable_slugs=SLUGS)
    item = next(i for i in analysis.executive_summary if i.id == "provisional")
    assert "April 2025 to August 2025" in item.text and "October 2025 to July 2026" in item.text
    assert "September 2025" not in item.text
    assert {e.period for e in item.evidence} == {"2025-04", "2025-08", "2025-10", "2026-07"}


def test_provisional_insight_says_year_ended_totals_with_a_provisional_month_are_provisional(
    rt,
) -> None:
    ids = ingest_months(rt, "2026-07")
    analysis = build_release_analysis(rt.conn, ids["2026-07"], analysable_slugs=SLUGS)
    item = next(i for i in analysis.executive_summary if i.id == "provisional")
    assert "Year-ended totals that include a provisional month are provisional too" in item.text
    assert any(e.series_key == "mig.ry.net" for e in item.evidence)


def test_an_all_final_release_makes_no_provisional_claim(rt, site) -> None:
    from nzstats.pipeline.ingest import ingest_release
    from tests.conftest import fixture_bytes

    ref = release_ref_for("2026-07")
    repo.upsert_release(rt.conn, ref, NOW)
    df = pd.read_csv(io.BytesIO(fixture_bytes("im_2026-07_age_sex.csv")))
    df["status"] = "Final"
    site.override(
        site.file_url("2026-07", "age_sex"), 200, df.to_csv(index=False, quoting=1).encode()
    )
    assert ingest_release(rt, ref.release_key, now_fn=lambda: NOW).outcome == "ingested"
    release_id = repo.get_release(rt.conn, ref.release_key)["id"]
    analysis = build_release_analysis(rt.conn, release_id, analysable_slugs=SLUGS)
    item = next(i for i in analysis.executive_summary if i.id == "provisional")
    assert item.text == "All estimates in this release are final."
