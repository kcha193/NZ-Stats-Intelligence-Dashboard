import sqlite3

from nzstats.cli import main


def test_migrate_then_backup_produces_valid_copy(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(tmp_path / "data"))
    assert main(["migrate"]) == 0
    dest = tmp_path / "backup.db"
    assert main(["backup", str(dest)]) == 0
    tables = {
        r[0]
        for r in sqlite3.connect(dest).execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"release", "observation", "vintage"} <= tables


def test_backup_creates_a_missing_destination_directory(tmp_path, monkeypatch) -> None:
    """Review #4268149432: the container user creates data/backups, not the host user."""
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(tmp_path / "data"))
    assert main(["migrate"]) == 0
    dest = tmp_path / "data" / "backups" / "nzstats.db"
    assert main(["backup", str(dest)]) == 0
    assert dest.is_file()


def test_health_prints_json(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(tmp_path / "data"))
    assert main(["health"]) == 0
    assert '"sources"' in capsys.readouterr().out


def test_serve_accepts_no_scheduler_flag(tmp_path, monkeypatch) -> None:
    import uvicorn

    import nzstats.api.app as app_module

    captured: dict[str, object] = {}
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(
        app_module,
        "create_app",
        lambda settings, start_scheduler, routers=(): captured.update(s=start_scheduler, r=routers),
    )
    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: None)
    assert main(["serve", "--no-scheduler", "--port", "9"]) == 0
    assert captured["s"] is False
    # The research routes are always mounted by serve (off unless NZSTATS_PUBLIC_RESEARCH=1).
    assert [r.routes[0].path for r in captured["r"]] == ["/research/feed"]


def test_serve_starts_the_scheduler_by_default(tmp_path, monkeypatch) -> None:
    import uvicorn

    import nzstats.api.app as app_module

    captured: dict[str, object] = {}
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(
        app_module,
        "create_app",
        lambda settings, start_scheduler, routers=(): captured.update(s=start_scheduler, r=routers),
    )
    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: None)
    assert main(["serve", "--port", "9"]) == 0
    assert captured["s"] is True


def test_backfill_exits_nonzero_and_names_a_failed_month(tmp_path, monkeypatch, capsys) -> None:
    import nzstats.cli as cli
    from nzstats.pipeline.ingest import IngestOutcome

    monkeypatch.setenv("NZSTATS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(cli, "build_runtime", lambda settings: object())
    monkeypatch.setattr(
        cli,
        "backfill",
        lambda rt, since: [
            IngestOutcome("calendar_month:2026-08", "failed", detail="calendar_month: network: x"),
            IngestOutcome("international-migration:july 2026", "ingested"),
        ],
    )
    assert cli.main(["backfill", "--since", "2026-06"]) == 1
    out = capsys.readouterr().out
    assert "calendar_month:2026-08: failed (calendar_month: network: x)" in out


def _run_backfill_with(monkeypatch, tmp_path, outcomes) -> int:
    import nzstats.cli as cli

    monkeypatch.setenv("NZSTATS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(cli, "build_runtime", lambda settings: object())
    monkeypatch.setattr(cli, "backfill", lambda rt, since: outcomes)
    return cli.main(["backfill", "--since", "2026-06"])


def test_a_release_that_is_not_available_makes_the_cli_exit_nonzero(tmp_path, monkeypatch) -> None:
    """Review #4246379621: a requested release that was not ingested is a gap, not a success."""
    from nzstats.pipeline.ingest import IngestOutcome

    outcomes = [
        IngestOutcome("international-migration:june 2026", "ingested"),
        IngestOutcome("international-migration:july 2026", "not_available"),
    ]
    assert _run_backfill_with(monkeypatch, tmp_path, outcomes) == 1


def test_ingested_and_unchanged_releases_exit_zero(tmp_path, monkeypatch) -> None:
    from nzstats.pipeline.ingest import IngestOutcome

    outcomes = [
        IngestOutcome("international-migration:june 2026", "ingested"),
        IngestOutcome("international-migration:july 2026", "unchanged"),
    ]
    assert _run_backfill_with(monkeypatch, tmp_path, outcomes) == 0


def test_an_explicit_release_key_without_an_adapter_makes_the_cli_exit_nonzero(
    tmp_path, monkeypatch, capsys
) -> None:
    """Review #4254166732: an explicitly requested release that was not ingested is not a success."""
    import nzstats.cli as cli
    from nzstats.pipeline.ingest import IngestOutcome

    monkeypatch.setenv("NZSTATS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(cli, "build_runtime", lambda settings: object())
    monkeypatch.setattr(
        cli, "ingest_release", lambda rt, key: IngestOutcome(key, "skipped_no_adapter")
    )
    assert cli.main(["ingest", "--release-key", "gdp:june 2026"]) == 1
    assert "gdp:june 2026: skipped_no_adapter" in capsys.readouterr().out
