"""Phase 4C: GDP and labour market dashboards in the public snapshot, optional until their data exists."""

import json
import sqlite3

from nzstats.publish.contract import known_kind
from nzstats.publish.reconcile import reconcile_with_database
from nzstats.publish.snapshot import export_snapshot
from nzstats.publish.validate import validate_snapshot
from tests.publish.conftest import EXPORT_NOW

FILES = ("gdp.json", "labour-market.json")


def payload(snapshot, name):
    return json.loads((snapshot / name).read_text())["payload"]


def test_both_dashboards_are_known_snapshot_files():
    assert known_kind("gdp.json") == "gdp" and known_kind("labour-market.json") == "labour-market"


def test_snapshot_carries_both_dashboards_as_the_api_serves_them(snapshot):
    manifest = json.loads((snapshot / "manifest.json").read_text())
    for name in FILES:
        assert name in manifest["files"]
    assert payload(snapshot, "gdp.json")["reference_period"] == "2026-06"
    assert payload(snapshot, "labour-market.json")["reference_period"] == "2026-06"


def test_a_snapshot_with_both_validates(snapshot):
    report = validate_snapshot(snapshot, now=EXPORT_NOW)
    assert report.errors == [], report.errors


def test_without_their_data_the_files_are_absent_and_the_snapshot_still_validates(
    without_macro_dir, tmp_path
):
    out = tmp_path / "snap"
    export_snapshot(without_macro_dir, out, now=EXPORT_NOW, allow_fixtures=True)
    assert not any((out / name).exists() for name in FILES)
    assert validate_snapshot(out, now=EXPORT_NOW).errors == []


def test_published_values_are_reconciled_with_the_database(full_dir, snapshot):
    payloads = {p.relative_to(snapshot).as_posix(): json.loads(p.read_text())["payload"]
                for p in snapshot.rglob("*.json") if p.name != "manifest.json"}  # fmt: skip
    conn = sqlite3.connect(full_dir / "nzstats.db")
    conn.row_factory = sqlite3.Row
    assert reconcile_with_database(payloads, conn) == []
    payloads["gdp.json"]["series"][0]["points"][-1]["value"] += 1
    payloads["labour-market.json"]["series"][0]["points"][-1]["value"] += 0.1
    problems = reconcile_with_database(payloads, conn)
    assert any("gdp." in p for p in problems) and any("hlfs." in p for p in problems)
