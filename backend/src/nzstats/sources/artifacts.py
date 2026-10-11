"""Content-addressed raw artifact storage (raw bytes are kept for audit and reprocessing)."""

from __future__ import annotations

import hashlib
import os
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
            tmp = target.with_suffix(".tmp")
            tmp.write_bytes(result.body)
            os.replace(tmp, target)
        return ArtifactRecord(
            url=result.url,
            sha256=sha,
            fetched_at=result.fetched_at,
            http_status=result.status,
            content_type=result.content_type,
            size_bytes=len(result.body),
            path=rel,
        )
