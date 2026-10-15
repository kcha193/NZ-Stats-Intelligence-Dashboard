from datetime import UTC, datetime

import pytest

from nzstats.adapters.migration.series import monthly_def
from nzstats.clock import to_utc_iso
from nzstats.domain import Observation, ObsStatus
from nzstats.store import repo
from nzstats.store.db import connect, migrate, transaction
from tests.support import release_ref_for

NOW = datetime(2026, 10, 11, tzinfo=UTC)


@pytest.fixture()
def conn(tmp_path):
    c = connect(tmp_path / "t.db")
    migrate(c)
    return c


def _vintage(conn, month, value):
    ref = release_ref_for(month)
    rid = repo.upsert_release(conn, ref, NOW)
    sid = repo.upsert_series(conn, monthly_def("net"))
    with transaction(conn):
        vid = repo.create_vintage(conn, rid, sid, NOW, "release_files", "v1", f"sha-{month}")
        repo.insert_observations(
            conn,
            vid,
            [Observation("mig.m.net", "2026-05", value, ObsStatus.PROVISIONAL, 7.0, "2026-07")],
        )
    return ref, rid


def test_release_and_previous_vintage_and_rows(conn) -> None:
    june, jid = _vintage(conn, "2026-06", 100.0)
    july, lid = _vintage(conn, "2026-07", 120.0)
    assert repo.release_vintage(conn, "mig.m.net", lid).release_key == july.release_key
    assert repo.release_vintage(conn, "mig.m.net", 9999) is None
    prev = repo.previous_vintage(conn, "mig.m.net", to_utc_iso(july.published_at))
    assert prev.release_key == june.release_key and prev.title == june.title
    assert repo.previous_vintage(conn, "mig.m.net", to_utc_iso(june.published_at)) is None
    rows = repo.vintage_observations(conn, prev.vintage_id)
    assert rows["2026-05"].std_error == 7.0 and rows["2026-05"].released_in == "2026-07"
    assert rows["2026-05"].status is ObsStatus.PROVISIONAL


def test_series_row_release_row_and_overview(conn) -> None:
    _, rid = _vintage(conn, "2026-07", 120.0)
    assert repo.get_series_row(conn, "mig.m.net")["unit"] == "people"
    assert repo.get_series_row(conn, "nope") is None
    assert repo.get_release_by_id(conn, rid)["series_slug"] == "international-migration"
    (row,) = repo.series_overview(conn)
    assert (row["key"], row["n_vintages"], row["latest_period"]) == ("mig.m.net", 1, "2026-05")
    assert repo.series_overview(conn, "nothing") == []
    assert len(repo.series_overview(conn, "migration")) == 1
