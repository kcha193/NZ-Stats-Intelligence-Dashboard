"""Table-derived figures on the internal bank routes (Phase 4AF): labelled by method, same gate, same allowlist."""

from decimal import Decimal

import pytest

from nzstats.research.table_store import store_extraction

from .conftest import NOW
from .test_bank_api import (
    BASE,
    LOCAL,
    bank_app,  # noqa: F401 (a fixture: pytest finds it by this name)
    get,
)
from .test_table_store import SHA, tf


@pytest.fixture()
def app(bank_app):  # noqa: F811
    return bank_app


def version_of(conn, key):
    return conn.execute(
        "SELECT v.id FROM research_document_version v JOIN research_publication p ON p.id = v.publication_id"
        " JOIN research_institution i ON i.id = p.institution_id WHERE i.key = ? ORDER BY v.id DESC", (key,)
    ).fetchone()[0]  # fmt: skip


def add_table(conn, key="bank_b", value="2.9", **kw):
    row = dict(label="OCR (%)", indicator="ocr", horizon="June 2026 quarter",
               value=Decimal(value), raw_text=value, unit="percent")  # fmt: skip
    return store_extraction(
        conn, version_of(conn, key), NOW, [tf(**{**row, **kw})], [], words_sha256=SHA
    )


def test_forecasts_say_how_each_figure_was_read(app):
    client, conn = app
    add_table(conn)
    body = get(client(), "forecasts").json()
    methods = {f["claim_path"].split("[")[0]: f["extraction_method"] for f in body["forecasts"]}
    assert methods == {"forecasts": "llm_verified", "tables": "table"}
    (table,) = [f for f in body["forecasts"] if f["extraction_method"] == "table"]
    assert table["forecast"]["value"] == 2.9 and table["forecast"]["institution"]["key"] == "bank_b"
    assert table["forecast"]["evidence"][0]["page"] == 1
    # the figure; the CPI claim; and a GDP claim whose measure has no readable basis
    assert body["table_reconciliation"] == {"ambiguous_or_unsupported": 1, "no_counterpart": 2}


def test_a_table_figure_that_contradicts_a_checked_claim_is_left_out_of_both(app):
    client, conn = app
    # bank B's checked claim says 2.2 for this measure and period
    add_table(
        conn,
        "bank_b",
        "9.9",
        label="Annual CPI inflation (%)",
        indicator="cpi_inflation",
        horizon="year to June 2027",
    )
    body = get(client(), "forecasts").json()
    codes = [e["code"] for e in body["excluded"] if e["institution_key"] == "bank_b"]
    assert codes.count("conflicting_forecasts") == 2
    shown = {
        r["forecast"]["value"]
        for c in body["comparison"]
        for g in c["comparison"]["groups"]
        for r in g["rows"]
        if r["forecast"]["institution"]["key"] == "bank_b"
    }
    assert 9.9 not in shown and 2.2 not in shown
    assert body["table_reconciliation"] == {
        "contradictory_value": 1,
        "ambiguous_or_unsupported": 1,
    }  # the GDP claim has no readable basis


def test_every_route_still_answers_with_table_figures_present(app):
    client, conn = app
    add_table(conn)
    for route in ("summary", "forecasts", "revisions", "consensus", "evaluation", "freshness"):
        assert get(client(), route).status_code == 200, route


def test_table_figures_need_the_gate_to_be_on(app):
    client, conn = app
    add_table(conn)
    assert client(enabled=False).get(f"{BASE}/forecasts", headers=LOCAL).status_code == 404
