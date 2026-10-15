import calendar
import csv
import html
import io
import json
import re
import sqlite3
from dataclasses import replace

import pandas as pd
import pytest

from nzstats.clock import AKL
from nzstats.domain import ErrorClass, ReleaseStatus
from nzstats.pipeline.ingest import backfill, ingest_release
from nzstats.sources.calendar import events_to_refs, parse_ics
from nzstats.stats.periods import add_months, month_range
from nzstats.stats.revision import revisions
from nzstats.store import repo
from tests.conftest import FIXTURES, fixture_bytes, fixture_text
from tests.support import NOW, page_url, release_ref_for


def _seed(rt, *months) -> list[str]:
    keys = []
    for m in months:
        ref = release_ref_for(m)
        repo.upsert_release(rt.conn, ref, NOW)
        keys.append(ref.release_key)
    return keys


def _count(rt, table: str) -> int:
    return rt.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _ingest(rt, key):
    return ingest_release(rt, key, now_fn=lambda: NOW)


def test_happy_path_ingests_real_fixtures_in_order(rt) -> None:
    june, july = _seed(rt, "2026-06", "2026-07")
    assert _ingest(rt, june).outcome == "ingested"
    out = _ingest(rt, july)
    assert out.outcome == "ingested", out.detail
    assert repo.latest_points(rt.conn, "mig.m.net")["2026-07"].value == 5170.0
    row = repo.get_release(rt.conn, july)
    assert row["status"] == "published" and row["headline"]
    assert len(repo.list_vintages(rt.conn, "mig.m.net")) == 2
    assert _count(rt, "ingest_run") == 2
    health = {r["source"]: r["state"] for r in rt.conn.execute("SELECT * FROM source_health")}
    assert health["release:international-migration"] == "ok"


def test_reingesting_identical_files_is_a_noop(rt) -> None:
    (july,) = _seed(rt, "2026-07")
    assert _ingest(rt, july).outcome == "ingested"
    before = (_count(rt, "vintage"), _count(rt, "observation"))
    assert _ingest(rt, july).outcome == "unchanged"
    assert (_count(rt, "vintage"), _count(rt, "observation")) == before


def _net(name: str) -> dict[str, int]:
    df = pd.read_csv(FIXTURES / name)
    t = df[(df.sex == "TOTAL") & (df.age == "TOTAL") & (df.direction == "Net")]
    return dict(zip(t.year_month, t.estimate, strict=True))


def test_revisions_between_real_vintages_match_independent_calculation(rt) -> None:
    june, july = _seed(rt, "2026-06", "2026-07")
    _ingest(rt, june)
    _ingest(rt, july)
    a, b = _net("im_2026-06_age_sex.csv"), _net("im_2026-07_age_sex.csv")
    expected = {p for p in a.keys() & b.keys() if a[p] != b[p]}
    v = repo.list_vintages(rt.conn, "mig.m.net")
    got = {
        r.period
        for r in revisions(
            repo.vintage_points(rt.conn, v[0].vintage_id),
            repo.vintage_points(rt.conn, v[1].vintage_id),
        )
        if r.absolute != 0
    }
    assert got == expected and expected, "the July release should revise earlier months"


def _drop_month(data: bytes, period: str) -> bytes:
    df = pd.read_csv(io.BytesIO(data))
    return df[df.year_month != period].to_csv(index=False, quoting=1).encode()


def test_validation_failure_writes_nothing_and_keeps_last_known_good(rt, site) -> None:
    june, july = _seed(rt, "2026-06", "2026-07")
    _ingest(rt, june)
    good = repo.latest_points(rt.conn, "mig.m.net")
    url = site.file_url("2026-07", "age_sex")
    site.override(url, 200, _drop_month(fixture_bytes("im_2026-07_age_sex.csv"), "2015-05"))
    out = _ingest(rt, july)
    assert out.outcome == "failed" and out.error_class is ErrorClass.VALIDATION_FAILED
    assert "continuity" in (out.detail or "") or "missing months" in (out.detail or "")
    assert repo.latest_points(rt.conn, "mig.m.net") == good
    assert len(repo.list_vintages(rt.conn, "mig.m.net")) == 1
    assert repo.get_release(rt.conn, july)["status"] == "published"  # from seed, unchanged
    run = rt.conn.execute("SELECT * FROM ingest_run ORDER BY id DESC LIMIT 1").fetchone()
    assert run["outcome"] == "failed" and run["error_class"] == "validation_failed"
    health = {r["source"]: r["state"] for r in rt.conn.execute("SELECT * FROM source_health")}
    assert health["release:international-migration"] == "degraded"


def _seed_with_status(rt, month: str, status: ReleaseStatus) -> str:
    ref = release_ref_for(month, status)
    repo.upsert_release(rt.conn, ref, NOW)
    return ref.release_key


def _release_health(rt) -> sqlite3.Row | None:
    return rt.conn.execute(
        "SELECT * FROM source_health WHERE source = 'release:international-migration'"
    ).fetchone()


def test_page_live_but_data_file_missing_is_not_available_and_writes_no_vintage(rt, site) -> None:
    july = _seed_with_status(rt, "2026-07", ReleaseStatus.SCHEDULED)
    site.override(site.file_url("2026-07", "citizenship_visa_country"), 404, b"", "text/html")
    out = _ingest(rt, july)
    assert out.outcome == "not_available" and out.error_class is ErrorClass.NOT_FOUND
    assert _count(rt, "vintage") == 0 and _count(rt, "observation") == 0
    assert _count(rt, "source_health") == 0  # polling before files exist is not a failure


def test_missing_files_of_a_published_release_degrade_release_health(rt, site) -> None:
    """Review #4254166737: a 404 on a release already published is a data gap, not pre-publication."""
    (july,) = _seed(rt, "2026-07")  # seeded as published
    site.override(site.file_url("2026-07", "age_sex"), 404, b"", "text/html")
    out = _ingest(rt, july)
    assert out.outcome == "not_available"
    health = _release_health(rt)
    assert health is not None and health["state"] == "degraded"
    assert july in health["detail"]


def test_release_health_recovers_once_the_published_release_is_available_again(rt, site) -> None:
    (july,) = _seed(rt, "2026-07")
    url = site.file_url("2026-07", "age_sex")
    good = site.routes[url]
    site.override(url, 404, b"", "text/html")
    _ingest(rt, july)
    assert _release_health(rt)["state"] == "degraded"
    site.override(url, *good)
    assert _ingest(rt, july).outcome == "ingested"
    assert _release_health(rt)["state"] == "ok"


def test_block_page_served_as_200_is_failed_blocked(rt, site) -> None:
    (july,) = _seed(rt, "2026-07")
    body = b"<html>Request unsuccessful. Incapsula incident ID: 42</html>"
    site.override(site.file_url("2026-07", "age_sex"), 200, body, "text/html")
    out = _ingest(rt, july)
    assert out.outcome == "failed" and out.error_class is ErrorClass.BLOCKED
    assert _count(rt, "vintage") == 0


def _bump(data: bytes, period: str, delta: int) -> bytes:
    df = pd.read_csv(io.BytesIO(data))
    sel = (df.sex == "TOTAL") & (df.age == "TOTAL") & (df.year_month == period)
    df.loc[sel & df.direction.isin(["Arrivals", "Net"]), "estimate"] += delta
    return df.to_csv(index=False, quoting=1).encode()


def _revise_consistently(site, month: str, period: str, delta: int) -> None:
    """Model a genuine Stats NZ revision of one month's arrivals (and so net).

    Every published figure derived from that month moves with it: the monthly arrivals and net, the
    non-NZ citizenship split, and the twelve year-ended chart values whose window contains the month.
    Validation requires these to agree, so a monthly-only edit would be (correctly) rejected.
    """
    age_url = site.file_url(month, "age_sex")
    site.override(age_url, 200, _bump(fixture_bytes(f"im_{month}_age_sex.csv"), period, delta))
    df = pd.read_csv(FIXTURES / f"im_{month}_citizenship_country.csv")
    sel = (
        (df.year_month == period)
        & (df.direction == "Arrivals")
        & (df.citizenship == "non-NZ")
        & (df.visa == "TOTAL")
        & (df.country_of_residence == "TOTAL")
        & (df.passenger_type == "Long-term migrant")
    )
    assert sel.sum() == 1
    df.loc[sel, "estimate"] += delta
    cit_url = site.file_url(month, "citizenship_visa_country")
    site.override(cit_url, 200, df.to_csv(index=False, quoting=1).encode())

    windows = {
        f"{calendar.month_abbr[int(m[5:])]}-{m[:4]}"
        for m in month_range(period, add_months(period, 11))
    }

    def edit(obj) -> None:
        series = _chart_series(obj, _DIRECTION_CHART)
        rows = list(csv.reader(io.StringIO(series["GraphCsvData"])))
        header = rows[0]
        cols = [i for i, h in enumerate(header) if h in windows]
        assert len(cols) == 12
        for row in rows[1:]:
            if row[0] in ("Migrant arrivals", "Net migration"):
                for i in cols:
                    row[i] = str(int(row[i]) + delta)
        out = io.StringIO()
        csv.writer(out, lineterminator="\n").writerows(rows)
        series["GraphCsvData"] = out.getvalue().rstrip("\n")

    _edit_page(site, month, edit)


def test_corrected_republication_adds_a_vintage_without_duplicates(rt, site) -> None:
    (july,) = _seed(rt, "2026-07")
    _ingest(rt, july)
    obs_before = _count(rt, "observation")
    _revise_consistently(site, "2026-07", "2010-01", 10)
    out = _ingest(rt, july)
    assert out.outcome == "ingested", out.detail
    assert repo.get_release(rt.conn, july)["status"] == ReleaseStatus.CORRECTED.value
    v = repo.list_vintages(rt.conn, "mig.m.arrivals")
    assert len(v) == 2
    first, second = (repo.vintage_points(rt.conn, i.vintage_id) for i in v)
    assert second["2010-01"].value == first["2010-01"].value + 10
    assert _count(rt, "observation") > obs_before
    assert _ingest(rt, july).outcome == "unchanged"  # same corrected bytes again


def test_inconsistent_correction_is_rejected_and_keeps_the_last_good_vintage(rt, site) -> None:
    (july,) = _seed(rt, "2026-07")
    assert _ingest(rt, july).outcome == "ingested"
    before = (_count(rt, "vintage"), _count(rt, "observation"))
    url = site.file_url("2026-07", "age_sex")
    # Monthly arrivals/net revised by 10, but the year-ended chart and citizenship split are not.
    site.override(url, 200, _bump(fixture_bytes("im_2026-07_age_sex.csv"), "2010-01", 10))
    out = _ingest(rt, july)
    assert out.outcome == "failed"
    assert "rolling_check" in (out.detail or "") and "citizenship_sum" in (out.detail or "")
    assert (_count(rt, "vintage"), _count(rt, "observation")) == before


def test_release_without_registered_adapter_is_skipped(rt) -> None:
    ref = next(
        r
        for r in events_to_refs(parse_ics(fixture_text("calendar_export_excerpt.ics")))
        if r.series_slug != "international-migration"
    )
    repo.upsert_release(rt.conn, ref, NOW)
    out = _ingest(rt, ref.release_key)
    assert out.outcome == "skipped_no_adapter" and _count(rt, "ingest_run") == 0


def test_unexpected_errors_are_classified_logged_and_not_disclosed(rt, monkeypatch, caplog) -> None:
    (july,) = _seed(rt, "2026-07")

    def boom(*a, **k):
        raise RuntimeError("parser exploded at /srv/internal/path.py")

    monkeypatch.setattr(rt.adapters["international-migration"], "parse", boom)
    out = _ingest(rt, july)
    assert out.outcome == "failed" and out.error_class is ErrorClass.UNEXPECTED
    # The stored (and API-served) detail names the exception type but never its message.
    assert "RuntimeError" in (out.detail or "")
    assert "parser exploded" not in (out.detail or "") and "/srv/internal" not in (out.detail or "")
    run = rt.conn.execute("SELECT detail FROM ingest_run ORDER BY id DESC LIMIT 1").fetchone()
    assert "parser exploded" not in (run["detail"] or "")
    health = rt.conn.execute("SELECT detail FROM source_health").fetchone()
    assert "parser exploded" not in (health["detail"] or "")
    # ...but the full exception is still available to the operator in the server log.
    assert "parser exploded" in caplog.text


def _month_payload(ref) -> bytes:
    stamp = ref.published_at.astimezone(AKL).strftime("%Y-%m-%d %H:%M:%S")
    path = ref.page_url.removeprefix("https://www.stats.govt.nz")
    return json.dumps(
        {
            "items": {
                "published": [
                    {
                        "ID": "1",
                        "PageLink": path,
                        "MetaDescription": "headline text for the release page",
                        "DateTaxonomyTerm": {"DisplayName": ref.title, "PublicationDate": stamp},
                    }
                ],
                "upcoming": [],
            }
        }
    ).encode()


def _empty_months(rt, site, *months: str) -> None:
    """Months in which Stats NZ lists no releases still answer 200 with empty lists."""
    for m in months:
        site.routes[f"{rt.settings.base_url}/api/v1/releaseCalendarMonth/{m}"] = (
            200,
            json.dumps({"items": {"published": [], "upcoming": []}}).encode(),
            "application/json",
        )


def test_backfill_ingests_releases_from_reference_period_in_order(rt, site) -> None:
    base = rt.settings.base_url
    _empty_months(rt, site, "2026-06", "2026-07", "2026-08", "2026-09", "2026-10")
    site.routes[f"{base}/api/v1/releaseCalendarMonth/2026-08"] = (
        200,
        _month_payload(release_ref_for("2026-06")),
        "application/json",
    )
    site.routes[f"{base}/api/v1/releaseCalendarMonth/2026-09"] = (
        200,
        _month_payload(release_ref_for("2026-07")),
        "application/json",
    )
    outcomes = backfill(rt, since="2026-06", until="2026-09", now_fn=lambda: NOW)
    assert [o.outcome for o in outcomes] == ["ingested", "ingested"]
    assert [o.release_key.split(":")[1] for o in outcomes] == ["june 2026", "july 2026"]


@pytest.mark.parametrize(
    ("until", "expected_periods"),
    [("2026-06", ["2026-06"]), ("2026-07", ["2026-06", "2026-07"])],
)
def test_backfill_only_ingests_the_inclusive_reference_period_interval(
    rt, site, until, expected_periods
) -> None:
    june, july = _seed(rt, "2026-06", "2026-07")
    august = replace(
        release_ref_for("2026-07"),
        release_key="international-migration:august 2026",
        title="International migration: August 2026",
        period_label="August 2026",
        reference_period="2026-08",
        published_at=NOW,
        page_url=page_url("2026-08"),
    )
    repo.upsert_release(rt.conn, august, NOW)
    # A release without a reference period cannot belong to a bounded interval.
    repo.upsert_release(
        rt.conn,
        replace(august, release_key="international-migration:unknown", reference_period=None),
        NOW,
    )
    _empty_months(rt, site, "2026-06", "2026-07", "2026-08", "2026-09", "2026-10")
    outcomes = backfill(rt, since="2026-06", until=until, now_fn=lambda: NOW)

    assert [o.release_key for o in outcomes] == [june, july][: len(expected_periods)]
    assert all(o.outcome == "ingested" for o in outcomes)
    stored_periods = rt.conn.execute(
        "SELECT DISTINCT r.reference_period FROM vintage v JOIN release r ON r.id = v.release_id"
        " ORDER BY r.reference_period"
    ).fetchall()
    assert [r[0] for r in stored_periods] == expected_periods
    assert page_url("2026-08") not in site.requests
    if until == "2026-06":
        assert page_url("2026-07") not in site.requests
    calendar_requests = [u.rsplit("/", 1)[1] for u in site.requests if "releaseCalendarMonth" in u]
    assert calendar_requests == ["2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]


def test_backfill_preserves_existing_vintages_outside_the_interval(rt, site) -> None:
    june, july = _seed(rt, "2026-06", "2026-07")
    assert _ingest(rt, july).outcome == "ingested"
    july_id = repo.get_release(rt.conn, july)["id"]
    before = [
        tuple(r) for r in rt.conn.execute("SELECT * FROM vintage WHERE release_id = ?", (july_id,))
    ]
    observations_before = repo.latest_points(rt.conn, "mig.m.net")
    # If July is fetched again, these revised bytes would create an unwanted vintage.
    site.override(
        site.file_url("2026-07", "age_sex"),
        200,
        _bump(fixture_bytes("im_2026-07_age_sex.csv"), "2010-01", 10),
    )
    site.requests.clear()
    _empty_months(rt, site, "2026-06", "2026-07", "2026-08", "2026-09", "2026-10")
    outcomes = backfill(rt, since="2026-06", until="2026-06", now_fn=lambda: NOW)

    assert [(o.release_key, o.outcome) for o in outcomes] == [(june, "ingested")]
    assert page_url("2026-07") not in site.requests
    assert [
        tuple(r) for r in rt.conn.execute("SELECT * FROM vintage WHERE release_id = ?", (july_id,))
    ] == before
    assert repo.latest_points(rt.conn, "mig.m.net") == observations_before
    assert repo.get_release(rt.conn, july)["status"] == "published"


def test_bounded_backfill_discovers_later_publications_in_the_reference_window(rt, site) -> None:
    # June's actual release was published in August. The calendar groups by publication month.
    _empty_months(rt, site, "2026-06", "2026-07", "2026-08", "2026-09", "2026-10")
    site.override(
        f"{rt.settings.base_url}/api/v1/releaseCalendarMonth/2026-08",
        200,
        _month_payload(release_ref_for("2026-06")),
        "application/json",
    )
    site.override(
        f"{rt.settings.base_url}/api/v1/releaseCalendarMonth/2026-09",
        200,
        _month_payload(release_ref_for("2026-07")),
        "application/json",
    )

    outcomes = backfill(rt, since="2026-06", until="2026-06", now_fn=lambda: NOW)

    assert [(o.release_key, o.outcome) for o in outcomes] == [
        ("international-migration:june 2026", "ingested")
    ]
    assert repo.get_release(rt.conn, "international-migration:july 2026") is None
    assert page_url("2026-07") not in site.requests
    assert [r[0] for r in rt.conn.execute("SELECT DISTINCT reference_period FROM release")] == [
        "2026-06"
    ]


@pytest.mark.parametrize(
    ("since", "until"),
    [
        ("0000-01", "0000-02"),
        ("2026-6", "2026-07"),
        ("2026-06", "2026-7"),
        ("2026-00", "2026-07"),
        ("2026-06", "2026-13"),
        ("2026-06 ", "2026-07"),
        ("2026-06", "2026-07\n"),
        ("", "2026-07"),
        ("2026-06", ""),
        ("2026-07", "2026-06"),
    ],
)
def test_backfill_rejects_invalid_bounds_before_network_or_database_changes(
    rt, site, since, until
) -> None:
    _seed(rt, "2026-06", "2026-07")
    before = rt.conn.total_changes
    with pytest.raises(ValueError):
        backfill(rt, since=since, until=until, now_fn=lambda: NOW)
    assert site.requests == []
    assert rt.conn.total_changes == before


def test_a_concurrent_duplicate_ingest_does_not_mark_the_release_corrected(rt, monkeypatch) -> None:
    """Two processes both pass the pre-check; the loser must not flip `published` to `corrected`."""
    import nzstats.pipeline.ingest as ingest_module

    (july,) = _seed(rt, "2026-07")
    assert _ingest(rt, july).outcome == "ingested"
    monkeypatch.setattr(ingest_module.repo, "has_vintage", lambda *a, **k: False)  # stale pre-check
    out = _ingest(rt, july)
    assert out.outcome == "unchanged"
    assert repo.get_release(rt.conn, july)["status"] == "published"


# --- page-derived charts take part in "unchanged" detection (review #4245952768) ---------------

_DATA_VALUE = re.compile(r'data-value="([^"]+)"')
_CITIZENSHIP_CHART = "Estimated migration by citizenship, rolling year ended"
_DIRECTION_CHART = "Estimated migration by direction, rolling year ended"


def _edit_page(site, month: str, edit) -> None:
    """Rewrite the release page's embedded JSON object (as served by the fake site)."""
    url = page_url(month)
    status, body, ctype = site.routes[url]
    text = body.decode("utf-8")
    for match in _DATA_VALUE.finditer(text):
        raw = html.unescape(match.group(1))
        if raw.startswith("{") and "PageBlocks" in raw:
            obj = json.loads(raw)
            edit(obj)
            replaced = f'data-value="{html.escape(json.dumps(obj), quote=True)}"'
            site.override(
                url,
                status,
                (text[: match.start()] + replaced + text[match.end() :]).encode(),
                ctype,
            )
            return
    raise AssertionError("fixture page has no embedded data object")


def _chart_series(obj, title_prefix: str):
    return next(
        s
        for b in obj["PageBlocks"]
        if b.get("ClassName") == "GraphTableBlock"
        for s in b["SeriesData"]
        if (s.get("Title") or "").startswith(title_prefix)
    )


def _drop_chart(title_prefix: str):
    def edit(obj) -> None:
        for b in obj["PageBlocks"]:
            if b.get("ClassName") == "GraphTableBlock":
                b["SeriesData"] = [
                    s
                    for s in b["SeriesData"]
                    if not (s.get("Title") or "").startswith(title_prefix)
                ]

    return edit


def _bump_net_rolling(obj) -> None:
    series = _chart_series(obj, _DIRECTION_CHART)
    lines = series["GraphCsvData"].splitlines()
    row = next(i for i, ln in enumerate(lines) if ln.startswith('"Net migration"'))
    cells = lines[row].split(",")
    # Earliest year-ended point, moved by a rounding-sized 1 (the validator allows 5): the test is
    # about the chart changing the digest, not about a revision large enough to be rejected.
    cells[1] = str(int(cells[1]) + 1)
    lines[row] = ",".join(cells)
    series["GraphCsvData"] = "\n".join(lines)


def test_corrected_embedded_chart_with_identical_files_adds_a_vintage(rt, site) -> None:
    (july,) = _seed(rt, "2026-07")
    assert _ingest(rt, july).outcome == "ingested"
    first = repo.latest_points(rt.conn, "mig.ry.net")
    _edit_page(site, "2026-07", _bump_net_rolling)
    out = _ingest(rt, july)
    assert out.outcome == "ingested", out.detail
    assert repo.get_release(rt.conn, july)["status"] == ReleaseStatus.CORRECTED.value
    vintages = repo.list_vintages(rt.conn, "mig.ry.net")
    assert len(vintages) == 2
    second = repo.vintage_points(rt.conn, vintages[1].vintage_id)
    assert repo.vintage_points(rt.conn, vintages[0].vintage_id) == first
    changed = {p for p in second if second[p].value != first[p].value}
    assert changed and len(changed) == 1
    assert _ingest(rt, july).outcome == "unchanged"  # the corrected page is itself stable


def test_optional_chart_published_later_is_picked_up_without_file_changes(rt, site) -> None:
    (july,) = _seed(rt, "2026-07")
    full_page = site.routes[page_url("2026-07")]
    _edit_page(site, "2026-07", _drop_chart(_CITIZENSHIP_CHART))
    out = _ingest(rt, july)
    assert out.outcome == "ingested", out.detail
    assert not repo.latest_points(rt.conn, "mig.ry.arrivals.nz")
    site.routes[page_url("2026-07")] = full_page  # Stats NZ adds the citizenship chart back
    out = _ingest(rt, july)
    assert out.outcome == "ingested", out.detail
    assert repo.latest_points(rt.conn, "mig.ry.arrivals.nz")
    # The newly available series has exactly one vintage, not one per re-ingest.
    assert len(repo.list_vintages(rt.conn, "mig.ry.arrivals.nz")) == 1


def test_volatile_page_markup_outside_the_charts_does_not_create_a_vintage(rt, site) -> None:
    (july,) = _seed(rt, "2026-07")
    assert _ingest(rt, july).outcome == "ingested"
    before = (_count(rt, "vintage"), _count(rt, "observation"))
    url = page_url("2026-07")
    status, body, ctype = site.routes[url]
    noisy = body.replace(b"</body>", b"<!-- render 20261012T0800 nonce=8f3a --></body>")
    assert noisy != body
    site.override(url, status, noisy, ctype)
    assert _ingest(rt, july).outcome == "unchanged"
    assert (_count(rt, "vintage"), _count(rt, "observation")) == before
    assert repo.get_release(rt.conn, july)["status"] == "published"


def test_backfill_reports_a_month_whose_discovery_failed(rt, site) -> None:
    """Review #4246272300: a failed month must not leave a silent gap in the backfill result."""
    base = rt.settings.base_url
    _empty_months(rt, site, "2026-06", "2026-07")
    site.routes[f"{base}/api/v1/releaseCalendarMonth/2026-08"] = (503, b"", "text/html")
    site.routes[f"{base}/api/v1/releaseCalendarMonth/2026-09"] = (
        200,
        _month_payload(release_ref_for("2026-07")),
        "application/json",
    )
    outcomes = backfill(rt, since="2026-06", until="2026-09", now_fn=lambda: NOW)
    failed = [o for o in outcomes if o.outcome == "failed"]
    assert [o.release_key for o in failed] == ["calendar_month:2026-08"]
    assert "calendar_month" in (failed[0].detail or "")
    assert [o.outcome for o in outcomes if o.outcome != "failed"] == ["ingested"]  # the rest ran


def test_backfill_of_healthy_months_reports_no_failure(rt, site) -> None:
    base = rt.settings.base_url
    _empty_months(rt, site, "2026-07", "2026-08")
    site.routes[f"{base}/api/v1/releaseCalendarMonth/2026-09"] = (
        200,
        _month_payload(release_ref_for("2026-07")),
        "application/json",
    )
    outcomes = backfill(rt, since="2026-07", until="2026-09", now_fn=lambda: NOW)
    assert [o.outcome for o in outcomes] == ["ingested"]


# --- source health follows the outstanding failures (review #4253658288) ------------------------


def _health(rt):
    return rt.conn.execute(
        "SELECT * FROM source_health WHERE source = 'release:international-migration'"
    ).fetchone()


def _break_june(site) -> None:
    url = site.file_url("2026-06", "age_sex")
    site.override(url, 200, _drop_month(fixture_bytes("im_2026-06_age_sex.csv"), "2015-05"))


def test_a_later_success_does_not_clear_another_releases_failure(rt, site) -> None:
    june, july = _seed(rt, "2026-06", "2026-07")
    _break_june(site)
    assert _ingest(rt, june).outcome == "failed"
    assert _ingest(rt, july).outcome == "ingested"  # a different release succeeds afterwards
    assert _ingest(rt, july).outcome == "unchanged"
    health = _health(rt)
    assert health["state"] == "degraded" and "june 2026" in health["detail"]


def test_the_failure_clears_when_that_same_release_recovers(rt, site) -> None:
    june, july = _seed(rt, "2026-06", "2026-07")
    _break_june(site)
    _ingest(rt, june)
    _ingest(rt, july)
    site.override(site.file_url("2026-06", "age_sex"), 200, fixture_bytes("im_2026-06_age_sex.csv"))
    assert _ingest(rt, june).outcome == "ingested"
    health = _health(rt)
    assert health["state"] == "ok" and health["detail"] is None


def test_every_outstanding_failure_is_named_until_each_recovers(rt, site) -> None:
    june, july = _seed(rt, "2026-06", "2026-07")
    _break_june(site)
    site.override(
        site.file_url("2026-07", "age_sex"),
        200,
        _drop_month(fixture_bytes("im_2026-07_age_sex.csv"), "2015-05"),
    )
    assert _ingest(rt, june).outcome == "failed" and _ingest(rt, july).outcome == "failed"
    detail = _health(rt)["detail"]
    assert "june 2026" in detail and "july 2026" in detail
    site.override(site.file_url("2026-07", "age_sex"), 200, fixture_bytes("im_2026-07_age_sex.csv"))
    assert _ingest(rt, july).outcome == "ingested"
    health = _health(rt)
    assert health["state"] == "degraded" and "june 2026" in health["detail"]
    assert "july 2026" not in health["detail"]


# --- empty optional series are unavailable, not a 500 (review #4253658294) ----------------------


def _blank_row(label: str, *, last_only: bool = False):
    def edit(obj) -> None:
        series = _chart_series(obj, _CITIZENSHIP_CHART)
        rows = list(csv.reader(io.StringIO(series["GraphCsvData"])))
        for row in rows:
            if row and row[0].strip() == label:
                if last_only:
                    row[-1] = ".."
                else:
                    row[1:] = [".."] * len(row[1:])
        out = io.StringIO()
        csv.writer(out, quoting=csv.QUOTE_ALL, lineterminator="\n").writerows(rows)
        series["GraphCsvData"] = out.getvalue()

    return edit


def test_an_all_blank_optional_series_is_not_stored_and_the_analysis_still_builds(rt, site) -> None:
    from nzstats.insights.migration import build_release_analysis

    (july,) = _seed(rt, "2026-07")
    _edit_page(site, "2026-07", _blank_row("Net migration (NZ citizens)"))
    out = _ingest(rt, july)
    assert out.outcome == "ingested", out.detail
    assert any("mig.ry.net.nz" in w for w in out.warnings)
    assert not repo.list_vintages(rt.conn, "mig.ry.net.nz")  # no empty vintage was written
    release_id = repo.get_release(rt.conn, july)["id"]
    analysis = build_release_analysis(
        rt.conn, release_id, analysable_slugs={"international-migration"}
    )
    assert analysis is not None and "mig.ry.net.nz" not in analysis.model_dump_json()


def test_an_already_stored_empty_optional_vintage_does_not_break_the_analysis(rt) -> None:
    from nzstats.adapters.migration import series as S
    from nzstats.insights.migration import build_release_analysis

    (july,) = _seed(rt, "2026-07")
    assert _ingest(rt, july).outcome == "ingested"
    release_id = repo.get_release(rt.conn, july)["id"]
    series_id = repo.upsert_series(rt.conn, S.rolling_def("net", "nz"))
    rt.conn.execute(  # leave the stored vintage in place but without observations
        "DELETE FROM observation WHERE vintage_id IN"
        " (SELECT id FROM vintage WHERE series_id=? AND release_id=?)",
        (series_id, release_id),
    )
    analysis = build_release_analysis(
        rt.conn, release_id, analysable_slugs={"international-migration"}
    )
    assert analysis is not None
    assert not any(i.id == "citizenship" for i in analysis.context)


# --- partially blank charts must not be presented as aligned data (review #4253711085/-094) -----


def test_citizenship_insight_is_suppressed_when_the_two_series_end_in_different_periods(
    rt, site
) -> None:
    """A blank latest NZ cell leaves its series a month behind; one period label cannot cover both."""
    from nzstats.insights.migration import build_release_analysis

    (july,) = _seed(rt, "2026-07")
    assert _ingest(rt, july).outcome == "ingested"
    release_id = repo.get_release(rt.conn, july)["id"]
    slugs = {"international-migration"}
    assert any(
        i.id == "citizenship"
        for i in build_release_analysis(rt.conn, release_id, analysable_slugs=slugs).context
    )

    _edit_page(site, "2026-07", _blank_row("Net migration (NZ citizens)", last_only=True))
    assert _ingest(rt, july).outcome == "ingested"
    nz = repo.latest_points(rt.conn, "mig.ry.net.nz")
    nonnz = repo.latest_points(rt.conn, "mig.ry.net.nonnz")
    assert max(nz) < max(nonnz)  # the premise: the NZ series now ends a month earlier
    analysis = build_release_analysis(rt.conn, release_id, analysable_slugs=slugs)
    assert analysis is not None
    assert not any(i.id == "citizenship" for i in analysis.context)
