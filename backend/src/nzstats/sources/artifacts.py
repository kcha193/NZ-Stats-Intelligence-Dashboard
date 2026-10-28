"""Content-addressed raw artifact storage (raw bytes are kept for audit and reprocessing)."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from collections.abc import Iterator
from pathlib import Path

from nzstats.sources.fetcher import FetchResult
from nzstats.store.repo import ArtifactRecord

_REL = re.compile(r"^[0-9a-f]{2}/[0-9a-f]{64}$")


def valid_rel(rel: str) -> bool:
    """Whether `rel` has the shape this store writes (`ab/<64 hex>`): nothing else is ever read or removed."""
    return bool(_REL.fullmatch(rel or ""))


class ArtifactStore:
    def __init__(self, raw_dir: Path) -> None:
        self._dir = raw_dir

    @property
    def root(self) -> Path:
        return self._dir

    def rel_for(self, body: bytes) -> str:
        sha = hashlib.sha256(body).hexdigest()
        return f"{sha[:2]}/{sha}"

    def exists(self, rel: str) -> bool:
        return valid_rel(rel) and (self._dir / rel).is_file()

    def remove(self, rel: str) -> bool:
        """Delete one stored file; False when it was already gone. Refuses any name this store would not write."""
        if not valid_rel(rel):
            raise ValueError("not a stored artifact name")
        try:
            (self._dir / rel).unlink()
        except FileNotFoundError:
            return False
        return True

    def files(self) -> Iterator[Path]:
        """Every stored artifact file and every leftover temporary file, without following links."""
        if not self._dir.is_dir():
            return
        for sub in sorted(self._dir.iterdir()):
            if sub.is_dir() and not sub.is_symlink():
                for path in sorted(sub.iterdir()):
                    if path.is_file() and not path.is_symlink():
                        yield path

    def save(self, result: FetchResult) -> ArtifactRecord:
        sha = hashlib.sha256(result.body).hexdigest()
        rel = f"{sha[:2]}/{sha}"
        target = self._dir / rel
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            # A temp name per writer: the scheduler and a CLI process may save the same bytes at once,
            # and a shared temp path would be renamed away under the slower one. Identical content
            # makes whichever replace lands last harmless.
            fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=f".{sha}.", suffix=".tmp")
            try:
                os.fchmod(fd, 0o644)  # mkstemp creates 0600; backups run as other host users
                with os.fdopen(fd, "wb") as fh:
                    fh.write(result.body)
                os.replace(tmp, target)
            except BaseException:
                Path(tmp).unlink(missing_ok=True)
                raise
        return ArtifactRecord(
            url=result.url,
            sha256=sha,
            fetched_at=result.fetched_at,
            http_status=result.status,
            content_type=result.content_type,
            size_bytes=len(result.body),
            path=rel,
        )
