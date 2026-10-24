import json
import shutil
import sqlite3
import subprocess
from datetime import timedelta
from pathlib import Path

import pytest

from nzstats.clock import to_utc_iso
from nzstats.publish.provenance import FIXTURE_MARKER
from nzstats.publish.publisher import PublisherConfig, publish
from nzstats.publish.snapshot import export_snapshot
from nzstats.publish.validate import validate_snapshot
from tests.publish.conftest import EXPORT_NOW

SITE = "https://nzstats.example"


def key_of(cmd) -> str:
    """Which tool a command runs: the script's file name for `bash script`, else the CLI's subcommand."""
    return Path(cmd[1]).name if cmd[0] == "bash" else cmd[1]


class Recorder:
    """Stands in for subprocess: records commands and answers like the real tools."""

    def __init__(self, deploy_json: dict | None = None, fail: str | None = None):
        self.calls: list[tuple[list[str], dict]] = []
        self.deploy_json = deploy_json or {
            "deploy_id": "d1",
            "deploy_url": "https://x--nzstats.netlify.app",
        }
        self.fail = fail

    def __call__(self, cmd, *, env=None, cwd=None):
        self.calls.append((list(cmd), {"env": env or {}, "cwd": cwd}))
        if self.fail and self.fail == key_of(cmd):
            return subprocess.CompletedProcess(cmd, 1, "", "boom")
        out = json.dumps(self.deploy_json) if key_of(cmd) == "deploy" else ""
        return subprocess.CompletedProcess(cmd, 0, out, "")

    def ran(self, key: str) -> list[list[str]]:
        return [c for c, _ in self.calls if key_of(c) == key]


class LiveSite:
    """The deployed site: its manifest changes only when a production deploy is run."""

    def __init__(self, snapshot_id: str | None = None):
        self.id, self.pending = snapshot_id, None

    def wrap(self, rec: Recorder):
        def run(cmd, **kw):
            if key_of(cmd) == "build_static_site.sh":
                self.pending = json.loads(
                    (Path(cmd[cmd.index("--snapshot") + 1]) / "manifest.json").read_text()
                )["snapshot_id"]
            result = rec(cmd, **kw)
            if "deploy" in cmd and "--prod" in cmd and result.returncode == 0:
                self.id = self.pending
            return result

        return run

    def fetch(self, url):
        return None if self.id is None else {"snapshot_id": self.id}


def cfg(tmp_path, data_dir, **over) -> PublisherConfig:
    base = dict(
        data_dir=data_dir,
        work_dir=tmp_path / "state",
        repo_root=tmp_path / "repo",
        site_url=SITE,
        netlify_site_id="site-123",
        netlify_auth_token="tok-secret-value",
        min_interval_hours=6,
    )
    base.update(over)
    return PublisherConfig(**base)


def live(snapshot_id: str | None):
    return lambda url: None if snapshot_id is None else {"snapshot_id": snapshot_id}


def test_an_unmarked_data_directory_exports_and_validates_for_publish(production_dir, tmp_path):
    out = tmp_path / "snap"
    manifest = export_snapshot(production_dir, out, now=EXPORT_NOW)
    assert manifest["origin"] == "production"
    assert validate_snapshot(out, for_publish=True).ok


def test_publishes_new_data_then_records_it_and_verifies_the_live_site(production_dir, tmp_path):
    run, site = Recorder(), LiveSite()
    out = publish(
        cfg(tmp_path, production_dir),
        runner=site.wrap(run),
        fetch_manifest=site.fetch,
        now=EXPORT_NOW,
        sleep=lambda s: None,
    )
    assert out.status == "deployed" and out.verified
    deploy = run.ran("deploy")[0]
    assert "--prod" in deploy and deploy[deploy.index("--dir") + 1].endswith("frontend/dist-static")
    env = run.calls[-1][1]["env"]
    assert env["NETLIFY_AUTH_TOKEN"] == "tok-secret-value" and env["NETLIFY_SITE_ID"] == "site-123"
    assert "tok-secret-value" not in " ".join(
        " ".join(c) for c, _ in run.calls
    )  # never on a command line
    state = json.loads((tmp_path / "state" / "state.json").read_text())
    assert state["last_snapshot_id"] == out.snapshot_id and state["last_deployed_at"]


def test_an_unchanged_snapshot_is_not_redeployed(production_dir, tmp_path):
    site = LiveSite()
    publish(
        cfg(tmp_path, production_dir),
        runner=site.wrap(Recorder()),
        fetch_manifest=site.fetch,
        now=EXPORT_NOW,
        sleep=lambda s: None,
    )
    second = Recorder()
    out = publish(
        cfg(tmp_path, production_dir),
        runner=site.wrap(second),
        fetch_manifest=lambda u: None,
        now=EXPORT_NOW + timedelta(days=1),
        sleep=lambda s: None,
    )
    assert out.status == "unchanged" and second.calls == []


def test_the_site_already_showing_this_data_is_not_redeployed_even_without_state(
    production_dir, tmp_path
):
    current = export_snapshot(production_dir, tmp_path / "probe", now=EXPORT_NOW)["snapshot_id"]
    run = Recorder()
    out = publish(
        cfg(tmp_path / "fresh", production_dir),
        runner=run,
        fetch_manifest=LiveSite(current).fetch,
        now=EXPORT_NOW,
        sleep=lambda s: None,
    )
    assert out.status == "unchanged" and not run.ran("deploy")


def _state(tmp_path, **fields):
    state = tmp_path / "state"
    state.mkdir(exist_ok=True)
    (state / "state.json").write_text(json.dumps(fields))


@pytest.mark.parametrize("known_by", ["state", "live", "both"])
def test_force_rebuilds_and_redeploys_an_unchanged_snapshot_for_a_new_domain(
    production_dir, tmp_path, known_by
):
    manifest = export_snapshot(production_dir, tmp_path / "probe", now=EXPORT_NOW)
    sid = manifest["snapshot_id"]
    if known_by in ("state", "both"):
        _state(
            tmp_path,
            last_snapshot_id=sid,
            last_data_updated_at=manifest["data_updated_at"],
            last_deployed_at=(EXPORT_NOW - timedelta(minutes=5)).isoformat(),
        )
    run = Recorder()
    site = LiveSite(sid if known_by in ("live", "both") else None)
    domain = "https://new-domain.example"
    out = publish(
        cfg(tmp_path, production_dir, force=True, site_url=domain),
        runner=site.wrap(run),
        fetch_manifest=site.fetch,
        now=EXPORT_NOW,
        sleep=lambda s: None,
    )
    assert out.status == "deployed" and out.verified and out.snapshot_id == sid
    build = run.ran("build_static_site.sh")[0]
    assert build[build.index("--site-url") + 1] == domain
    assert len(run.ran("deploy")) == 1 and "--prod" in run.ran("deploy")[0]


@pytest.mark.parametrize("previously_verified", [False, True])
@pytest.mark.parametrize("became_live", [False, True])
def test_calendar_refresh_after_an_unverified_deploy_waits_for_the_interval(
    production_dir, tmp_path, previously_verified, became_live
):
    if previously_verified:
        _state(
            tmp_path,
            last_snapshot_id="old",
            last_data_updated_at="2026-01-01T00:00:00+00:00",
            last_deployed_at=(EXPORT_NOW - timedelta(days=1)).isoformat(),
        )
    first = publish(
        cfg(tmp_path, production_dir),
        runner=Recorder(),
        fetch_manifest=live("old"),
        now=EXPORT_NOW,
        sleep=lambda s: None,
    )
    assert first.status == "deployed_unverified"
    original = json.loads((tmp_path / "state" / "snapshot" / "manifest.json").read_text())

    # A real calendar-only database change gives a different content id without newer statistical data.
    with sqlite3.connect(production_dir / "nzstats.db") as db:
        changed = db.execute(
            "UPDATE release SET published_at = ? WHERE status = 'scheduled'",
            (to_utc_iso(EXPORT_NOW + timedelta(days=30)),),
        )
        assert changed.rowcount > 0
    refreshed = export_snapshot(production_dir, tmp_path / "probe", now=EXPORT_NOW)
    assert refreshed["snapshot_id"] != first.snapshot_id
    assert refreshed["data_updated_at"] == original["data_updated_at"]
    state_path = tmp_path / "state" / "state.json"
    before = state_path.read_bytes()
    run = Recorder()
    site = LiveSite(first.snapshot_id if became_live else "old")
    again = publish(
        cfg(tmp_path, production_dir),
        runner=site.wrap(run),
        fetch_manifest=site.fetch,
        now=EXPORT_NOW + timedelta(hours=1),
        sleep=lambda s: None,
    )
    assert again.status == "too_soon" and run.calls == []
    assert state_path.read_bytes() == before
    state = json.loads(before)
    assert state["unverified_data_updated_at"] == original["data_updated_at"]
    if previously_verified:
        assert state["last_snapshot_id"] == "old"
        assert state["last_data_updated_at"] == "2026-01-01T00:00:00+00:00"
    else:
        assert "last_snapshot_id" not in state and "last_data_updated_at" not in state

    later = publish(
        cfg(tmp_path, production_dir),
        runner=site.wrap(run),
        fetch_manifest=site.fetch,
        now=EXPORT_NOW + timedelta(hours=7),
        sleep=lambda s: None,
    )
    assert later.status == "deployed" and later.verified
    state = json.loads(state_path.read_text())
    assert state["last_snapshot_id"] == refreshed["snapshot_id"]
    assert state["last_data_updated_at"] == original["data_updated_at"]
    assert "unverified_snapshot_id" not in state and "unverified_data_updated_at" not in state


def test_newer_data_after_an_unverified_deploy_still_publishes_immediately(
    production_dir, tmp_path
):
    first = publish(
        cfg(tmp_path, production_dir),
        runner=Recorder(),
        fetch_manifest=live("old"),
        now=EXPORT_NOW,
        sleep=lambda s: None,
    )
    assert first.status == "deployed_unverified"
    with sqlite3.connect(production_dir / "nzstats.db") as db:
        db.execute(
            "UPDATE vintage SET captured_at = ?",
            (to_utc_iso(EXPORT_NOW + timedelta(minutes=30)),),
        )
    run, site = Recorder(), LiveSite("old")
    out = publish(
        cfg(tmp_path, production_dir),
        runner=site.wrap(run),
        fetch_manifest=site.fetch,
        now=EXPORT_NOW + timedelta(hours=1),
        sleep=lambda s: None,
    )
    assert out.status == "deployed" and out.verified
    assert out.snapshot_id != first.snapshot_id and len(run.ran("deploy")) == 1


def test_changes_that_are_not_new_data_are_spaced_by_the_minimum_interval(production_dir, tmp_path):
    data_updated = export_snapshot(production_dir, tmp_path / "probe", now=EXPORT_NOW)[
        "data_updated_at"
    ]
    _state(
        tmp_path,
        last_snapshot_id="old",
        last_data_updated_at=data_updated,
        last_deployed_at=(EXPORT_NOW - timedelta(hours=1)).isoformat(),
    )
    run, site = Recorder(), LiveSite("old")
    out = publish(
        cfg(tmp_path, production_dir),
        runner=site.wrap(run),
        fetch_manifest=site.fetch,
        now=EXPORT_NOW,
        sleep=lambda s: None,
    )
    assert out.status == "too_soon" and not run.ran("deploy")
    forced = publish(
        cfg(tmp_path, production_dir, force=True),
        runner=site.wrap(Recorder()),
        fetch_manifest=site.fetch,
        now=EXPORT_NOW,
        sleep=lambda s: None,
    )
    assert forced.status == "deployed"


def test_newly_verified_data_is_published_at_once_whatever_the_interval(production_dir, tmp_path):
    _state(
        tmp_path,
        last_snapshot_id="old",
        last_data_updated_at="2026-01-01T00:00:00+13:00",
        last_deployed_at=(EXPORT_NOW - timedelta(minutes=5)).isoformat(),
    )
    site = LiveSite("old")
    out = publish(
        cfg(tmp_path, production_dir),
        runner=site.wrap(Recorder()),
        fetch_manifest=site.fetch,
        now=EXPORT_NOW,
        sleep=lambda s: None,
    )
    assert out.status == "deployed"


def test_fixture_data_is_never_published(full_dir, tmp_path):
    run = Recorder()
    out = publish(cfg(tmp_path, full_dir), runner=run, fetch_manifest=live(None), now=EXPORT_NOW)
    assert out.status == "failed" and "fixtures" in out.message and run.calls == []


def test_a_failed_export_leaves_the_live_site_alone(migration_only_dir, tmp_path):
    """Only migration data, with the fixture flags cleared: CPI and card transactions are missing."""
    import sqlite3

    data = tmp_path / "partial"
    shutil.copytree(migration_only_dir, data)
    (data / FIXTURE_MARKER).unlink()
    db = sqlite3.connect(data / "nzstats.db")
    db.execute("PRAGMA user_version = 0")
    db.close()
    run = Recorder()
    out = publish(cfg(tmp_path, data), runner=run, fetch_manifest=live(None), now=EXPORT_NOW)
    assert out.status == "failed" and "missing" in out.message and run.calls == []


def test_a_failed_build_or_deploy_does_not_advance_the_state(production_dir, tmp_path):
    for broken in ("build_static_site.sh", "deploy"):
        work = tmp_path / broken
        out = publish(
            cfg(work, production_dir),
            runner=Recorder(fail=broken),
            fetch_manifest=live(None),
            now=EXPORT_NOW,
            sleep=lambda s: None,
        )
        assert out.status == "failed" and broken.split("_")[0] in out.message
        assert not (work / "state" / "state.json").exists()


def test_dry_run_builds_but_never_deploys(production_dir, tmp_path):
    run = Recorder()
    out = publish(
        cfg(tmp_path, production_dir, dry_run=True),
        runner=run,
        fetch_manifest=live(None),
        now=EXPORT_NOW,
    )
    assert out.status == "dry_run" and run.ran("build_static_site.sh") and not run.ran("deploy")


def test_draft_deploys_omit_prod_and_do_not_advance_the_published_state(production_dir, tmp_path):
    run = Recorder()
    site = LiveSite()
    out = publish(
        cfg(tmp_path, production_dir, draft=True),
        runner=site.wrap(run),
        fetch_manifest=site.fetch,
        now=EXPORT_NOW,
        sleep=lambda s: None,
    )
    assert out.status == "draft_deployed" and "--prod" not in run.ran("deploy")[0]
    assert not (tmp_path / "state" / "state.json").exists()


def test_an_unverified_deploy_is_reported_not_hidden(production_dir, tmp_path):
    out = publish(
        cfg(tmp_path, production_dir),
        runner=Recorder(),
        fetch_manifest=live("something-else"),
        now=EXPORT_NOW,
        sleep=lambda s: None,
    )
    assert out.status == "deployed_unverified" and not out.verified


def test_only_one_publisher_runs_at_a_time(production_dir, tmp_path):
    import fcntl

    (tmp_path / "state").mkdir()
    with (tmp_path / "state" / "lock").open("a+") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        out = publish(
            cfg(tmp_path, production_dir),
            runner=Recorder(),
            fetch_manifest=live(None),
            now=EXPORT_NOW,
        )
    assert out.status == "busy"


def test_the_token_never_appears_in_the_outcome_or_log(production_dir, tmp_path, caplog):
    caplog.set_level("DEBUG")
    out = publish(
        cfg(tmp_path, production_dir),
        runner=Recorder(fail="deploy"),
        fetch_manifest=live(None),
        now=EXPORT_NOW,
        sleep=lambda s: None,
    )
    assert "tok-secret-value" not in out.message and "tok-secret-value" not in caplog.text


def test_a_deploy_that_is_not_confirmed_live_does_not_advance_the_published_state(
    production_dir, tmp_path
):
    run = Recorder()
    out = publish(
        cfg(tmp_path, production_dir),
        runner=run,
        fetch_manifest=live("something-else"),
        now=EXPORT_NOW,
        sleep=lambda s: None,
    )
    assert out.status == "deployed_unverified" and not out.ok
    state = json.loads((tmp_path / "state" / "state.json").read_text())
    assert "last_snapshot_id" not in state and state["unverified_snapshot_id"] == out.snapshot_id


def test_an_unconfirmed_snapshot_is_retried_only_after_the_interval_but_newer_data_goes_at_once(
    production_dir, tmp_path
):
    first = publish(
        cfg(tmp_path, production_dir),
        runner=Recorder(),
        fetch_manifest=live("elsewhere"),
        now=EXPORT_NOW,
        sleep=lambda s: None,
    )
    assert first.status == "deployed_unverified"
    run = Recorder()
    again = publish(
        cfg(tmp_path, production_dir),
        runner=run,
        fetch_manifest=live("elsewhere"),
        now=EXPORT_NOW + timedelta(hours=1),
        sleep=lambda s: None,
    )
    assert again.status == "too_soon" and not run.ran("deploy")
    later = publish(
        cfg(tmp_path, production_dir),
        runner=Recorder(),
        fetch_manifest=live("elsewhere"),
        now=EXPORT_NOW + timedelta(hours=25),
        sleep=lambda s: None,
    )
    assert later.status == "deployed_unverified"


def test_the_token_is_not_given_to_the_build_only_to_the_deploy(production_dir, tmp_path):
    run = Recorder()
    site = LiveSite()
    publish(
        cfg(tmp_path, production_dir),
        runner=site.wrap(run),
        fetch_manifest=site.fetch,
        now=EXPORT_NOW,
        sleep=lambda s: None,
    )
    build_env = next(kw["env"] for c, kw in run.calls if key_of(c) == "build_static_site.sh")
    assert not any(k.startswith("NETLIFY_") for k in build_env)


def test_run_command_strips_netlify_credentials_unless_given_explicitly(monkeypatch):
    from nzstats.publish.publisher import run_command

    monkeypatch.setenv("NETLIFY_AUTH_TOKEN", "from-the-shell")
    code = "import os;print(os.environ.get('NETLIFY_AUTH_TOKEN'))"
    import sys

    assert run_command([sys.executable, "-c", code]).stdout.strip() == "None"
    assert (
        run_command(
            [sys.executable, "-c", code], env={"NETLIFY_AUTH_TOKEN": "explicit"}
        ).stdout.strip()
        == "explicit"
    )


def test_an_unexpected_exception_becomes_a_failed_outcome_not_a_traceback(
    production_dir, tmp_path, monkeypatch
):
    import nzstats.publish.publisher as module

    def boom(*a, **k):
        raise RuntimeError("database exploded")

    monkeypatch.setattr(module, "export_snapshot", boom)
    run = Recorder()
    out = publish(
        cfg(tmp_path, production_dir), runner=run, fetch_manifest=live(None), now=EXPORT_NOW
    )
    assert out.status == "failed" and "RuntimeError" in out.message and run.calls == []
