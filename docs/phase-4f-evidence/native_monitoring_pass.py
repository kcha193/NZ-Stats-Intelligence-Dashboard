"""Phase 4F: drive the real CLI and the real server over an ISOLATED COPY of the production data (never `data/`).

    backend/.venv/bin/python -I docs/phase-4f-evidence/native_monitoring_pass.py <prod data dir> <scratch dir> <repo root>

Every process runs under an in-process network guard that refuses any non-loopback lookup or connection and counts the
attempts. The scheduler is never started (`serve --no-scheduler`), so nothing here can contact Stats NZ. Writes
<scratch>/results.json and prints it.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

PROD, SCRATCH, REPO = (Path(a).resolve() for a in sys.argv[1:4])
DATA = SCRATCH / "data"
PY = REPO / "backend" / ".venv" / "bin" / "python"
GUARD = r"""
import atexit, json, os, socket, sys
refused = []
LOOP = ("127.0.0.1", "::1", "localhost", None)
_c, _g = socket.socket.connect, socket.getaddrinfo
def connect(self, a, *r, **k):
    h = a[0] if isinstance(a, tuple) else None
    if self.family != socket.AF_UNIX and h not in LOOP:
        refused.append(str(h)); raise OSError("network refused by the evidence guard")
    return _c(self, a, *r, **k)
def lookup(h, *r, **k):
    if h not in LOOP:
        refused.append(str(h)); raise OSError("network refused by the evidence guard")
    return _g(h, *r, **k)
socket.socket.connect, socket.getaddrinfo = connect, lookup
atexit.register(lambda: open(os.environ["GUARD_LOG"], "a").write(json.dumps(refused) + "\n"))
from nzstats.cli import main
sys.exit(main(sys.argv[1:]))
"""
GUARD_LOG = SCRATCH / "guard.log"
ENV = {**{k: v for k, v in os.environ.items() if not k.startswith(("NZSTATS_", "STATSNZ_"))},
       "NZSTATS_DATA_DIR": str(DATA), "GUARD_LOG": str(GUARD_LOG), "NZSTATS_STATIC_DIR": str(REPO / "frontend" / "dist")}  # fmt: skip


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prod_fingerprint() -> dict:
    files = {str(p.relative_to(PROD)): sha(p) for p in sorted(PROD.rglob("*")) if p.is_file() and "raw" in p.parts or p.name in ("nzstats.db", ".request-pace")}  # fmt: skip
    return {"files": len(files), "digest": hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()}


def cli(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([str(PY), "-c", GUARD, *args], env={**ENV, **(env or {})}, capture_output=True, text=True, timeout=300)


def status() -> dict:
    r = cli("status", "--json")
    report = json.loads(r.stdout)
    return {"exit": r.returncode, "overall": report["overall"], "collection": report["collection"]["mode"], "process": report["process"]["state"],
            "backup": report["backup"]["state"], "issues": [(i["severity"], i["key"]) for i in report["issues"]], "notes": report["notes"],
            "schema": report["database"]["schema_version"], "freshness": {f["series_slug"]: f["state"] for f in report["freshness"]}}  # fmt: skip


def counts(db: Path) -> dict:
    conn = sqlite3.connect(f"{db.as_uri()}?mode=ro", uri=True)
    try:
        return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("release", "series", "vintage", "observation", "raw_artifact", "ingest_run")}
    finally:
        conn.close()


def main() -> None:
    results: dict = {"steps": {}}
    before = prod_fingerprint()
    shutil.rmtree(SCRATCH, ignore_errors=True)
    DATA.mkdir(parents=True)
    # An isolated copy: SQLite online backup from a READ-ONLY connection, plus the raw tree and the earlier manual backup.
    src = sqlite3.connect(f"{(PROD / 'nzstats.db').as_uri()}?mode=ro", uri=True)
    dst = sqlite3.connect(DATA / "nzstats.db")
    src.backup(dst), src.close(), dst.close()
    shutil.copytree(PROD / "raw", DATA / "raw")
    for old in (PROD / "backups").glob("phase-4e-*"):
        (DATA / "backups" / old.name).mkdir(parents=True)
        shutil.copy2(old / "nzstats.db", DATA / "backups" / old.name / "nzstats.db")
    s = results["steps"]
    s["01_copy_counts"] = counts(DATA / "nzstats.db")

    s["02_status_schema_10_untouched"] = status()
    s["02_status_schema_10_untouched"]["schema_after_status"] = sqlite3.connect(DATA / "nzstats.db").execute("SELECT MAX(version) FROM schema_version").fetchone()[0]

    s["03_migrate"] = cli("migrate").stdout.strip()
    s["04_status_after_migrate_no_process_yet"] = status()

    stamp = time.strftime("%Y-%m-%d-%H%M")
    t0 = time.time()
    r = cli("backup", "--bundle", str(DATA / "backups" / f"nzstats-{stamp}"))
    bundle = DATA / "backups" / f"nzstats-{stamp}"
    s["05_bundle_backup"] = {"exit": r.returncode, "out": r.stdout.strip(), "seconds": round(time.time() - t0, 2), "files": sum(1 for p in bundle.rglob("*") if p.is_file())}
    s["06_verify_bundle"] = {"exit": (v := cli("verify-backup", str(bundle))).returncode, "out": v.stdout.strip()}
    s["07_status_with_backup"] = status()

    port = socket.socket()
    port.bind(("127.0.0.1", 0))
    p = port.getsockname()[1]
    port.close()
    server = subprocess.Popen([str(PY), "-c", GUARD, "serve", "--no-scheduler", "--host", "127.0.0.1", "--port", str(p)], env=ENV, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # fmt: skip
    base = f"http://127.0.0.1:{p}"
    for _ in range(100):
        try:
            urllib.request.urlopen(f"{base}/api/capabilities", timeout=1)
            break
        except OSError:
            time.sleep(0.1)
    s["08_serving_no_scheduler"] = {"status_cli": status(), "api": json.load(urllib.request.urlopen(f"{base}/api/ops/status")),
                                    "capabilities": json.load(urllib.request.urlopen(f"{base}/api/capabilities"))}  # fmt: skip
    api = s["08_serving_no_scheduler"]["api"]
    s["08_serving_no_scheduler"]["api"] = {k: api[k] for k in ("overall", "summary")} | {"collection": api["collection"]["mode"], "process": api["process"]["state"], "issue_keys": [i["key"] for i in api["issues"]]}  # fmt: skip
    ui = subprocess.run(["node", str(REPO / "docs/phase-4f-evidence/ops_ui_pass.mjs"), str(REPO / "frontend"), base, str(SCRATCH / "ui")], capture_output=True, text=True, timeout=300)
    s["09_ops_ui"] = json.loads(ui.stdout) if ui.returncode == 0 else {"error": ui.stderr[-400:]}
    ux = subprocess.run(["node", str(REPO / "docs/phase-4e-evidence/internal-readiness/ux_pass.mjs"), str(REPO / "frontend"), base, str(SCRATCH / "ux")], capture_output=True, text=True, timeout=600)  # noqa: E501
    if ux.returncode == 0:
        summary = json.loads(ux.stdout)
        rows = json.loads((SCRATCH / "ux" / "ux-results.json").read_text())["results"]
        outlook = [r for r in rows if r["route"] == "/economic-outlook"]
        s["10_all_routes"] = {
            "views": summary["views"], "problem_views": summary["problemViews"], "page_errors": sum(len(r["pageErrors"]) for r in rows),
            "external_requests": sum(len(r["external"]) for r in rows), "exports": summary["exports"],
            "economic_outlook_failed_api_responses": sorted({f for r in outlook for f in r["failedApi"]}),
            "economic_outlook_console_errors": sorted({c for r in outlook for c in r["consoleErrors"]}),
        }  # fmt: skip
    else:
        s["10_all_routes"] = {"error": ux.stderr[-400:]}
    server.send_signal(signal.SIGHUP)  # the terminal is closed
    server.wait(timeout=30)
    s["11_after_sighup"] = status()
    rows_ = sqlite3.connect(DATA / "nzstats.db").execute("SELECT stop_reason, scheduler_enabled FROM ops_process ORDER BY id DESC LIMIT 1").fetchone()
    s["11_after_sighup"]["recorded_stop"] = {"stop_reason": rows_[0], "scheduler_enabled": rows_[1]}

    r = cli("restore-backup", str(bundle), str(SCRATCH / "restored"))
    s["12_restore"] = {"exit": r.returncode, "out": r.stdout.strip(), "counts_equal": counts(SCRATCH / "restored" / "nzstats.db") == s["01_copy_counts"] | {"ingest_run": counts(DATA / "nzstats.db")["ingest_run"]} or counts(SCRATCH / "restored" / "nzstats.db") == counts(DATA / "nzstats.db")}  # fmt: skip
    s["12_restore"]["raw_files"] = sum(1 for _ in (SCRATCH / "restored" / "raw").rglob("*") if _.is_file())
    r2 = cli("restore-backup", str(bundle), str(SCRATCH / "restored"))
    s["12_restore"]["second_restore_into_same_dir_refused"] = r2.returncode == 1

    first = cli("alert-check", "--channels", "file")
    lines1 = (DATA / "ops" / "alerts.jsonl").read_text().splitlines() if (DATA / "ops" / "alerts.jsonl").exists() else []
    second = cli("alert-check", "--channels", "file")
    lines2 = (DATA / "ops" / "alerts.jsonl").read_text().splitlines() if (DATA / "ops" / "alerts.jsonl").exists() else []
    s["13_alert_check"] = {"first_exit": first.returncode, "delivered_lines": len(lines1), "second_exit": second.returncode, "lines_after_repeat": len(lines2),
                           "keys": sorted(a["key"] for line in lines1 for a in json.loads(line)["alerts"])}  # fmt: skip
    results["network_guard_refusals"] = sum(len(json.loads(x)) for x in GUARD_LOG.read_text().splitlines() if x.strip())
    results["guarded_processes"] = len([x for x in GUARD_LOG.read_text().splitlines() if x.strip()])
    after = prod_fingerprint()
    results["production_data_unchanged"] = before == after
    results["production_fingerprint"] = after
    (SCRATCH / "results.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


main()
