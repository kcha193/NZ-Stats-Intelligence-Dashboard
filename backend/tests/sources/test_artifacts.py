import hashlib
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from nzstats.sources.artifacts import ArtifactStore
from nzstats.sources.fetcher import FetchResult


def _res(body: bytes) -> FetchResult:
    return FetchResult(
        "http://h.test/a.csv", 200, "text/csv", body, datetime(2026, 10, 11, tzinfo=UTC)
    )


def test_save_writes_content_addressed_file(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    rec = store.save(_res(b"hello"))
    sha = hashlib.sha256(b"hello").hexdigest()
    assert rec.sha256 == sha and rec.size_bytes == 5
    assert (tmp_path / rec.path).read_bytes() == b"hello"
    assert rec.path == f"{sha[:2]}/{sha}"


def test_same_bytes_are_stored_once(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    a = store.save(_res(b"same"))
    b = store.save(_res(b"same"))
    assert a.path == b.path
    assert len(list(tmp_path.rglob("*"))) == 2  # one shard dir + one file


def test_different_bytes_get_different_files(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    assert store.save(_res(b"one")).sha256 != store.save(_res(b"two")).sha256


def test_concurrent_writers_of_the_same_content_both_succeed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The scheduler and a CLI process can both see the file missing and write it at once. Simulate
    # the second writer finishing its whole save between the first writer's write and its replace.
    import nzstats.sources.artifacts as artifacts

    first, second = ArtifactStore(tmp_path), ArtifactStore(tmp_path)
    real_replace = os.replace
    interleaved = False

    def replace(src: str | Path, dst: str | Path) -> None:
        nonlocal interleaved
        if not interleaved:
            interleaved = True
            second.save(_res(b"shared"))
        real_replace(src, dst)

    monkeypatch.setattr(artifacts.os, "replace", replace)
    rec = first.save(_res(b"shared"))

    assert (tmp_path / rec.path).read_bytes() == b"shared"
    assert [p.name for p in tmp_path.rglob("*") if p.is_file()] == [rec.sha256]  # no temp left


def test_saved_files_are_readable_by_the_backup_user(tmp_path: Path) -> None:
    rec = ArtifactStore(tmp_path).save(_res(b"mode"))
    assert (tmp_path / rec.path).stat().st_mode & 0o777 == 0o644
