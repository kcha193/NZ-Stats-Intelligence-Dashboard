"""Statistical identity excludes editorial source changes without deleting old vintages."""

import csv
import io

import pandas as pd
import pytest

from nzstats.store import repo
from tests.conftest import fixture_bytes
from tests.pipeline.test_ingest import (
    _DIRECTION_CHART,
    _bump_net_rolling,
    _chart_series,
    _count,
    _edit_page,
    _ingest,
    _seed,
)
from tests.support import page_url


def _editorial_title(obj):
    _chart_series(obj, _DIRECTION_CHART)["Title"] += " (updated caption)"


def _unused_chart(obj):
    graph = next(b for b in obj["PageBlocks"] if b.get("ClassName") == "GraphTableBlock")
    graph["SeriesData"].append(
        {"Title": "Editorial companion chart", "GraphCsvData": '"Category","Count"\n"A",1'}
    )


@pytest.mark.parametrize("edit", [_editorial_title, _unused_chart])
def test_editorial_chart_changes_do_not_create_statistical_vintages(rt, site, edit):
    (key,) = _seed(rt, "2026-07")
    assert _ingest(rt, key).outcome == "ingested"
    before = (_count(rt, "vintage"), _count(rt, "observation"))
    _edit_page(site, "2026-07", edit)
    assert _ingest(rt, key).outcome == "unchanged"
    assert (_count(rt, "vintage"), _count(rt, "observation")) == before
    assert repo.get_release(rt.conn, key)["status"] == "published"


def test_reformatted_files_do_not_create_statistical_vintages(rt, site):
    (key,) = _seed(rt, "2026-07")
    assert _ingest(rt, key).outcome == "ingested"
    before = _count(rt, "vintage")
    rows = list(csv.reader(io.StringIO(fixture_bytes("im_2026-07_age_sex.csv").decode())))
    out = io.StringIO()
    csv.writer(out, quoting=csv.QUOTE_ALL, lineterminator="\r\n").writerows(rows)
    site.override(site.file_url("2026-07", "age_sex"), 200, out.getvalue().encode())
    assert _ingest(rt, key).outcome == "unchanged"
    assert _count(rt, "vintage") == before


def test_legacy_identity_is_reused_without_rewriting_vintages_and_can_be_reactivated(rt, site):
    (key,) = _seed(rt, "2026-07")
    original_page = site.routes[page_url("2026-07")]
    assert _ingest(rt, key).outcome == "ingested"
    # Simulate the existing unversioned source-bundle digest in an installed database.
    rt.conn.execute("UPDATE vintage SET bundle_sha256 = ?", ("f" * 64,))
    rt.conn.commit()
    before = [tuple(r) for r in rt.conn.execute("SELECT * FROM vintage ORDER BY id")]
    assert _ingest(rt, key).outcome == "unchanged"
    assert [tuple(r) for r in rt.conn.execute("SELECT * FROM vintage ORDER BY id")] == before
    _edit_page(site, "2026-07", _bump_net_rolling)
    assert _ingest(rt, key).outcome == "ingested"
    count = _count(rt, "vintage")
    site.override(page_url("2026-07"), *original_page)
    _edit_page(site, "2026-07", _editorial_title)
    assert _ingest(rt, key).outcome == "ingested"
    rid = repo.get_release(rt.conn, key)["id"]
    assert repo.release_bundle(rt.conn, rid) == "f" * 64
    assert _count(rt, "vintage") == count
    assert len(repo.list_vintages(rt.conn, "mig.ry.net")) == 2


@pytest.mark.parametrize("field,value", [("status", "Final"), ("standard_error", 123.0)])
def test_observation_status_and_standard_error_are_statistical_changes(rt, site, field, value):
    (key,) = _seed(rt, "2026-07")
    assert _ingest(rt, key).outcome == "ingested"
    df = pd.read_csv(io.BytesIO(fixture_bytes("im_2026-07_age_sex.csv")))
    df.loc[(df.year_month == "2026-07") & (df.direction == "Net"), field] = value
    site.override(site.file_url("2026-07", "age_sex"), 200, df.to_csv(index=False).encode())
    assert _ingest(rt, key).outcome == "ingested"
    assert len(repo.list_vintages(rt.conn, "mig.m.net")) == 2


def test_signed_zero_standard_error_format_does_not_create_a_statistical_vintage(rt, site):
    (key,) = _seed(rt, "2026-07")
    assert _ingest(rt, key).outcome == "ingested"
    before = _count(rt, "vintage")
    df = pd.read_csv(io.BytesIO(fixture_bytes("im_2026-07_age_sex.csv")))
    assert (df.standard_error == 0).any()
    df["standard_error"] = df.standard_error.astype(float)
    df.loc[df.standard_error == 0, "standard_error"] = -0.0
    site.override(site.file_url("2026-07", "age_sex"), 200, df.to_csv(index=False).encode())
    assert _ingest(rt, key).outcome == "unchanged"
    assert _count(rt, "vintage") == before
