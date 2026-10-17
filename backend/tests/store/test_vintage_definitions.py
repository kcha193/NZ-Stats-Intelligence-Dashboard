from dataclasses import replace

from nzstats.domain import Adjustment, Frequency, SeriesDef
from nzstats.store import repo
from tests.support import NOW, release_ref_for


def test_definitions_are_immutable_per_vintage_and_latest_follows_publication(rt):
    old = SeriesDef(
        "ect.m.sa.retail.value",
        "Retail",
        "NZD million",
        Frequency.MONTHLY,
        Adjustment.SEASONALLY_ADJUSTED,
        "Original methodology",
        "ect-v1",
        "ect",
    )
    rid = repo.upsert_release(rt.conn, release_ref_for("2026-06"), NOW)
    sid = repo.upsert_series(rt.conn, old)
    v1 = repo.create_vintage(rt.conn, rid, sid, NOW, "release_files", "v1", "a")
    new = replace(old, unit="NZD", definition="New methodology", definition_id="ect-v2")
    rid2 = repo.upsert_release(rt.conn, release_ref_for("2026-07"), NOW)
    repo.upsert_series(rt.conn, new)
    v2 = repo.create_vintage(rt.conn, rid2, sid, NOW, "release_files", "v2", "b")
    assert repo.get_series_row(rt.conn, old.key, v1)["unit"] == "NZD million"
    assert repo.get_series_row(rt.conn, old.key, v2)["definition_id"] == "ect-v2"
    repo.upsert_series(rt.conn, old)  # an older backfill must not relabel the newest vintage
    assert repo.get_series_row(rt.conn, old.key)["unit"] == "NZD"
    assert repo.bundle_series(rt.conn, rid, "a")[0][0] == old
    overview = next(r for r in repo.series_overview(rt.conn) if r["key"] == old.key)
    assert overview["unit"] == "NZD"


def test_revision_view_declines_incompatible_vintage_metadata(rt):
    from nzstats.domain import Observation, ObsStatus
    from nzstats.insights.revisions import revision_view

    d = SeriesDef(
        "ect.m.sa.retail.value",
        "Retail",
        "NZD million",
        Frequency.MONTHLY,
        Adjustment.SEASONALLY_ADJUSTED,
        "First",
        "v1",
        "ect",
    )
    for i, month in enumerate(("2026-06", "2026-07")):
        rid = repo.upsert_release(rt.conn, release_ref_for(month), NOW)
        sid = repo.upsert_series(rt.conn, replace(d, definition_id=f"v{i + 1}"))
        vid = repo.create_vintage(rt.conn, rid, sid, NOW, "release_files", "v1", str(i))
        repo.insert_observations(
            rt.conn, vid, [Observation(d.key, "2026-06", 100 + i, ObsStatus.FINAL)]
        )
    result = revision_view(rt.conn, d.key)
    assert result.n_common == 0
    assert "incompatible" in result.coverage.note.lower()


def test_correction_with_changed_units_does_not_compare_incompatible_numbers(rt):
    from nzstats.domain import Observation, ObsStatus
    from nzstats.insights.migration import _corrections

    d = SeriesDef(
        "ect.m.sa.retail.value",
        "Retail",
        "NZD million",
        Frequency.MONTHLY,
        Adjustment.SEASONALLY_ADJUSTED,
        "Method",
        "v1",
        "ect",
    )
    rid = repo.upsert_release(rt.conn, release_ref_for("2026-07"), NOW)
    for unit, digest, value in [("NZD million", "a", 100), ("NZD", "b", 100_000_000)]:
        sid = repo.upsert_series(rt.conn, replace(d, unit=unit))
        vid = repo.create_vintage(rt.conn, rid, sid, NOW, "release_files", "v1", digest)
        repo.insert_observations(
            rt.conn, vid, [Observation(d.key, "2026-07", value, ObsStatus.FINAL)]
        )
    vintage = repo.release_vintage(rt.conn, d.key, rid)
    block = _corrections(rt.conn, rid, "b", vintage, primary_key=d.key)
    assert block.available is False
    assert "incompatible" in block.note.lower()
