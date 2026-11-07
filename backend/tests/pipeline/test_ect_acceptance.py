"""Phase 4Y rehearsal: no real October figures, no network, temporary databases only."""

import copy
import csv
import hashlib
import io
import sqlite3
import zipfile
from datetime import timedelta

import pytest

from nzstats.config import RefreshSettings
from nzstats.insights.ect import build_ect_dashboard
from nzstats.pipeline.ingest import ingest_release
from nzstats.pipeline.refresh import rolling_backup, run_refresh
from nzstats.store import repo
from nzstats.store.backup_bundle import restore_bundle, verify_bundle
from tests.adapters.test_ect import archive, csv_rows
from tests.ect_acceptance import (
    OCTOBER_KEY,
    OCTOBER_TIME,
    SYNTHETIC_PAGE,
    SYNTHETIC_ZIP,
    reconcile_archive,
    seed_synthetic_october,
)
from tests.ect_support import NOW, seed_ect
from tests.support import BASE


@pytest.fixture()
def october(rt, site):
    for month in ("2026-08", "2026-09"):
        _, key, _ = seed_ect(rt, site, month)
        assert ingest_release(rt, key, now_fn=lambda: NOW).outcome == "ingested"
    rid, raw = seed_synthetic_october(rt, site)
    # Discovery runs normally against empty, explicit mock calendars. Only the seeded
    # target is eligible: this is not a claim about the future official calendar.
    site.override(
        f"{BASE}/release-calendar/calendar-export/",
        200,
        b"BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:synthetic\nSUMMARY:Synthetic event\n"
        b"DTSTART:20261112T104500\nEND:VEVENT\nEND:VCALENDAR",
        "text/calendar",
    )
    for month in ("2026-10", "2026-11", "2026-12"):
        site.override(
            f"{BASE}/api/v1/releaseCalendarMonth/{month}",
            200,
            b'{"items":{"published":[],"upcoming":[]}}',
            "application/json",
        )
    site.requests.clear()
    return rid, raw


def stored(conn):
    return {
        t: [tuple(r) for r in conn.execute(f'SELECT * FROM "{t}" ORDER BY 1')]
        for t in ("vintage", "observation", "vintage_series_definition")
    }


def test_october_refresh_preserves_vintages_reconciles_and_restores(rt, site, october, tmp_path):
    _, raw = october
    before = stored(rt.conn)
    assert len(before["vintage"]) == 192
    old_count = repo.list_vintages(rt.conn, "ect.q.actual.total.count")[-1].vintage_id
    old_points = repo.vintage_points(rt.conn, old_count)
    backup = []

    def verified_backup():
        backup.append(rolling_backup(rt.conn, rt.settings, OCTOBER_TIME))
        assert SYNTHETIC_PAGE not in site.requests
        assert verify_bundle(backup[-1]).ok

    result = run_refresh(rt, RefreshSettings(), now_fn=lambda: OCTOBER_TIME, backup=verified_backup)
    assert (result.ingested, result.requests, result.failures, result.pending) == (1, 6, [], [])
    assert len(backup) == 1
    after = stored(rt.conn)
    assert len(after["vintage"]) == 288
    for table in before:
        assert set(before[table]) <= set(after[table])
    payload = build_ect_dashboard(rt.conn).model_dump(mode="json")
    assert payload["analysis"]["release"]["period_label"] == "October 2026"
    assert payload["analysis"]["release"]["published_at"] == "2026-11-12T10:45:00+13:00"
    assert payload["analysis"]["release"]["status"] == "published"
    assert all(s["vintage"]["release_key"] == OCTOBER_KEY for s in payload["series"])
    assert all(s["source_url"] == SYNTHETIC_ZIP for s in payload["series"])
    assert reconcile_archive(raw, payload, "2026-10") > 1000
    assert (
        max(
            p["period"]
            for s in payload["series"]
            if s["series"]["frequency"] == "quarterly"
            for p in s["points"]
        )
        == "2026-09"
    )
    latest = repo.latest_points(rt.conn, "ect.q.actual.total.count")
    assert latest["2026-09"].value == old_points["2026-09"].value + 1
    assert repo.vintage_points(rt.conn, old_count) == old_points
    assert ingest_release(rt, OCTOBER_KEY, now_fn=lambda: OCTOBER_TIME).outcome == "unchanged"
    assert stored(rt.conn) == after
    site.requests.clear()
    assert run_refresh(rt, RefreshSettings(), now_fn=lambda: OCTOBER_TIME).discovered == 0
    assert len(site.requests) == 4 and SYNTHETIC_PAGE not in site.requests
    for row in rt.conn.execute("SELECT path,sha256 FROM raw_artifact"):
        assert (
            hashlib.sha256((rt.settings.raw_dir / row["path"]).read_bytes()).hexdigest()
            == row["sha256"]
        )
    target = tmp_path / "rollback"
    assert restore_bundle(backup[0], target).ok
    conn = sqlite3.connect(target / "nzstats.db")
    try:
        assert stored(conn) == before
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        conn.close()


@pytest.mark.parametrize("failure", ["not_yet", "scaled", "definition", "stale_quarter", "backup"])
def test_october_failures_keep_last_known_good(rt, site, october, failure):
    _, raw = october
    before = stored(rt.conn)
    if failure == "not_yet":
        site.override(SYNTHETIC_ZIP, 404, b"", "text/html")
    elif failure != "backup":
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            rows = list(csv.DictReader(io.StringIO(z.read(z.namelist()[0]).decode())))
        if failure == "stale_quarter":
            rows = [
                r for r in rows if r["Series_reference"] != "ECTQ.S29A9" or r["Period"] != "2026.09"
            ]
        else:
            row = next(
                r
                for r in rows
                if r["Series_reference"] == "ECTM.S19A2" and r["Period"] == "2026.10"
            )
            row["Data_value" if failure == "scaled" else "Magnitude"] = (
                "999999" if failure == "scaled" else "0"
            )
        site.override(SYNTHETIC_ZIP, 200, archive(rows), "application/zip")

    def backup():
        if failure == "backup":
            raise OSError("synthetic backup failure")
        rolling_backup(rt.conn, rt.settings, OCTOBER_TIME)

    result = run_refresh(rt, RefreshSettings(), now_fn=lambda: OCTOBER_TIME, backup=backup)
    assert result.ingested == 0 and stored(rt.conn) == before
    assert build_ect_dashboard(rt.conn).analysis.release.period_label == "September 2026"
    if failure == "not_yet":
        assert [(p.release_key, p.reason) for p in result.pending] == [
            (OCTOBER_KEY, "not_published_yet")
        ]
    elif failure == "backup":
        assert result.error_class == "backup_failed" and SYNTHETIC_PAGE not in site.requests
    else:
        assert result.failures[0]["error_class"] == "validation_failed"
        site.requests.clear()
        retry = run_refresh(rt, RefreshSettings(), now_fn=lambda: OCTOBER_TIME)
        assert [(p.release_key, p.reason) for p in retry.pending] == [
            (OCTOBER_KEY, "rejected_today")
        ]
        assert SYNTHETIC_PAGE not in site.requests


def test_october_is_not_requested_before_release_time(rt, site, october):
    result = run_refresh(rt, RefreshSettings(), now_fn=lambda: OCTOBER_TIME - timedelta(seconds=1))
    assert result.discovered == 0 and SYNTHETIC_PAGE not in site.requests


@pytest.mark.parametrize("damage", ["period", "unit", "level", "percent", "comparison", "status"])
def test_independent_reconciliation_rejects_wrong_dashboard(rt, site, october, damage):
    _, raw = october
    assert ingest_release(rt, OCTOBER_KEY, now_fn=lambda: OCTOBER_TIME).outcome == "ingested"
    payload = build_ect_dashboard(rt.conn).model_dump(mode="json")
    assert reconcile_archive(raw, payload, "2026-10") > 1000
    payload = copy.deepcopy(payload)
    retail = next(s for s in payload["series"] if s["series"]["key"] == "ect.m.sa.retail.value")
    metric = next(
        m
        for m in payload["analysis"]["headline_metrics"]
        if m["series_key"] == "ect.m.sa.retail.value"
    )
    if damage == "period":
        metric["period"] = "2026-09"
    elif damage == "unit":
        retail["series"]["unit"] = "NZD"
    elif damage == "level":
        retail["points"][-1]["value"] *= 10
    elif damage == "status":
        retail["points"][-1]["status"] = "final"
    elif damage == "comparison":
        metric["change_prior"]["comparison_period"] = "2026-08"
    else:
        metric["change_prior"]["percent"] = 5
    with pytest.raises(AssertionError):
        reconcile_archive(raw, payload, "2026-10")


def _october_payload(rt, october):
    _, raw = october
    assert ingest_release(rt, OCTOBER_KEY, now_fn=lambda: OCTOBER_TIME).outcome == "ingested"
    payload = build_ect_dashboard(rt.conn).model_dump(mode="json")
    assert reconcile_archive(raw, payload, "2026-10") > 1000
    return raw, copy.deepcopy(payload)


@pytest.mark.parametrize(
    "removed",
    [
        "ect.m.sa.core.value",
        "ect.m.sa.total.value",
        "ect.m.actual.total.value",
        "ect.m.actual.total.count",
        "ect.m.actual.total.average",
    ],
)
def test_oracle_requires_every_headline_metric(rt, site, october, removed):
    raw, payload = _october_payload(rt, october)
    metrics = payload["analysis"]["headline_metrics"]
    payload["analysis"]["headline_metrics"] = [m for m in metrics if m["series_key"] != removed]
    with pytest.raises(AssertionError, match="missing required headline metrics"):
        reconcile_archive(raw, payload, "2026-10")


def test_oracle_rejects_retail_only_headline_metrics(rt, site, october):
    raw, payload = _october_payload(rt, october)
    metrics = payload["analysis"]["headline_metrics"]
    payload["analysis"]["headline_metrics"] = metrics[:1]
    with pytest.raises(AssertionError, match="missing required headline metrics"):
        reconcile_archive(raw, payload, "2026-10")


def test_oracle_rejects_duplicate_headline_metric(rt, site, october):
    raw, payload = _october_payload(rt, october)
    payload["analysis"]["headline_metrics"].append(payload["analysis"]["headline_metrics"][0])
    with pytest.raises(AssertionError, match="duplicate headline metric"):
        reconcile_archive(raw, payload, "2026-10")


def test_oracle_allows_optional_extra_headline_metric(rt, site, october):
    raw, payload = _october_payload(rt, october)
    durables = next(s for s in payload["series"] if s["series"]["key"] == "ect.m.sa.durables.value")
    prior, current = durables["points"][-2], durables["points"][-1]
    extra = copy.deepcopy(payload["analysis"]["headline_metrics"][0])
    extra["series_key"] = durables["series"]["key"]
    extra["period"], extra["value"] = current["period"], current["value"]
    extra["change_prior"] = {
        "comparison_period": prior["period"],
        "absolute": current["value"] - prior["value"],
        "percent": (current["value"] / prior["value"] - 1) * 100,
    }
    payload["analysis"]["headline_metrics"].append(extra)
    assert reconcile_archive(raw, payload, "2026-10") > 1000


@pytest.mark.parametrize("key", ["ect.m.sa.retail.value", "ect.q.sa.retail.value"])
@pytest.mark.parametrize("damage", ["reversed", "duplicate", "misplaced"])
def test_oracle_rejects_unordered_or_duplicate_points(rt, site, october, key, damage):
    raw, payload = _october_payload(rt, october)
    points = next(s for s in payload["series"] if s["series"]["key"] == key)["points"]
    if damage == "reversed":
        points.reverse()
    elif damage == "duplicate":
        points.append(copy.deepcopy(points[-1]))
    else:  # latest observation moved away from the end
        points.insert(0, points.pop())
    with pytest.raises(AssertionError, match="duplicate periods|not chronological"):
        reconcile_archive(raw, payload, "2026-10")


def test_september_oracle_matches_official_headlines(rt, site):
    from decimal import Decimal

    from tests.conftest import fixture_bytes

    _, key, _ = seed_ect(rt, site)
    assert ingest_release(rt, key, now_fn=lambda: NOW).outcome == "ingested"
    assert (
        reconcile_archive(
            fixture_bytes("ect_2026-09.zip"),
            build_ect_dashboard(rt.conn).model_dump(mode="json"),
            "2026-09",
        )
        > 1000
    )
    source = {
        (r["Series_reference"], r["Period"]): Decimal(r["Data_value"])
        for r in csv_rows()
        if r["Data_value"] and not r["Suppressed"]
    }
    # Official September prose benchmarks, not values obtained from dashboard outputs.
    for code, current, prior, percent, dollars in [
        ("ECTM.S19S1", "2026.09", "2026.08", "-0.4", "-30"),
        ("ECTM.S19S2", "2026.09", "2026.08", "-0.7", "-41"),
        ("ECTM.S19S9", "2026.09", "2026.08", "-0.5", "-51"),
        ("ECTQ.S19S1", "2026.09", "2026.06", "0.1", "14"),
        ("ECTQ.S19S2", "2026.09", "2026.06", "0.4", "79"),
    ]:
        value, previous = source[code, current], source[code, prior]
        assert abs((value / previous - 1) * 100 - Decimal(percent)) <= Decimal("0.065")
        assert abs(value - previous - Decimal(dollars)) <= Decimal("0.55")
