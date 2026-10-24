import json
from datetime import UTC, datetime
from pathlib import Path

from nzstats.publish.leaks import scan_for_leaks
from nzstats.publish.validate import validate_snapshot


def rehash(root: Path, name: str) -> None:
    import hashlib

    manifest = json.loads((root / "manifest.json").read_text())
    data = (root / name).read_bytes()
    manifest["files"][name]["sha256"] = hashlib.sha256(data).hexdigest()
    manifest["files"][name]["bytes"] = len(data)
    (root / "manifest.json").write_text(json.dumps(manifest))


def mutate(root: Path, name: str, change) -> None:
    env = json.loads((root / name).read_text())
    change(env["payload"])
    (root / name).write_text(
        json.dumps(env, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"
    )
    rehash(root, name)


def test_a_fixture_snapshot_is_valid_but_not_publishable(snapshot):
    assert validate_snapshot(snapshot).ok
    report = validate_snapshot(snapshot, for_publish=True)
    assert any("only production data" in e for e in report.errors)


def test_a_tampered_file_is_detected(snapshot):
    path = snapshot / "cpi.json"
    path.write_text(path.read_text().replace("2026", "2025", 1))
    assert any("manifest hash" in e for e in validate_snapshot(snapshot).errors)


def test_an_unlisted_file_is_rejected(snapshot):
    (snapshot / "notes.txt").write_text("hello")
    assert any("not listed" in e for e in validate_snapshot(snapshot).errors)


def test_a_missing_required_file_is_rejected(snapshot):
    (snapshot / "ect.json").unlink()
    errors = validate_snapshot(snapshot).errors
    assert any("ect.json is listed in the manifest but missing" in e for e in errors)


def test_a_file_from_another_snapshot_is_rejected(snapshot):
    path = snapshot / "overview.json"
    env = json.loads(path.read_text())
    env["snapshot_id"] = "0" * 64
    path.write_text(json.dumps(env, sort_keys=True, separators=(",", ":")) + "\n")
    rehash(snapshot, "overview.json")
    assert any("different snapshot" in e for e in validate_snapshot(snapshot).errors)


def test_an_unknown_field_is_rejected_as_an_internal_leak(snapshot):
    mutate(snapshot, "overview.json", lambda p: p.update(db_path="x"))
    assert any("outside the public response model" in e for e in validate_snapshot(snapshot).errors)


def test_private_text_is_rejected(snapshot):
    mutate(
        snapshot,
        "health.json",
        lambda p: p["sources"][0].update(detail="/Users/kevin/data/x.db boom"),
    )
    errors = validate_snapshot(snapshot).errors
    assert any("filesystem path" in e for e in errors) and any("database file" in e for e in errors)


def test_evidence_must_cite_a_published_release(snapshot):
    def change(p):
        p["analysis"]["executive_summary"][0]["evidence"][0]["release_key"] = "no-such-release"

    mutate(snapshot, "cpi.json", change)
    assert any("not a published release" in e for e in validate_snapshot(snapshot).errors)


def test_a_headline_that_disagrees_with_its_series_is_rejected(snapshot):
    def change(p):
        for k in p["kpis"]:
            if k["metric"]["series_key"].startswith("mig."):
                k["metric"]["value"] += 1
                return

    mutate(snapshot, "overview.json", change)
    assert any(
        "does not equal the published series" in e for e in validate_snapshot(snapshot).errors
    )


def test_a_snapshot_without_verified_data_is_rejected(snapshot):
    mutate(snapshot, "overview.json", lambda p: p.update(data_updated_at=None))
    manifest = json.loads((snapshot / "manifest.json").read_text())
    manifest["data_updated_at"] = None
    (snapshot / "manifest.json").write_text(json.dumps(manifest))
    assert any("no data has been verified" in e for e in validate_snapshot(snapshot).errors)


def test_a_stale_calendar_is_a_warning_not_an_error(snapshot):
    later = datetime(2026, 12, 1, tzinfo=UTC)
    report = validate_snapshot(snapshot, now=later)
    assert report.ok and any("calendar" in w for w in report.warnings)


def test_leak_scanner_findings():
    assert scan_for_leaks("see https://www.stats.govt.nz/assets/data/x.csv") == []
    assert scan_for_leaks("contact a.b@example.com")
    assert scan_for_leaks("NETLIFY_AUTH_TOKEN=abc")
    assert scan_for_leaks("clean", extra=("clean",))
