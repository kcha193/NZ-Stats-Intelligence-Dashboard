"""Publish a validated snapshot to Netlify, only when the data has changed.

Runs on the trusted host next to the database (see docs/netlify-deployment.md). One run is: export, validate, decide
whether anything changed, build the static site, deploy with the Netlify CLI, then check the live manifest. A failure
anywhere stops before the deploy, so the site keeps showing its last-known-good snapshot.

The Netlify credential is read from the environment, handed to the CLI through the environment (never a command line),
and redacted from anything logged or returned.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from nzstats.clock import utc_now
from nzstats.publish.contract import MANIFEST
from nzstats.publish.snapshot import SnapshotError, export_snapshot
from nzstats.publish.validate import validate_snapshot

log = logging.getLogger("nzstats.publish")

VERIFY_ATTEMPTS = 6
VERIFY_WAIT_SECONDS = 10


@dataclass(frozen=True)
class PublisherConfig:
    data_dir: Path
    work_dir: (
        Path  # state, lock and the staged snapshot; keep it outside the data volume's public paths
    )
    repo_root: (
        Path  # checkout (or image) holding scripts/ and frontend/ with its dependencies installed
    )
    site_url: str
    netlify_site_id: str = ""
    netlify_auth_token: str = ""
    min_interval_hours: float = (
        24.0  # applies to changes that are not new verified data (see publish)
    )
    draft: bool = False  # deploy to a draft URL, not production
    dry_run: bool = False  # export, validate and build; never deploy
    force: bool = False  # rebuild unchanged snapshots and ignore the minimum interval


@dataclass(frozen=True)
class Outcome:
    status: str  # unchanged | too_soon | busy | dry_run | draft_deployed | deployed | deployed_unverified | failed
    snapshot_id: str | None = None
    message: str = ""
    verified: bool = False

    @property
    def ok(self) -> bool:
        return self.status not in ("failed", "deployed_unverified")


Runner = Callable[..., "subprocess.CompletedProcess[str]"]
ManifestFetcher = Callable[[str], "Mapping[str, Any] | None"]


def run_command(
    cmd: Sequence[str], *, env: Mapping[str, str] | None = None, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    # The Netlify credential reaches only the process that is handed it explicitly, never the build tooling.
    inherited = {k: v for k, v in os.environ.items() if not k.startswith("NETLIFY_")}
    return subprocess.run(  # noqa: S603 - fixed argument lists, no shell
        list(cmd),
        env={**inherited, **(env or {})},
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def fetch_live_manifest(site_url: str) -> Mapping[str, Any] | None:
    try:
        res = httpx.get(
            f"{site_url.rstrip('/')}/data/v1/manifest.json",
            timeout=15,
            headers={"Cache-Control": "no-cache"},
            follow_redirects=True,
        )
        return res.json() if res.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        return None


def _redact(text: str, secrets: Sequence[str]) -> str:
    for secret in filter(None, secrets):
        text = text.replace(secret, "***")
    return text


def _tail(text: str, secrets: Sequence[str], limit: int = 400) -> str:
    return _redact(text.strip(), secrets)[-limit:]


def _load_state(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_state(path: Path, state: Mapping[str, Any]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)  # atomic: a crash never leaves half a state file


def publish(
    cfg: PublisherConfig,
    *,
    runner: Runner = run_command,
    fetch_manifest: ManifestFetcher = fetch_live_manifest,
    now: datetime | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> Outcome:
    now = now or utc_now()
    secrets = (cfg.netlify_auth_token,)
    cfg.work_dir.mkdir(parents=True, exist_ok=True)
    with (cfg.work_dir / "lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return Outcome("busy", message="another publisher run is in progress")
        return _publish_locked(cfg, runner, fetch_manifest, now, sleep, secrets)


def _publish_locked(
    cfg: PublisherConfig,
    runner: Runner,
    fetch_manifest: ManifestFetcher,
    now: datetime,
    sleep: Callable[[float], None],
    secrets: Sequence[str],
) -> Outcome:
    def fail(message: str, sid: str | None = None) -> Outcome:
        message = _redact(message, secrets)
        log.error("publish failed: %s", message)
        return Outcome("failed", sid, message)

    state_path = cfg.work_dir / "state.json"
    state = _load_state(state_path)
    snapshot = cfg.work_dir / "snapshot"

    try:
        manifest = export_snapshot(cfg.data_dir, snapshot, now=now)
    except SnapshotError as exc:
        return fail(f"export refused: {exc}")
    except Exception as exc:  # never a traceback: an unexpected failure is still "do not deploy"
        log.exception("unexpected error during export")
        return fail(f"export failed unexpectedly ({type(exc).__name__}); see the log")
    sid = manifest["snapshot_id"]
    report = validate_snapshot(snapshot, for_publish=True, now=now)
    for warning in report.warnings:
        log.warning("snapshot warning: %s", warning)
    if report.errors:
        return fail("snapshot failed validation: " + "; ".join(report.errors[:5]), sid)

    live = fetch_manifest(cfg.site_url)
    if not cfg.force and (
        sid == state.get("last_snapshot_id") or (live and live.get("snapshot_id") == sid)
    ):
        log.info("snapshot %s is already published", sid[:12])
        return Outcome("unchanged", sid, "the published site already shows this data")

    # New verified data is published at once. Anything else (a calendar refresh, say) waits out the minimum interval,
    # because each production deploy costs hosting credits.
    # Compare with the latest production attempt, even if it was never seen live. A calendar refresh changes its
    # snapshot id but does not make its statistical data new again. The id check also handles older state files.
    last_attempt_data_updated_at = state.get(
        "unverified_data_updated_at", state.get("last_data_updated_at")
    )
    material = manifest["data_updated_at"] != last_attempt_data_updated_at and sid != state.get(
        "unverified_snapshot_id"
    )
    if not material and not cfg.force and not cfg.draft and state.get("last_deployed_at"):
        due = datetime.fromisoformat(state["last_deployed_at"]) + timedelta(
            hours=cfg.min_interval_hours
        )
        if now < due:
            return Outcome(
                "too_soon",
                sid,
                f"last deploy was less than {cfg.min_interval_hours:g} h ago; next at {due.isoformat()}",
            )

    build = runner(
        ["bash", str(cfg.repo_root / "scripts" / "build_static_site.sh"), "--snapshot", str(snapshot),
         "--site-url", cfg.site_url, "--skip-install"],
        cwd=cfg.repo_root,
    )  # fmt: skip
    if build.returncode != 0:
        return fail(f"build failed: {_tail(build.stderr or build.stdout, secrets)}", sid)
    if cfg.dry_run:
        return Outcome("dry_run", sid, "built; not deployed (dry run)")

    if not cfg.netlify_auth_token or not cfg.netlify_site_id:
        return fail("NETLIFY_AUTH_TOKEN and NETLIFY_SITE_ID are required to deploy", sid)
    cmd = ["netlify", "deploy", "--dir", str(cfg.repo_root / "frontend" / "dist-static"),
           "--message", f"snapshot {sid[:12]}", "--json"]  # fmt: skip
    if not cfg.draft:
        cmd.append("--prod")
    deploy = runner(
        cmd,
        env={"NETLIFY_AUTH_TOKEN": cfg.netlify_auth_token, "NETLIFY_SITE_ID": cfg.netlify_site_id},
        cwd=cfg.repo_root,
    )
    if deploy.returncode != 0:
        return fail(f"deploy failed: {_tail(deploy.stderr or deploy.stdout, secrets)}", sid)
    try:
        detail = json.loads(deploy.stdout or "{}")
    except ValueError:
        detail = {}

    if cfg.draft:
        url = detail.get("deploy_url") or detail.get("logs") or ""
        log.info("draft deployed: %s", url)
        return Outcome("draft_deployed", sid, f"draft deploy {url}".strip())

    history = cfg.work_dir / "history"
    history.mkdir(exist_ok=True)
    (history / f"{now:%Y%m%dT%H%M%SZ}-{sid[:12]}.json").write_text(
        (snapshot / MANIFEST).read_text(encoding="utf-8"), encoding="utf-8"
    )

    verified = False
    for attempt in range(VERIFY_ATTEMPTS):
        seen = fetch_manifest(cfg.site_url)
        if seen and seen.get("snapshot_id") == sid:
            verified = True
            break
        if attempt < VERIFY_ATTEMPTS - 1:
            sleep(VERIFY_WAIT_SECONDS)

    # Only a deploy confirmed live advances what counts as published. An unconfirmed one is remembered, so it is not
    # redeployed every hour, but newer verified data still goes out at once.
    base = {
        "last_deployed_at": now.isoformat(),
        "last_deploy_id": detail.get("deploy_id"),
    }
    if verified:
        _write_state(
            state_path,
            {
                **base,
                "last_snapshot_id": sid,
                "last_data_updated_at": manifest["data_updated_at"],
                "previous_snapshot_id": state.get("last_snapshot_id"),
                "previous_deploy_id": state.get("last_deploy_id"),
            },
        )
        log.info("published snapshot %s and confirmed it is live", sid[:12])
        return Outcome("deployed", sid, "deployed and confirmed live", verified=True)
    kept = {
        k: v for k, v in state.items() if k.startswith(("last_snapshot", "last_data", "previous_"))
    }
    _write_state(
        state_path,
        {
            **kept,
            **base,
            "unverified_snapshot_id": sid,
            "unverified_data_updated_at": manifest["data_updated_at"],
        },
    )
    log.warning("deployed snapshot %s but the live manifest does not show it yet", sid[:12])
    return Outcome(
        "deployed_unverified",
        sid,
        "deployed, but the live site does not show it yet; check the Netlify deploy log and PUBLISH_SITE_URL",
    )
