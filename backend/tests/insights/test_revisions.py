import pandas as pd

from nzstats.insights.revisions import revision_view
from nzstats.store import repo
from tests.conftest import FIXTURES
from tests.support import ingest_months


def _net(name):
    df = pd.read_csv(FIXTURES / name)
    t = df[(df.sex == "TOTAL") & (df.age == "TOTAL") & (df.direction == "Net")]
    return dict(zip(t.year_month, t.estimate, strict=True))


def test_default_view_compares_latest_with_previous_vintage(rt) -> None:
    ingest_months(rt, "2026-06", "2026-07")
    view = revision_view(rt.conn, "mig.m.net")
    old, new = _net("im_2026-06_age_sex.csv"), _net("im_2026-07_age_sex.csv")
    expected = {p for p in old.keys() & new.keys() if old[p] != new[p]}
    assert {r.period for r in view.rows} == expected
    assert view.n_revised == len(expected) and view.n_common == len(old.keys() & new.keys())
    assert view.base.title.endswith("June 2026") and view.compare.title.endswith("July 2026")
    assert view.coverage.kind == "release_files" and view.coverage.n_vintages == 2
    assert [h.title for h in view.history] == [view.compare.title]
    assert [r.period for r in view.rows] == sorted(r.period for r in view.rows)


def test_explicit_vintages_and_unknown_vintage(rt) -> None:
    ids = ingest_months(rt, "2026-06", "2026-07")
    june = repo.get_release_by_id(rt.conn, ids["2026-06"])["release_key"]
    july = repo.get_release_by_id(rt.conn, ids["2026-07"])["release_key"]
    swapped = revision_view(rt.conn, "mig.m.net", base_release_key=july, compare_release_key=june)
    assert swapped.base.release_key == july and swapped.compare.release_key == june
    assert revision_view(rt.conn, "mig.m.net", base_release_key="nope") is None


def test_single_vintage_states_the_limitation(rt) -> None:
    ingest_months(rt, "2026-07")
    view = revision_view(rt.conn, "mig.m.net")
    assert view.rows == [] and view.base is None and view.compare is None
    assert "at least two vintages" in view.coverage.note.lower()
    assert view.coverage.n_vintages == 1


def test_unknown_series_is_none(rt) -> None:
    assert revision_view(rt.conn, "nope") is None
