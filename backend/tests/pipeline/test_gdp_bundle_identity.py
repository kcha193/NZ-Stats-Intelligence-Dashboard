"""Upgrade legacy GDP wording without changing retained statistical history."""

from dataclasses import replace

import pytest

from nzstats.adapters.gdp.adapter import GdpAdapter
from nzstats.adapters.gdp.series import BY_KEY
from nzstats.clock import from_utc_iso
from nzstats.domain import Adjustment, Frequency, Observation, ObsStatus, ReleaseStatus
from nzstats.insights.vintages import first_stored
from nzstats.pipeline.ingest import _bundle_digest
from nzstats.sources.release_page import parse_release_page
from nzstats.store import repo
from nzstats.store.db import transaction
from tests.conftest import fixture_text
from tests.macro_support import NOW, gdp_files, ingest, seed
from tests.support import BASE

REAL_LEVELS = (
    "gdp.production.cv.sa",
    "gdp.production.cv.nsa",
    "gdp.expenditure.cv.sa",
    "gdp.expenditure.cv.nsa",
)
OLD_UNIT = "NZD million (2009/10 prices)"
# Frozen pre-Phase-4D data-v1 digest of the March fixture with its original four unit labels.
LEGACY_DIGEST = "data-v1:f644e3871bc57810e1c0c219b3928900812573f2a83b223b4dc00d335e794e1a"
SLUG = "gross-domestic-product"
HEADLINE = REAL_LEVELS[0]
QOQ = "gdp.production.cv.sa.pct_qoq"


def _legacy_release(rt, site, digest):
    """Insert an old installed bundle directly; never run it through the new identity function."""
    files = gdp_files("2026-03")
    key = seed(rt, site, "gdp_2026-03_page.html", files)
    row = repo.get_release(rt.conn, key)
    page = parse_release_page(fixture_text("gdp_2026-03_page.html"), BASE)
    bundle = GdpAdapter().parse(page, files)
    with transaction(rt.conn):
        for url in (row["page_url"], bundle.series[0].definition.source_url):
            result = rt.fetcher.get(url, expect=("text/html", "text/csv"))
            repo.record_artifact(rt.conn, rt.artifacts.save(result))
        for ps in bundle.series:
            definition = ps.definition
            if definition.key in REAL_LEVELS:
                definition = replace(definition, unit=OLD_UNIT)
            sid = repo.upsert_series(rt.conn, definition)
            vid = repo.create_vintage(
                rt.conn,
                row["id"],
                sid,
                from_utc_iso(row["published_at"]),
                "release_files",
                bundle.layout_version,
                digest,
            )
            repo.insert_observations(rt.conn, vid, ps.observations)
    return key, row["id"]


def _history(rt):
    tables = (
        "release",
        "series",
        "vintage",
        "vintage_series_definition",
        "observation",
        "raw_artifact",
    )
    return {
        t: [tuple(row) for row in rt.conn.execute(f"SELECT * FROM {t} ORDER BY 1, 2")]
        for t in tables
    }


def _raw_bytes(rt):
    return {p.relative_to(rt.artifacts.root): p.read_bytes() for p in rt.artifacts.files()}


def _original(rt, key):
    return first_stored(rt.conn, SLUG, QOQ, repo.get_release(rt.conn, key)["published_at"])


@pytest.mark.parametrize("digest", [LEGACY_DIGEST, "f" * 64])
@pytest.mark.parametrize("status", [ReleaseStatus.PUBLISHED, ReleaseStatus.CORRECTED])
def test_identical_gdp_upgrade_preserves_every_historical_row(rt, site, digest, status):
    key, rid = _legacy_release(rt, site, digest)
    repo.set_release_status(rt.conn, key, status, NOW)
    before, raw, original = _history(rt), _raw_bytes(rt), _original(rt, key)
    assert len(raw) == 2 and original[0].is_publication
    for _ in range(2):
        outcome = ingest(rt, key)
        assert outcome.outcome == "unchanged", outcome.detail
        assert repo.release_bundle(rt.conn, rid) == digest
        assert _history(rt) == before  # includes activation, capture times and original definitions
        assert _raw_bytes(rt) == raw
        assert _original(rt, key) == original


def test_gdp_upgrade_detects_correction_and_restores_the_legacy_bundle(rt, site):
    key, rid = _legacy_release(rt, site, LEGACY_DIGEST)
    before, raw, original = _history(rt), _raw_bytes(rt), _original(rt, key)
    url = next(
        u for u in site.routes if u.endswith("gross-domestic-product-march-2026-quarter.csv")
    )
    response = site.routes[url]
    # One real statistical difference, small enough to retain the published growth reconciliation.
    changed = response[1].replace(
        b"SNEQ.SG01RSC00B01,1987.06,27977,", b"SNEQ.SG01RSC00B01,1987.06,27978,"
    )
    assert changed != response[1]
    site.override(url, 200, changed, "text/csv")
    outcome = ingest(rt, key)
    assert outcome.outcome == "ingested", outcome.detail
    corrected = repo.release_bundle(rt.conn, rid)
    assert corrected != LEGACY_DIGEST
    assert repo.get_release(rt.conn, key)["status"] == "corrected"
    assert repo.latest_points(rt.conn, HEADLINE)["1987-06"].value == 27978
    after_correction = _history(rt)
    assert len(after_correction["vintage"]) == 24
    # The active data-v1 digest fast path must also leave the entire history intact.
    assert ingest(rt, key).outcome == "unchanged"
    assert _history(rt) == after_correction

    site.override(url, *response)
    outcome = ingest(rt, key)
    assert outcome.outcome == "ingested", outcome.detail
    assert repo.release_bundle(rt.conn, rid) == LEGACY_DIGEST
    assert repo.latest_points(rt.conn, HEADLINE)["1987-06"].value == 27977
    after = _history(rt)
    assert len(after["vintage"]) == 24  # reactivation, never a third bundle
    for table in ("vintage_series_definition", "observation"):
        assert after[table] == after_correction[table]
        assert after[table][: len(before[table])] == before[table]
    assert _original(rt, key) == original
    assert _raw_bytes(rt).items() >= raw.items()
    final = _history(rt)
    assert ingest(rt, key).outcome == "unchanged"
    assert _history(rt) == final


@pytest.mark.parametrize("key", REAL_LEVELS)
def test_only_the_legacy_gdp_level_wording_is_equivalent(key):
    definition = BY_KEY[key].definition
    obs = (Observation(key, "2026-03", 27977, ObsStatus.FINAL),)
    assert _bundle_digest([(replace(definition, unit=OLD_UNIT), obs)]) == _bundle_digest(
        [(definition, obs)]
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"unit": "NZD billion (chain volume)"},
        {"unit": "NZD million (current prices)"},
        {"unit": "NZD million (2017/18 prices)"},
        {"frequency": Frequency.MONTHLY},
        {"adjustment": Adjustment.NONE},
        {"definition_id": "gdp.production.cv.sa.v2"},
        {"key": "gdp.production.cv.other"},
    ],
)
def test_gdp_measurement_changes_remain_distinct(changes):
    definition = BY_KEY[HEADLINE].definition
    obs = (Observation(HEADLINE, "2026-03", 27977, ObsStatus.FINAL),)
    assert _bundle_digest([(replace(definition, **changes), obs)]) != _bundle_digest(
        [(definition, obs)]
    )


@pytest.mark.parametrize(
    "key", ["gdp.expenditure.cp.sa", "gdp.per_capita.production.cv.sa", "other.cv.sa"]
)
def test_legacy_wording_alias_does_not_apply_to_other_series(key):
    definition = replace(BY_KEY[HEADLINE].definition, key=key)
    obs = (Observation(key, "2026-03", 27977, ObsStatus.FINAL),)
    assert _bundle_digest([(replace(definition, unit=OLD_UNIT), obs)]) != _bundle_digest(
        [(definition, obs)]
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"value": 27978},
        {"status": ObsStatus.UNKNOWN},
        {"std_error": 1.0},
        {"released_in": "2026-06"},
        {"period": "2025-12"},
    ],
)
def test_gdp_observation_changes_remain_distinct(changes):
    definition = BY_KEY[HEADLINE].definition
    obs = Observation(HEADLINE, "2026-03", 27977, ObsStatus.FINAL)
    assert _bundle_digest([(definition, (replace(obs, **changes),))]) != _bundle_digest(
        [(definition, (obs,))]
    )
