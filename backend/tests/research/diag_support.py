"""Shared synthetic fixture for the Phase 4V diagnostics tests: a summary stored as verify-4 graded it (SYNTHETIC FIXTURE)."""

import json
import sqlite3
from datetime import date

from nzstats.research import summary_store as ss
from nzstats.research.contract import ModelProvenance, assemble, parse_draft
from nzstats.research.summarise import load_sections
from nzstats.research.verify import VerificationContext, verify
from nzstats.store.db import transaction

from .llm_support import NOW, seed_version

VOTE = (
    "The Monetary Policy Committee today voted 4:3 to hold the Official Cash Rate at 2.75 percent."
)
CPI = "Annual CPI inflation was 3.7% in the September 2026 quarter, up from 3.3% in the June 2026 quarter."
BRENT = "Brent crude averaged US$82 a barrel in October 2026."
FORWARD = "The Committee expects inflation to ease after it agreed to hold the Official Cash Rate at 2.75 percent."
SECRET = "SYNTHETIC-SECRET-MARKER"
SECTIONS = (
    f"SYNTHETIC FIXTURE. {VOTE} {SECRET}",
    f"SYNTHETIC FIXTURE. {CPI} {BRENT}",
    f"SYNTHETIC FIXTURE. {FORWARD}",
)


def ev(version_id, section, quote, page=None):
    return {
        "version_id": version_id,
        "section_ordinal": section,
        "page": page or section + 1,
        "quote": quote,
    }


def output(v: int) -> dict:
    return {
        "outlook": {"text": "Policy held; inflation rose.", "evidence": [ev(v, 1, "Annual CPI inflation was 3.7%")]},
        "indicators": ["ocr", "cpi_inflation"],
        "forecasts": [],
        "decisions": [
            {"action": "hold", "rate": 2.75, "decided_on": "2026-10-28", "vote_for": 4, "vote_against": 3,
             "decision_maker": "Monetary Policy Committee", "evidence": [ev(v, 0, VOTE.rstrip("."))]},
            {"action": "hold", "rate": 2.75, "decided_on": "2026-10-28",
             "decision_maker": "Monetary Policy Committee", "evidence": [ev(v, 2, FORWARD.rstrip("."))]},
        ],
        "facts": [
            {"text": "CPI inflation was 3.7%.", "source": "Stats NZ", "value": 3.7, "unit": "percent",
             "period": "September 2026 quarter", "evidence": [ev(v, 1, CPI.rstrip("."))]},
            {"text": "Brent crude averaged US$82.", "source": "Stats NZ", "value": 82, "unit": None,
             "period": "October 2026", "evidence": [ev(v, 1, BRENT.rstrip("."))]},
        ],
    }  # fmt: skip


def store_verify_4_summary(conn: sqlite3.Connection, build=output, sections=SECTIONS):
    """One summary stored as verify-4 graded it, as summary 4 is stored: (connection, summary id, verify-4 report).

    `build(version_id)` returns the stored output as a dict; tests pass a variant to reproduce one shape at a time."""
    version_id = seed_version(conn, sections, key="rbnz", published_on="2026-10-28")
    prov = ModelProvenance(provider="openrouter", model="m", prompt_version="outlook-v5", processing_version="3b-1",
                           parameters={}, input_text_sha256="b" * 64, created_at=NOW)  # fmt: skip
    summary = assemble(
        parse_draft(json.dumps(build(version_id))), version_id=version_id, provenance=prov
    )
    ctx = VerificationContext(published_on=date(2026, 10, 28), institution="rbnz")
    report = verify(summary, load_sections(conn, version_id), ctx, version="verify-4")
    key = ss.SummaryKey(version_id, "openrouter", "m", "outlook-v5", "3b-1", "b" * 64)
    run = ss.start_run(conn, provider="openrouter", model="m", hosted=True, prompt_version="outlook-v5",
                       processing_version="3b-1", limits={}, dry_run=False, now=NOW)  # fmt: skip
    raw = summary.model_dump_json()
    with transaction(conn):
        sid = ss.insert_summary(
            conn, key, run_id=run, attempt=1, hosted=True, verifier_version="verify-4", parameters={},
            raw_output=raw, output_json=raw, status="failed_verification", error_class=None,
            verification=report.to_json(), now=NOW,
        )  # fmt: skip
    return conn, sid, report
