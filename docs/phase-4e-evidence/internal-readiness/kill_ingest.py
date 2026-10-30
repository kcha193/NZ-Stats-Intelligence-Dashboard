"""SIGKILL a real ingest inside its write transaction, then prove last-known-good survives and a retry works.

Run from backend/ (so `tests` imports): python kill_ingest.py <empty dir>. Uses the test suite's FakeSite
(real official fixture files, no network) and the real runtime, pipeline and SQLite store.
"""

import os
import signal
import sqlite3
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

NOW = datetime(2026, 10, 1, tzinfo=UTC)


def runtime(data_dir):
    from nzstats.config import load_settings
    from nzstats.runtime import build_runtime
    from tests.support import BASE, FakeSite

    settings = load_settings({"NZSTATS_DATA_DIR": str(data_dir), "NZSTATS_BASE_URL": BASE})
    return build_runtime(settings, fetcher=FakeSite().fetcher())


def child(data_dir, mode):
    from nzstats.pipeline.ingest import ingest_release
    from nzstats.store import repo
    from tests.support import release_ref_for

    rt = runtime(data_dir)
    keys = []
    for m in ("2026-06", "2026-07"):
        ref = release_ref_for(m)
        repo.upsert_release(rt.conn, ref, NOW)
        keys.append(ref.release_key)
    if mode == "seed":
        print(ingest_release(rt, keys[0], now_fn=lambda: NOW).outcome)
        return
    if mode == "hang":
        real = repo.insert_observations

        def insert_then_hang(*args, **kwargs):
            real(*args, **kwargs)
            Path(data_dir, "IN_TRANSACTION").write_text(str(os.getpid()))
            time.sleep(120)

        repo.insert_observations = insert_then_hang
    print(ingest_release(rt, keys[1], now_fn=lambda: NOW).outcome)


def state(db):
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    return {
        "integrity": c.execute("PRAGMA integrity_check").fetchone()[0],
        "fk_violations": len(c.execute("PRAGMA foreign_key_check").fetchall()),
        "vintages_by_release": dict(
            c.execute(
                "SELECT r.reference_period, COUNT(v.id) FROM release r LEFT JOIN vintage v"
                " ON v.release_id = r.id GROUP BY r.reference_period"
            ).fetchall()
        ),
        "observations": c.execute("SELECT COUNT(*) FROM observation").fetchone()[0],
        "orphan_observations": c.execute(
            "SELECT COUNT(*) FROM observation WHERE vintage_id NOT IN (SELECT id FROM vintage)"
        ).fetchone()[0],
    }


def main(data_dir):
    d = Path(data_dir)
    run = [sys.executable, __file__, str(d)]
    print(
        "seed June:", subprocess.run([*run, "seed"], capture_output=True, text=True).stdout.strip()
    )
    before = state(d / "nzstats.db")
    proc = subprocess.Popen([*run, "hang"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    for _ in range(600):
        if (d / "IN_TRANSACTION").exists():
            break
        time.sleep(0.05)
    else:
        proc.kill()
        sys.exit("ingest never reached the write transaction")
    os.kill(proc.pid, signal.SIGKILL)
    proc.wait()
    after_kill = state(d / "nzstats.db")
    retry = subprocess.run([*run, "retry"], capture_output=True, text=True)
    after_retry = state(d / "nzstats.db")
    print("before kill :", before)
    print("after SIGKILL:", after_kill, "exit", proc.returncode)
    print("retry outcome:", retry.stdout.strip() or retry.stderr[-400:])
    print("after retry :", after_retry)
    ok = (
        after_kill == before
        and after_retry["integrity"] == "ok"
        and after_retry["vintages_by_release"]["2026-07"] > 0
        and after_retry["vintages_by_release"]["2026-06"]
        == before["vintages_by_release"]["2026-06"]
        and after_retry["orphan_observations"] == 0
    )
    print("RESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    if len(sys.argv) == 3:
        child(sys.argv[1], sys.argv[2])
    else:
        main(sys.argv[1])
