"""Validate a snapshot directory: structure, hashes, schemas, completeness, cross-file consistency, privacy."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nzstats.publish.contract import (
    MANIFEST,
    ORIGIN_FIXTURE,
    ORIGIN_PRODUCTION,
    REQUIRED_FILES,
    REQUIRED_REVISIONS,
    REQUIRED_SERIES,
    SCHEMA_VERSION,
    kind_of,
    validate_payload,
)
from nzstats.publish.leaks import scan_for_leaks

MAX_TOTAL_BYTES = 50 * 1024 * 1024
CALENDAR_STALE_DAYS = 7
PUBLISHED = ("published", "corrected")


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    manifest: dict[str, Any] | None = None

    @property
    def ok(self) -> bool:
        return not self.errors


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_snapshot(
    root: Path,
    *,
    for_publish: bool = False,
    now: datetime | None = None,
    scrub: tuple[str, ...] = (),
) -> Report:
    """Collect every problem rather than stopping at the first. `for_publish` additionally demands
    production origin. `scrub` lists literal strings (paths, hostnames) that must not appear anywhere."""
    root, now, report = Path(root), now or datetime.now(UTC), Report()
    err = report.errors.append
    if not (root / MANIFEST).exists():
        err(f"{MANIFEST} is missing")
        return report
    try:
        manifest = _load(root / MANIFEST)
    except ValueError as exc:
        err(f"{MANIFEST} is not valid JSON: {exc}")
        return report
    report.manifest = manifest
    if manifest.get("schema_version") != SCHEMA_VERSION:
        err(f"unsupported schema_version {manifest.get('schema_version')!r}")
        return report
    origin = manifest.get("origin")
    if origin not in (ORIGIN_PRODUCTION, ORIGIN_FIXTURE):
        err(f"unknown origin {origin!r}")
    if for_publish and origin != ORIGIN_PRODUCTION:
        err(f"origin is {origin!r}; only production data may be published")

    listed = manifest.get("files", {})
    on_disk = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()} - {MANIFEST}
    for extra in sorted(on_disk - set(listed)):
        err(f"{extra} is not listed in the manifest")
    for path in sorted(set(listed) - on_disk):
        err(f"{path} is listed in the manifest but missing")
    for path in REQUIRED_FILES:
        if path not in listed:
            err(f"required file {path} is absent")
    for key in REQUIRED_SERIES:
        if f"series/{key}.json" not in listed:
            err(f"required series {key} is absent")
    for key in REQUIRED_REVISIONS:
        if f"revisions/{key}.json" not in listed:
            err(f"required revisions for {key} are absent")

    payloads: dict[str, Any] = {}
    total = 0
    for path, meta in sorted(listed.items()):
        file = root / path
        if not file.exists():
            continue
        data = file.read_bytes()
        total += len(data)
        if hashlib.sha256(data).hexdigest() != meta["sha256"] or len(data) != meta["bytes"]:
            err(f"{path} does not match its manifest hash")
            continue
        text = data.decode("utf-8")
        for finding in scan_for_leaks(text, extra=scrub):
            err(f"{path} contains {finding}")
        try:
            env = json.loads(text)
        except ValueError:
            err(f"{path} is not valid JSON")
            continue
        if env.get("schema_version") != SCHEMA_VERSION or env.get("kind") != kind_of(path):
            err(f"{path} has the wrong envelope (kind or schema_version)")
            continue
        if env.get("snapshot_id") != manifest.get("snapshot_id"):
            err(f"{path} belongs to a different snapshot")
            continue
        try:
            model = validate_payload(kind_of(path), env["payload"])
        except ValueError as exc:
            err(f"{path} does not match its response model: {str(exc).splitlines()[0]}")
            continue
        if path != "releases.json" and not isinstance(model, list):
            # Round trip: a field the response model does not know is an internal field leaking out.
            if model.model_dump(mode="json") != env["payload"]:
                err(f"{path} carries fields outside the public response model")
        payloads[path] = env["payload"]
    if total > MAX_TOTAL_BYTES:
        err(f"snapshot is {total / 1e6:.1f} MB, over the {MAX_TOTAL_BYTES // 2**20} MB limit")

    if all(p in payloads for p in ("releases.json", "overview.json", "cpi.json", "ect.json")):
        _consistency(payloads, report)
    _freshness(manifest, payloads, now, report)
    return report


def _consistency(payloads: dict[str, Any], report: Report) -> None:
    err = report.errors.append
    listing = payloads["releases.json"]
    by_key = {r["release_key"]: r for r in listing}
    ids = [r["id"] for r in listing]
    if len(set(ids)) != len(ids):
        err("releases.json contains duplicate release ids")
    for r in listing:
        detail = payloads.get(f"releases/{r['id']}.json")
        if detail is None:
            err(f"release {r['id']} has no detail file")
            continue
        if detail["release"] != r:
            err(f"release {r['id']}: detail disagrees with the listing")
        if r["has_analysis"] != (detail["analysis"] is not None):
            err(f"release {r['id']}: has_analysis disagrees with its detail")
        if r["status"] not in PUBLISHED and r["has_analysis"]:
            err(f"release {r['id']} is {r['status']} but carries an analysis")

    def check_evidence(where: str, insights: list[dict[str, Any]]) -> None:
        for insight in insights:
            for ev in insight["evidence"]:
                rel = by_key.get(ev["release_key"])
                if rel is None or rel["status"] not in PUBLISHED:
                    err(
                        f"{where}: evidence cites {ev['release_key']!r}, which is not a published release"
                    )

    for name, dash in (("cpi.json", payloads["cpi.json"]), ("ect.json", payloads["ect.json"])):
        a = dash["analysis"]
        check_evidence(name, a["executive_summary"] + a["context"] + a["interpretation"])
        if a["release"]["release_key"] not in by_key:
            err(f"{name}: analysis release is not in releases.json")
    for kpi in payloads["overview.json"]["kpis"]:
        if kpi["release_id"] not in {r["id"] for r in listing}:
            err(f"overview KPI {kpi['metric']['series_key']} cites an unknown release")

    # Headline figures must equal the underlying published series.
    ect = {s["series"]["key"]: s["points"] for s in payloads["ect.json"]["series"]}
    mig = {
        p.split("/")[1].removesuffix(".json"): v["points"]
        for p, v in payloads.items()
        if p.startswith("series/")
    }
    for kpi in payloads["overview.json"]["kpis"]:
        m = kpi["metric"]
        pts = mig.get(m["series_key"]) or ect.get(m["series_key"])
        if pts is None:
            continue
        match = [p for p in pts if p["period"] == m["period"]]
        if not match or match[0]["value"] != m["value"] or match[0]["status"] != m["status"]:
            err(f"overview KPI {m['series_key']} {m['period']} does not equal the published series")


def _freshness(
    manifest: dict[str, Any], payloads: dict[str, Any], now: datetime, report: Report
) -> None:
    if not manifest.get("data_updated_at"):
        report.errors.append("no data has been verified yet (data_updated_at is empty)")
    cal = payloads.get("calendar.json")
    checked = cal and cal["last_success_at"]
    if checked and (now - datetime.fromisoformat(checked)).days >= CALENDAR_STALE_DAYS:
        report.warnings.append(
            f"release calendar last refreshed {checked}; over {CALENDAR_STALE_DAYS} days ago"
        )
    for s in (payloads.get("health.json") or {}).get("sources", []):
        if s["state"] != "ok":
            report.warnings.append(
                f"source {s['source']} is degraded; the snapshot shows last-known-good data"
            )
