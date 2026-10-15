import pytest

from nzstats.domain import ObsStatus, Point
from nzstats.stats.revision import revisions, summarise


def _p(period: str, value: float, status: ObsStatus = ObsStatus.PROVISIONAL) -> Point:
    return Point(period, value, status)


def test_revisions_cover_common_periods_only() -> None:
    orig = {"2026-05": _p("2026-05", 100.0), "2026-06": _p("2026-06", 200.0)}
    rev = {"2026-05": _p("2026-05", 110.0, ObsStatus.FINAL), "2026-07": _p("2026-07", 5.0)}
    out = revisions(orig, rev)
    assert [r.period for r in out] == ["2026-05"]
    r = out[0]
    assert r.absolute == 10.0 and r.percent == pytest.approx(10.0)
    assert (r.original_status, r.revised_status) == (ObsStatus.PROVISIONAL, ObsStatus.FINAL)


def test_percent_is_none_when_not_meaningful() -> None:
    orig = {"2026-05": _p("2026-05", -50.0)}
    rev = {"2026-05": _p("2026-05", 20.0)}
    (r,) = revisions(orig, rev)
    assert r.absolute == 70.0 and r.percent is None


def test_summary() -> None:
    orig = {f"2026-0{i}": _p(f"2026-0{i}", 100.0) for i in range(1, 5)}
    rev = {
        "2026-01": _p("2026-01", 100.0),
        "2026-02": _p("2026-02", 90.0),
        "2026-03": _p("2026-03", 130.0),
        "2026-04": _p("2026-04", 100.0),
    }
    s = summarise(revisions(orig, rev))
    assert s.n_common == 4 and s.n_revised == 2
    assert s.max_abs.period == "2026-03" and s.max_abs.absolute == 30.0
    assert s.mean_abs == pytest.approx(20.0)  # mean over revised periods only


def test_summary_of_nothing() -> None:
    s = summarise([])
    assert s.n_common == 0 and s.n_revised == 0 and s.max_abs is None and s.mean_abs is None
