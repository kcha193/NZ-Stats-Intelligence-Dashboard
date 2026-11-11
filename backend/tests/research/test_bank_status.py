"""Phase 4AE: per-series source states, metrics and the read-only `bank-status` command (SYNTHETIC FIXTURE)."""

import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

import pytest

from nzstats.cli import main
from nzstats.research import store
from nzstats.research.bank_status import (
    bank_metrics,
    bank_status,
    bank_status_exit,
)
from nzstats.research.registry import load_registry
from nzstats.store.db import connect, migrate

from .bank_support import BANK_KEYS, SYNTH_ADAPTERS, synthetic_registry
from .llm_support import SECTIONS, draft, seed_version
from .support import institution
from .test_drafts_auto import store_hosted

NOW = datetime(2026, 11, 10, 1, 0, tzinfo=UTC)
SENTINEL = "SENTINEL-DOCUMENT-TEXT-7731"


def only(key: str):
    return {key: synthetic_registry()[key]}


def states(statuses, key="bank_a"):
    bank = next(s for s in statuses if s.key == key)
    return bank.state, {s.series_key: s.state for s in bank.series}


def seed(conn, doc, published_on, key="bank_a", sections=SECTIONS):
    return seed_version(conn, sections, key=key, doc=doc, published_on=published_on)


def test_every_real_bank_is_permission_denied_and_exits_zero(conn):
    got = bank_status(conn, load_registry(), NOW)
    assert [s.key for s in got] == sorted(BANK_KEYS)
    assert {s.state for s in got} == {"permission_denied"}
    assert bank_status_exit(got) == 0


def test_a_permitted_bank_without_an_adapter_is_unsupported(conn):
    reg = {"bank_x": institution("bank_x", name="Example Bank X")}
    got = bank_status(conn, reg, NOW, adapters={})
    assert states(got, "bank_x") == ("unsupported", {})
    assert bank_status_exit(got) == 0


def test_a_permitted_supported_bank_with_nothing_stored_is_missing(conn):
    got = bank_status(conn, only("bank_a"), NOW, SYNTH_ADAPTERS)
    assert states(got) == ("missing", {"outlook": "missing", "weekly": "missing"})
    assert bank_status_exit(got) == 1


def test_a_fresh_weekly_cannot_mask_a_stale_outlook(conn):
    seed(conn, "research/outlook/q3", "2026-05-01")  # 193 days old, cadence 100
    seed(conn, "research/weekly/w45", "2026-11-05")
    got = bank_status(conn, only("bank_a"), NOW, SYNTH_ADAPTERS)
    assert states(got) == ("stale", {"outlook": "stale", "weekly": "ok"})
    assert bank_status_exit(got) == 1


def test_fresh_series_are_ok(conn):
    seed(conn, "research/outlook/q4", "2026-10-01")
    seed(conn, "research/weekly/w45", "2026-11-05")
    got = bank_status(conn, only("bank_a"), NOW, SYNTH_ADAPTERS)
    assert states(got) == ("ok", {"outlook": "ok", "weekly": "ok"})
    assert bank_status_exit(got) == 0


def test_a_blocked_crawler_state_is_blocked_whatever_is_stored(conn):
    seed(conn, "research/outlook/q4", "2026-10-01")
    inst_id = conn.execute("SELECT id FROM research_institution WHERE key='bank_a'").fetchone()[0]
    store.set_health(conn, inst_id, state="blocked", now=NOW, success=False, detail="blocked")
    got = bank_status(conn, only("bank_a"), NOW, SYNTH_ADAPTERS)
    assert states(got)[0] == "blocked"
    assert bank_status_exit(got) == 1


def test_permission_outranks_everything(conn):
    seed(conn, "research/outlook/q4", "2026-10-01")
    revoked = institution(
        "bank_a", name="Example Bank A", review_status="needs_review", content_policy="none"
    )
    got = bank_status(conn, {"bank_a": revoked}, NOW, SYNTH_ADAPTERS)
    assert states(got) == (
        "permission_denied",
        {"outlook": "permission_denied", "weekly": "permission_denied"},
    )


def test_a_series_whose_reports_have_no_dates_is_undated_not_ok(conn):
    seed(conn, "research/outlook/q4", None)
    seed(conn, "research/weekly/w45", "2026-11-05")
    got = bank_status(conn, only("bank_a"), NOW, SYNTH_ADAPTERS)
    assert states(got) == ("undated", {"outlook": "undated", "weekly": "ok"})
    assert bank_status_exit(got) == 1


def test_one_dated_report_is_enough_to_judge_freshness(conn):
    seed(conn, "research/outlook/q3", None)
    seed(conn, "research/outlook/q4", "2026-10-01")
    got = bank_status(conn, only("bank_a"), NOW, SYNTH_ADAPTERS)
    assert states(got)[1]["outlook"] == "ok"


def test_the_text_report_shows_pacific_auckland_times_and_the_json_keeps_utc(conn):
    from nzstats.research.bank_status import render_text

    seed(conn, "research/outlook/q4", "2026-10-01")
    inst_id = conn.execute("SELECT id FROM research_institution WHERE key='bank_a'").fetchone()[0]
    store.set_health(
        conn, inst_id, state="ok", now=NOW - timedelta(hours=3), success=True, detail=None
    )
    got = bank_status(conn, only("bank_a"), NOW, SYNTH_ADAPTERS)
    text = "\n".join(render_text(got))
    assert (
        "2026-11-10T11:00:00+13:00" in text
    )  # 22:00 UTC on the 9th is 11:00 on the 10th in Auckland (NZDT)
    assert "UTC as stored" not in text and "Pacific/Auckland" in text
    assert (
        asdict(got[0].series[0])["last_checked_at"] == "2026-11-09T22:00:00Z"
    )  # machine output stays UTC


def test_the_four_dates_are_separate(conn):
    v = seed(conn, "research/outlook/q4", "2026-10-01")
    inst_id = conn.execute("SELECT id FROM research_institution WHERE key='bank_a'").fetchone()[0]
    store.set_health(
        conn, inst_id, state="ok", now=NOW - timedelta(hours=3), success=True, detail=None
    )
    got = bank_status(conn, only("bank_a"), NOW, SYNTH_ADAPTERS)
    outlook = next(s for s in got[0].series if s.series_key == "outlook")
    assert outlook.newest_published_on == "2026-10-01"
    assert outlook.ingested_at is not None and outlook.ingested_at.startswith("2026-10-26")
    assert outlook.analysed_at is None  # nothing summarised yet
    assert outlook.last_checked_at == "2026-11-09T22:00:00Z"
    store_hosted(conn, v)
    got = bank_status(conn, only("bank_a"), NOW, SYNTH_ADAPTERS)
    outlook = next(s for s in got[0].series if s.series_key == "outlook")
    assert outlook.analysed_at is not None


def test_status_output_has_no_document_text(conn):
    sections = (f"{SENTINEL} grows 2.5% in the year to March 2027.", SECTIONS[1])
    seed(conn, "research/outlook/q4", "2026-10-01", sections=sections)
    got = bank_status(conn, only("bank_a"), NOW, SYNTH_ADAPTERS)
    assert SENTINEL not in json.dumps([asdict(s) for s in got])


def test_metrics_count_runs_items_and_failures(conn):
    seed(conn, "research/outlook/q4", "2026-10-01")
    inst_id = conn.execute("SELECT id FROM research_institution WHERE key='bank_a'").fetchone()[0]
    start = NOW - timedelta(hours=1)
    for outcome, items in (
        ("ok", ["new", "updated", "unchanged"]),
        ("partial", ["new", "failed"]),
        ("blocked", []),
        ("failed", ["failed"]),
    ):
        run = store.record_run(
            conn, inst_id, started_at=start, finished_at=NOW, outcome=outcome, dry_run=False,
            counts={}, error_class=None, detail=None,
        )  # fmt: skip
        for item in items:
            store.record_item(
                conn, run, url="https://research.example.org/x", outcome=item, error_class=None,
                detail=None, publication_id=None, version_id=None,
            )  # fmt: skip
    old = store.record_run(
        conn, inst_id, started_at=NOW - timedelta(days=90), finished_at=NOW - timedelta(days=90),
        outcome="ok", dry_run=False, counts={}, error_class=None, detail=None,
    )  # fmt: skip
    store.record_item(conn, old, url="https://research.example.org/o", outcome="new",
                      error_class=None, detail=None, publication_id=None, version_id=None)  # fmt: skip
    m = bank_metrics(
        conn, only("bank_a"), NOW - timedelta(days=30), now=NOW, adapters=SYNTH_ADAPTERS
    )["bank_a"]
    assert (m.discovery_ok, m.discovery_failed, m.blocked) == (2, 1, 1)
    assert (m.new_documents, m.updated_versions, m.extraction_failures) == (2, 1, 2)
    assert (
        m.missing_expected == 1
    )  # the weekly series has nothing stored; the outlook series is fresh


def test_metrics_count_verification_failures_by_bank(conn):
    v = seed(conn, "research/outlook/q4", "2026-10-01")
    out = draft(v)
    out["forecasts"][0]["value"] = 9.9
    store_hosted(conn, v, output=out)
    m = bank_metrics(
        conn, only("bank_a"), NOW - timedelta(days=30), now=NOW, adapters=SYNTH_ADAPTERS
    )["bank_a"]
    assert m.verification_failures == 1


def test_cli_bank_status_on_the_real_registry(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("NZSTATS_RESEARCH_SOURCES_FILE", raising=False)
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(tmp_path / "data"))
    c = connect(tmp_path / "data" / "nzstats.db")
    migrate(c)
    c.close()
    monkeypatch.setattr("nzstats.research.cli.build_fetcher", pytest.fail)
    assert main(["research", "bank-status", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert {b["key"]: b["state"] for b in payload["banks"]} == dict.fromkeys(
        BANK_KEYS, "permission_denied"
    )
    assert payload["exit_code"] == 0


def test_research_health_json_carries_bank_metrics(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("NZSTATS_RESEARCH_SOURCES_FILE", raising=False)
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(tmp_path / "data"))
    main(["research", "health", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert sorted(payload["bank_metrics"]) == sorted(BANK_KEYS)
    assert set(payload["bank_metrics"]["anz"]) == {
        "discovery_ok", "discovery_failed", "new_documents", "updated_versions", "blocked",
        "extraction_failures", "verification_failures", "missing_expected",
    }  # fmt: skip


def test_cli_bank_status_does_not_create_or_migrate_a_database(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("NZSTATS_RESEARCH_SOURCES_FILE", raising=False)
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(tmp_path / "data"))
    assert main(["research", "bank-status"]) == 3
    assert not (tmp_path / "data" / "nzstats.db").exists()
    assert "no database" in capsys.readouterr().out.lower()
