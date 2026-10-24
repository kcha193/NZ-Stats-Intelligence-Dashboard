"""Whether a data directory holds real ingested data or data built from test fixtures.

Fixture files are real excerpts of official files, and some are byte-identical to production downloads, so
content cannot tell them apart. Provenance is recorded instead: any runtime built with an injected fetcher (tests,
the e2e seed, fixture dumps) marks its data directory, and a production runtime never does.
"""

from __future__ import annotations

from pathlib import Path

FIXTURE_MARKER = "FIXTURE_DATA"
_NOTE = (
    "This data directory was written by a runtime with an injected fetcher (test or fixture data).\n"
    "It must never be published as Stats NZ releases.\n"
)


def mark_fixture_data(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    marker = data_dir / FIXTURE_MARKER
    if not marker.exists():
        marker.write_text(_NOTE, encoding="utf-8")


def is_fixture_data(data_dir: Path) -> bool:
    return (data_dir / FIXTURE_MARKER).exists()
