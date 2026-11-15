"""Phase 4AI: under the real registry, an ANZ report imported by hand is read locally and goes nowhere else.

The document is a SYNTHETIC FIXTURE with fictitious figures under an address that matches ANZ's outlook route; no ANZ text or
figure is used. It proves the owner's personal-research scope end to end: the manual import is accepted, the deterministic
table reader stores figures, and neither the public research feed nor the private research gate shows anything of ANZ.
"""

import socket
from datetime import date

import pytest

from nzstats.research.api import research_router
from nzstats.research.manual_import import import_document
from nzstats.research.private_api import CLIENT_HEADER, private_research_router
from nzstats.research.registry import load_registry
from nzstats.research.table_ingest import extract_version_tables
from nzstats.research.table_store import load_forecasts
from nzstats.sources.artifacts import ArtifactStore

from .bank_support import assert_anz_holds_only_the_personal_scope
from .conftest import NOW
from .pdf_table_support import table_pdf
from .test_table_forecast import line, page

QEO_URL = "https://www.anz.co.nz/content/dam/anzconz/documents/economics-and-market-research/2026/ANZ-QEO-20261111.pdf"
LOCAL = {"host": "127.0.0.1:8000", CLIENT_HEADER: "dashboard"}
PROSE = "SYNTHETIC FIXTURE prose page for a fictitious outlook; it carries no real forecast, text or figure at all."


def synthetic_outlook_pdf() -> bytes:
    """A forecast table on page 1 and enough prose on page 2 to clear the registry's 500-character floor (SYNTHETIC)."""
    table = page([
        *line(686, "OCR (%)", ["4.25", "3.75", "3.25", "3.00"]),
        *line(672, "Annual CPI inflation (%)", ["4", "3", "2.6", "2.2"]),
    ])  # fmt: skip
    prose = [(72, 700 - 14 * i, PROSE) for i in range(8)]
    return table_pdf([table, prose])


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("the Phase 4AI scope must not use the network")

    monkeypatch.setattr(socket.socket, "connect", refuse)


def test_a_hand_imported_anz_report_is_read_locally_and_reaches_no_public_or_private_route(
    make, tmp_path
):
    build, conn = make
    registry = load_registry()
    anz = registry["anz"]
    assert_anz_holds_only_the_personal_scope(anz)
    artifacts = ArtifactStore(tmp_path / "raw")

    result = import_document(
        conn, anz, body=synthetic_outlook_pdf(), file_format="pdf", url=QEO_URL, importer="Test Owner",
        note="SYNTHETIC FIXTURE: not an ANZ document", now=NOW, artifacts=artifacts,
        published_on=date(2026, 11, 11),
    )  # fmt: skip
    extracted = extract_version_tables(
        conn, result.version_id, artifacts, registry, NOW, isolate=False
    )
    assert extracted.status == "stored" and extracted.forecasts > 0
    assert load_forecasts(conn, result.version_id)  # the internal gate has figures to show

    client = build(
        routers=[
            research_router(enabled=True, registry=lambda: registry),
            private_research_router(enabled=True, registry=lambda: registry),
        ]
    )
    for route, headers in (("/api/research/feed", {}), ("/api/private/research/items", LOCAL)):
        response = client.get(route, headers=headers)
        assert response.status_code == 200, (
            route
        )  # the gate answered: an empty answer, not a missing route
        body = response.text
        assert "anz" not in body.lower() and "ANZ-QEO" not in body, route
