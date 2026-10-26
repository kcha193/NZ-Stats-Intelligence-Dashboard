"""Shared doubles for the Phase 3B tests: stored synthetic document versions and model outputs."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from nzstats.research import store
from nzstats.store.db import transaction

NOW = datetime(2026, 10, 26, 1, 0, tzinfo=UTC)
SECTIONS = (
    "SYNTHETIC FIXTURE. The economy is expected to grow 2.5% in the year to March 2027.",
    "Annual CPI inflation is forecast to fall to 2.1% in the year to June 2027.",
)


def seed_version(
    conn: sqlite3.Connection,
    sections: Sequence[str] = SECTIONS,
    *,
    key: str = "example",
    doc: str = "a",
    published_on: str | None = "2026-08-13",
    pages: bool = True,
    headings: Sequence[str | None] = (),
) -> int:
    """Store one publication with one version made of `sections` (one page each); its version id.

    `headings[i]`, when given, is the stored heading of section i (as the HTML extractor keeps them).
    """
    with transaction(conn):
        inst = store.upsert_institution(conn, key=key, name=key.title(), review_status="approved",
                                        content_policy="full_text", now=NOW)  # fmt: skip
        pub, _ = store.upsert_publication(
            conn, inst, doc_key=f"{key}:research.example.org/{doc}",
            url=f"https://research.example.org/{doc}", title=f"Synthetic outlook {doc}",
            series="outlook", categories=["economic_outlook"], published_on=published_on,
            published_at=None, precision="day" if published_on else None, content_status="extracted",
            now=NOW,
        )  # fmt: skip
        rows, offset = [], 0
        for i, text in enumerate(sections):
            page = i + 1 if pages else None
            heading = headings[i] if i < len(headings) else None
            rows.append(store.SectionRow(i, heading, text, page, page, offset, offset + len(text)))
            offset += len(text) + 1
        digest = hashlib.sha256("\n".join(sections).encode()).hexdigest()
        version, _ = store.add_version(
            conn, pub, content_sha256=digest, text_sha256=digest, fmt="pdf", fetched_at=NOW,
            extractor_version="pdf-1", raw_artifact_id=None, title=f"Synthetic outlook {doc}",
            sections=rows, page_count=len(sections) if pages else None, licence_snapshot="{}", now=NOW,
        )  # fmt: skip
    return version


def draft(version_id: int, **overrides: Any) -> dict[str, Any]:
    """A faithful model draft for `SECTIONS`."""
    data: dict[str, Any] = {
        "outlook": {"text": "Growth is expected to pick up while inflation eases.", "evidence": [
            {"version_id": version_id, "section_ordinal": 0, "page": 1,
             "quote": "The economy is expected to grow 2.5% in the year to March 2027"},
            {"version_id": version_id, "section_ordinal": 1, "page": 2,
             "quote": "Annual CPI inflation is forecast to fall to 2.1%"}]},
        "indicators": ["gdp", "cpi_inflation"],
        "forecasts": [
            {"indicator": "gdp", "indicator_label": "Economic growth", "horizon": "year to March 2027",
             "value": 2.5, "unit": "percent", "direction": "up", "evidence": [
                 {"version_id": version_id, "section_ordinal": 0, "page": 1,
                  "quote": "expected to grow 2.5% in the year to March 2027"}]},
            {"indicator": "cpi_inflation", "indicator_label": "Annual CPI inflation",
             "horizon": "year to June 2027", "value": 2.1, "unit": "percent", "direction": "down",
             "evidence": [{"version_id": version_id, "section_ordinal": 1, "page": 2,
                           "quote": "forecast to fall to 2.1% in the year to June 2027"}]},
        ],
    }  # fmt: skip
    data.update(overrides)
    return data


def draft_json(version_id: int, **overrides: Any) -> str:
    return json.dumps(draft(version_id, **overrides))
