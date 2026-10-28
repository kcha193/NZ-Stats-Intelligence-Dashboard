"""Cross-process coordination of Stats NZ artifact registration and orphan cleanup."""

import os
import subprocess
import sys
import time

import pytest

from nzstats.pipeline.ingest import ingest_release
from nzstats.research import purge
from tests.cpi_support import NOW, seed_cpi


@pytest.mark.parametrize("target", ["page", "cpi_index_numbers", "cpi_workbook"])
def test_old_orphan_cannot_be_swept_between_save_and_registration(rt, site, monkeypatch, target):
    _, key, page_url, downloads = seed_cpi(rt, site)
    target_url = page_url if target == "page" else downloads[target]
    body = site.routes[target_url][1]
    path = rt.artifacts.root / rt.artifacts.rel_for(body)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    old = time.time() - 7200
    os.utime(path, (old, old))
    real_save = rt.artifacts.save
    sweep = []

    def save(result):
        rec = real_save(result)
        if result.url == target_url:
            # A separate process makes a nonblocking sweep attempt exactly after save.
            script = """
import sqlite3, sys
from pathlib import Path
from nzstats.research.purge import remove_orphan_files
from nzstats.sources.artifacts import ArtifactStore
conn = sqlite3.connect(sys.argv[1], timeout=0, isolation_level=None)
try:
    print(remove_orphan_files(conn, ArtifactStore(Path(sys.argv[2])), older_than_seconds=3600))
except sqlite3.OperationalError as e:
    if 'locked' not in str(e):
        raise
    print('locked')
"""
            proc = subprocess.run(
                [sys.executable, "-c", script, str(rt.settings.db_path), str(rt.artifacts.root)],
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )
            sweep.append(proc.stdout.strip())
        return rec

    monkeypatch.setattr(rt.artifacts, "save", save)
    outcome = ingest_release(rt, key, now_fn=lambda: NOW)
    assert outcome.outcome == "ingested", outcome.detail
    row = rt.conn.execute("SELECT path FROM raw_artifact WHERE url=?", (target_url,)).fetchone()
    assert row is not None and path.exists() and row[0] == str(path.relative_to(rt.artifacts.root))
    assert sweep == ["locked"]
    assert purge.remove_orphan_files(rt.conn, rt.artifacts, older_than_seconds=3600) == 0
    assert path.exists()


def test_failed_registration_rolls_back_and_retry_reuses_orphan(rt, monkeypatch):
    from nzstats.pipeline.ingest import _record_raw
    from nzstats.sources.fetcher import FetchResult
    from nzstats.store import repo

    result = FetchResult("https://example.test/file", 200, "text/plain", b"test bytes", NOW)
    path = rt.artifacts.root / rt.artifacts.rel_for(result.body)
    record = repo.record_artifact

    def fail(conn, rec):
        record(conn, rec)
        raise ValueError("test rollback")

    monkeypatch.setattr(repo, "record_artifact", fail)
    with pytest.raises(ValueError, match="test rollback"):
        _record_raw(rt, result)
    assert rt.conn.execute("SELECT COUNT(*) FROM raw_artifact").fetchone()[0] == 0
    assert path.exists() and not rt.conn.in_transaction
    monkeypatch.setattr(repo, "record_artifact", record)
    _record_raw(rt, result)
    assert rt.conn.execute("SELECT COUNT(*) FROM raw_artifact").fetchone()[0] == 1
    assert (
        path.exists()
        and purge.remove_orphan_files(rt.conn, rt.artifacts, older_than_seconds=0) == 0
    )
