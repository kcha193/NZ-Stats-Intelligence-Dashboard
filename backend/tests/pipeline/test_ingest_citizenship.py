"""F01: corrupt optional data must never replace the last successful official bundle."""

import csv
import io

import pytest

from nzstats.domain import ErrorClass
from nzstats.pipeline.ingest import ingest_release
from nzstats.store import repo
from tests.pipeline.test_ingest import _CITIZENSHIP_CHART, _chart_series, _edit_page
from tests.support import NOW, ingest_months, release_ref_for


@pytest.mark.parametrize(
    "label",
    [
        "Migrant arrivals (NZ citizens)",
        "Migrant arrivals (non-NZ citizens)",
        "Migrant departures (NZ citizens)",
        "Migrant departures (non-NZ citizens)",
        "Net migration (NZ citizens)",
        "Net migration (non-NZ citizens)",
    ],
)
def test_corrupt_optional_annual_data_preserves_last_good_bundle(rt, site, label):
    ingest_months(rt, "2026-06")
    before = repo.latest_points(rt.conn, "mig.m.net")
    before_count = rt.conn.execute("SELECT COUNT(*) FROM vintage").fetchone()[0]
    ref = release_ref_for("2026-07")
    repo.upsert_release(rt.conn, ref, NOW)

    def edit(obj):
        chart = _chart_series(obj, _CITIZENSHIP_CHART)
        rows = list(csv.reader(io.StringIO(chart["GraphCsvData"])))
        column = rows[0].index("Jul-2026")
        next(row for row in rows[1:] if row[0] == label)[column] = "999999999"
        out = io.StringIO()
        csv.writer(out).writerows(rows)
        chart["GraphCsvData"] = out.getvalue()

    _edit_page(site, "2026-07", edit)
    result = ingest_release(rt, ref.release_key, now_fn=lambda: NOW)
    assert result.error_class is ErrorClass.VALIDATION_FAILED
    assert result.outcome == "failed"
    assert repo.latest_points(rt.conn, "mig.m.net") == before
    assert rt.conn.execute("SELECT COUNT(*) FROM vintage").fetchone()[0] == before_count
