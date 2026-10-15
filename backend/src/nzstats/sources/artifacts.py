"""Content-addressed raw artifact storage (raw bytes are kept for audit and reprocessing)."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from nzstats.sources.fetcher import FetchResult
from nzstats.store.repo import ArtifactRecord


class ArtifactStore:
    def __init__(self, raw_dir: Path) -> None:
        self._dir = raw_dir

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
