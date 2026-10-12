import io
import json

import pandas as pd

from nzstats.clock import AKL
from nzstats.domain import ErrorClass, ReleaseStatus
from nzstats.pipeline.ingest import backfill, ingest_release
from nzstats.sources.calendar import events_to_refs, parse_ics
from nzstats.stats.revision import revisions
from nzstats.store import repo
from tests.conftest import FIXTURES, fixture_bytes, fixture_text
from tests.support import NOW, release_ref_for


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


def test_page_live_but_data_file_missing_is_not_available_and_writes_no_vintage(rt, site) -> None:
    (july,) = _seed(rt, "2026-07")
    site.override(site.file_url("2026-07", "citizenship_visa_country"), 404, b"", "text/html")
    out = _ingest(rt, july)
    assert out.outcome == "not_available" and out.error_class is ErrorClass.NOT_FOUND
    assert _count(rt, "vintage") == 0 and _count(rt, "observation") == 0
    assert _count(rt, "source_health") == 0  # polling before files exist is not a failure


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


def test_corrected_republication_adds_a_vintage_without_duplicates(rt, site) -> None:
    (july,) = _seed(rt, "2026-07")
    _ingest(rt, july)
    obs_before = _count(rt, "observation")
    url = site.file_url("2026-07", "age_sex")
    site.override(url, 200, _bump(fixture_bytes("im_2026-07_age_sex.csv"), "2010-01", 10))
    out = _ingest(rt, july)
    assert out.outcome == "ingested", out.detail
    assert repo.get_release(rt.conn, july)["status"] == ReleaseStatus.CORRECTED.value
    v = repo.list_vintages(rt.conn, "mig.m.arrivals")
    assert len(v) == 2
    first, second = (repo.vintage_points(rt.conn, i.vintage_id) for i in v)
    assert second["2010-01"].value == first["2010-01"].value + 10
    assert _count(rt, "observation") > obs_before
    assert _ingest(rt, july).outcome == "unchanged"  # same corrected bytes again


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


def test_backfill_ingests_releases_from_reference_period_in_order(rt, site) -> None:
    base = rt.settings.base_url
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


def test_a_concurrent_duplicate_ingest_does_not_mark_the_release_corrected(rt, monkeypatch) -> None:
    """Two processes both pass the pre-check; the loser must not flip `published` to `corrected`."""
    import nzstats.pipeline.ingest as ingest_module

    (july,) = _seed(rt, "2026-07")
    assert _ingest(rt, july).outcome == "ingested"
    monkeypatch.setattr(ingest_module.repo, "has_vintage", lambda *a, **k: False)  # stale pre-check
    out = _ingest(rt, july)
    assert out.outcome == "unchanged"
    assert repo.get_release(rt.conn, july)["status"] == "published"
