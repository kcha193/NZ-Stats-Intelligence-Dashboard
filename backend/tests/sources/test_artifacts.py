import hashlib
from datetime import UTC, datetime
from pathlib import Path

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
