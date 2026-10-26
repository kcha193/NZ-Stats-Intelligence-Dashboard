"""Research data must never reach the public snapshot or change any Stats NZ API answer."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nzstats.api.app import create_app
from nzstats.config import load_settings
from nzstats.publish.contract import is_stats_nz_url
from nzstats.publish.snapshot import export_snapshot
from nzstats.publish.validate import validate_snapshot
from nzstats.research import store
from nzstats.research import summary_store as ss
from nzstats.research.contract import ForecastClaim
from nzstats.store.db import connect, migrate, transaction

from .conftest import EXPORT_NOW

NOW = datetime(2026, 10, 25, 1, 0, tzinfo=UTC)
TEXT = "SYNTHETIC FIXTURE research text that must never be published. https://www.anz.co.nz/x"


def seed_research(data_dir: Path) -> None:
    conn = connect(data_dir / "nzstats.db")
    migrate(conn)
    with transaction(conn):
        inst = store.upsert_institution(conn, key="anz", name="ANZ", review_status="approved",
                                        content_policy="full_text", now=NOW)  # fmt: skip
        pub, _ = store.upsert_publication(
            conn, inst, doc_key="anz:www.anz.co.nz/x", url="https://www.anz.co.nz/x", title=TEXT,
            series="outlook", categories=["economic_outlook"], published_on="2026-08-13",
            published_at=None, precision="day", content_status="link_only", now=NOW,
        )  # fmt: skip
        version, _ = store.add_version(
            conn, pub, content_sha256="c" * 64, text_sha256="t" * 64, fmt="html", fetched_at=NOW,
            extractor_version="html-1", raw_artifact_id=None, title=TEXT,
            sections=[store.SectionRow(0, "Outlook", TEXT, None, None, 0, len(TEXT))],
            page_count=None, licence_snapshot="{}", now=NOW,
        )  # fmt: skip
        run = store.record_run(conn, inst, started_at=NOW, finished_at=NOW, outcome="ok",
                               dry_run=False, counts={"new": 1}, error_class=None, detail=None)  # fmt: skip
        store.record_item(conn, run, url="https://www.anz.co.nz/x", outcome="new", error_class=None,
                          detail=None, publication_id=pub, version_id=version)  # fmt: skip
        store.set_health(conn, inst, state="ok", now=NOW, success=True, detail=None)
    seed_summary(conn, version)
    conn.close()


def seed_summary(conn, version: int) -> None:
    """A verified, approved Phase 3B summary with a claim, usage and a review decision."""
    key = ss.SummaryKey(version, "fake", "fake-1", "outlook-v1", "3b-1", "a" * 64)
    run = ss.start_run(conn, provider="fake", model="fake-1", hosted=False, prompt_version="outlook-v1",
                       processing_version="3b-1", limits={}, dry_run=False, now=NOW)  # fmt: skip
    claim = ForecastClaim(indicator="gdp", indicator_label=TEXT[:100], horizon="2027", value=9.9,
                          unit="percent", direction="up", evidence=[{"version_id": version,
                          "section_ordinal": 0, "quote": TEXT[:60]}])  # fmt: skip
    with transaction(conn):
        sid = ss.insert_summary(conn, key, run_id=run, attempt=1, hosted=False, verifier_version="v",
                                parameters={}, raw_output=TEXT, output_json=json.dumps({"t": TEXT}),
                                status="verified", error_class=None, verification={}, now=NOW)  # fmt: skip
        ss.insert_claims(conn, sid, [claim])
        ss.record_usage(conn, run_id=run, version_id=version, summary_id=sid, call_no=1, provider="fake",
                        model="fake-1", input_tokens=1, output_tokens=1, usage_estimated=False,
                        latency_ms=1, cost_usd=0.0, outcome="ok", error_class=None, now=NOW)  # fmt: skip
    ss.review(conn, sid, decision="approved", reviewer="Test", note=TEXT, now=NOW)
    ss.finish_run(conn, run, outcome="ok", counts={"verified": 1}, spent_usd=0.0, now=NOW)


def _files(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_snapshot_is_byte_identical_with_research_rows_present(full_dir, copy_of, tmp_path):
    with_research = copy_of(full_dir)
    seed_research(with_research)
    plain = export_snapshot(full_dir, tmp_path / "plain", now=EXPORT_NOW, allow_fixtures=True)
    mixed = export_snapshot(with_research, tmp_path / "mixed", now=EXPORT_NOW, allow_fixtures=True)
    assert plain["snapshot_id"] == mixed["snapshot_id"]
    assert _files(tmp_path / "plain") == _files(tmp_path / "mixed")
    blob = b"".join(_files(tmp_path / "mixed").values())
    assert b"SYNTHETIC FIXTURE research" not in blob and b"anz.co.nz" not in blob


@pytest.mark.parametrize("path", ["/api/health", "/api/overview", "/api/releases", "/api/cpi"])
def test_stats_nz_api_answers_are_unchanged_by_research_rows(full_dir, copy_of, path):
    def answer(data_dir: Path):
        app = create_app(load_settings({"NZSTATS_DATA_DIR": str(data_dir)}), start_scheduler=False)
        app.state.now = lambda: EXPORT_NOW
        with TestClient(app) as client:
            return client.get(path).json()

    with_research = copy_of(full_dir)
    seed_research(with_research)
    assert answer(full_dir) == answer(with_research)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.anz.co.nz/about-us/economic-markets-research/",
        "https://www.treasury.govt.nz/publications",
        "https://www.rbnz.govt.nz/research-and-publications/publications",
        "https://assets.dam.westpac.co.nz/is/content/wnzl/x.pdf",
        "https://stats.govt.nz.evil.example/x",
    ],
)
def test_research_hosts_are_not_stats_nz_source_urls(url):
    assert not is_stats_nz_url(url)


def _list(root: Path, name: str, payload: dict) -> None:
    manifest = json.loads((root / "manifest.json").read_text())
    data = (json.dumps(
        {"schema_version": manifest["schema_version"], "kind": name.split("/")[0].removesuffix(".json"),
         "snapshot_id": manifest["snapshot_id"], "payload": payload}, sort_keys=True) + "\n").encode()  # fmt: skip
    (root / name).parent.mkdir(parents=True, exist_ok=True)
    (root / name).write_bytes(data)
    manifest["files"][name] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    (root / "manifest.json").write_text(json.dumps(manifest))


@pytest.mark.parametrize("name", ["research/anz-outlook.json", "research.json"])
def test_a_research_file_slipped_into_a_snapshot_is_an_error_not_a_crash(snapshot, name):
    _list(snapshot, name, {"title": TEXT})
    report = validate_snapshot(snapshot)
    assert not report.ok
    assert any(name in e and "not a known snapshot file" in e for e in report.errors)
