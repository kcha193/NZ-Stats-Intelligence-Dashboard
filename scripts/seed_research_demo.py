"""Seed SYNTHETIC research summaries for UI tests and screenshots. Usage: python scripts/seed_research_demo.py DIR

Adds research rows to DIR/nzstats.db (on top of any Stats NZ data already there) and writes
DIR/research_sources.synthetic.toml, a registry of four fictional institutions with display permission. Every
institution, document and sentence is invented and marked SYNTHETIC FIXTURE. The summaries go through the real
verifier, review and publication functions, so they are exactly what the public API would serve. Never point a
production deployment at this registry.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from nzstats.research import summary_store as ss  # noqa: E402
from nzstats.research.registry import load_registry  # noqa: E402
from nzstats.store.db import connect, migrate  # noqa: E402
from tests.research.llm_support import NOW, seed_version  # noqa: E402
from tests.research.public_support import store_summary  # noqa: E402

HOST = "research.example.org"
SYN = "SYNTHETIC FIXTURE. "


def ev(version: int, ordinal: int, quote: str) -> dict:
    return {"version_id": version, "section_ordinal": ordinal, "page": ordinal + 1, "quote": quote}


def claim(version, ordinal, quote, indicator, label, horizon, value, direction, unit="percent", **kw) -> dict:
    return {"indicator": indicator, "indicator_label": label, "horizon": horizon, "value": value,
            "unit": unit if value is not None else None, "direction": direction,
            "evidence": [ev(version, ordinal, quote)], **kw}  # fmt: skip


INSTITUTIONS = {
    "harbourside": ("Harbourside Bank (synthetic)", "bank", "excerpt"),
    "kauri": ("Kauri Economics (synthetic)", "consultancy", "excerpt"),
    "southern": ("Southern Treasury Office (synthetic)", "government", "summary"),
    "tasman": ("Tasman Markets (synthetic)", "bank", "link_only"),
}


def registry_toml() -> str:
    out = ["# SYNTHETIC FIXTURE registry for UI tests. Fictional institutions; never used in production.\n"]
    for key, (name, kind, level) in INSTITUTIONS.items():
        out.append(f"""
[institutions.{key}]
name = "{name}"
kind = "{kind}"
allowed_hosts = ["{HOST}"]
landing_urls = ["https://{HOST}/research/"]
categories = ["economic_outlook"]
review_status = "approved"
content_policy = "full_text"
robots_evidence = "direct"
landing_evidence = "direct"
terms_evidence = "direct"
licence = "Synthetic test licence"
approved_by = "Synthetic Fixture"
approved_on = "2026-10-25"
approval_note = "synthetic test source"
llm_processing = "local_only"
llm_processing_note = "synthetic"
public_display = "{level}"
public_display_approved_by = "Synthetic Fixture"
public_display_approved_on = "2026-10-26"
public_display_note = "synthetic test source: display permitted"
""")
    return "".join(out)


def harbourside(conn) -> None:
    s = [
        SYN + "Annual CPI inflation is forecast to ease to 2.3% in the year to June 2027 as fuel prices settle.",
        "We expect GDP annual average growth of 1.8% in the year to March 2027, with household spending recovering slowly.",
        "The OCR is forecast to be 2.75% in December 2026, with little room for further cuts.",
        "In a downside scenario with weaker export prices, annual CPI inflation would fall to 1.6% in the year to June 2027.",
        "A sharper slowdown in China would weigh on dairy prices. Uncertainty about the housing market remains high.",
    ]
    v = seed_version(conn, s, key="harbourside", doc="harbourside/quarterly-outlook", published_on="2026-10-08")
    store_summary(conn, v, output={
        "outlook": {"text": "Inflation is expected to ease while household spending recovers slowly.", "evidence": [
            ev(v, 0, "Annual CPI inflation is forecast to ease to 2.3% in the year to June 2027"),
            ev(v, 1, "household spending recovering slowly")]},
        "drivers": [{"text": "Fuel prices are expected to settle.", "evidence": [ev(v, 0, "as fuel prices settle")]}],
        "risks": [{"text": "A sharper slowdown in China would weigh on dairy prices.",
                   "evidence": [ev(v, 4, "A sharper slowdown in China would weigh on dairy prices")]}],
        "uncertainty": {"text": "Uncertainty about the housing market remains high.",
                        "evidence": [ev(v, 4, "Uncertainty about the housing market remains high")]},
        "indicators": ["cpi_inflation", "gdp", "ocr"],
        "forecasts": [
            claim(v, 0, "forecast to ease to 2.3% in the year to June 2027", "cpi_inflation", "Annual CPI inflation",
                  "year to June 2027", 2.3, "down"),
            claim(v, 1, "We expect GDP annual average growth of 1.8% in the year to March 2027", "gdp",
                  "GDP, annual average growth", "year to March 2027", 1.8, "up"),
            claim(v, 2, "The OCR is forecast to be 2.75% in December 2026", "ocr", "OCR", "December 2026", 2.75, "flat"),
            claim(v, 3, "In a downside scenario with weaker export prices, annual CPI inflation would fall to 1.6% in"
                  " the year to June 2027", "cpi_inflation", "Annual CPI inflation", "year to June 2027", 1.6, "down",
                  scenario="Downside", qualification="Weaker export prices"),
        ],
    })  # fmt: skip
    # A rejected and an unreviewed summary of a second document: neither may ever appear publicly.
    r = seed_version(conn, [SYN + "REJECTED DRAFT TEXT. Inflation is forecast to rise sharply in the year to June 2027."],
                     key="harbourside", doc="harbourside/rejected", published_on="2026-10-20")  # fmt: skip
    rejected = {"outlook": {"text": "REJECTED SUMMARY TEXT: inflation is forecast to rise sharply.", "evidence": [
        ev(r, 0, "Inflation is forecast to rise sharply in the year to June 2027")]}}
    store_summary(conn, r, output=rejected, review="rejected", publish=False)
    u = seed_version(conn, [SYN + "UNREVIEWED DRAFT TEXT. Growth is forecast to slow in the year to March 2027."],
                     key="harbourside", doc="harbourside/unreviewed", published_on="2026-10-21")  # fmt: skip
    store_summary(conn, u, output={"outlook": {"text": "UNREVIEWED SUMMARY TEXT: growth is forecast to slow.",
                                               "evidence": [ev(u, 0, "Growth is forecast to slow in the year to March 2027")]}},
                  review=None, publish=False)  # fmt: skip


def kauri(conn) -> None:
    s = [
        SYN + "We forecast annual CPI inflation of 2.1% in the year to June 2027.",
        "Real GDP growth (y/y) is forecast at 2.0% in the year to March 2027.",
        "On an annual average basis, GDP growth is forecast at 1.5% in the year to March 2027.",
        "The unemployment rate is forecast to be 5.4% in the December 2026 quarter.",
        "We expect the OCR to be 2.5% in December 2026.",
        "Growth should improve next year as interest rates fall.",
    ]
    v = seed_version(conn, s, key="kauri", doc="kauri/spring-forecasts", published_on="2026-09-24")
    store_summary(conn, v, output={
        "outlook": {"text": "Growth should improve as interest rates fall.",
                    "evidence": [ev(v, 5, "Growth should improve next year as interest rates fall")]},
        "drivers": [{"text": "Lower interest rates are expected to support growth.",
                     "evidence": [ev(v, 5, "as interest rates fall")]}],
        "indicators": ["cpi_inflation", "gdp", "unemployment", "ocr"],
        "forecasts": [
            claim(v, 0, "We forecast annual CPI inflation of 2.1% in the year to June 2027", "cpi_inflation",
                  "Annual CPI inflation", "year to June 2027", 2.1, "down"),
            claim(v, 1, "Real GDP growth (y/y) is forecast at 2.0% in the year to March 2027", "gdp",
                  "Real GDP growth (y/y)", "year to March 2027", 2.0, "up"),
            claim(v, 2, "GDP growth is forecast at 1.5% in the year to March 2027", "gdp", "GDP, annual average growth",
                  "year to March 2027", 1.5, "up"),
            claim(v, 3, "The unemployment rate is forecast to be 5.4% in the December 2026 quarter", "unemployment",
                  "Unemployment rate", "December 2026 quarter", 5.4, "up"),
            claim(v, 4, "We expect the OCR to be 2.5% in December 2026", "ocr", "OCR", "December 2026", 2.5, "down"),
            claim(v, 5, "Growth should improve next year", "gdp", "Economic growth", "next year", None, "up"),
        ],
    })  # fmt: skip


def southern(conn) -> None:
    s = [
        SYN + "Annual CPI inflation is forecast to be 2.4% in the year to June 2027.",
        "Economic growth is forecast to be 1.2% in the year to March 2027.",
        "Net core Crown debt is forecast to reach 43.5% of GDP in the year to June 2027.",
        "Weaker growth would add to government debt.",
    ]
    v = seed_version(conn, s, key="southern", doc="southern/fiscal-update", published_on="2026-10-15")
    store_summary(conn, v, output={
        "outlook": {"text": "Inflation is forecast to settle while government debt rises.", "evidence": [
            ev(v, 0, "Annual CPI inflation is forecast to be 2.4% in the year to June 2027"),
            ev(v, 2, "Net core Crown debt is forecast to reach 43.5% of GDP")]},
        "risks": [{"text": "Weaker growth would add to government debt.",
                   "evidence": [ev(v, 3, "Weaker growth would add to government debt")]}],
        "indicators": ["cpi_inflation", "gdp", "government_debt"],
        "forecasts": [
            claim(v, 0, "Annual CPI inflation is forecast to be 2.4% in the year to June 2027", "cpi_inflation",
                  "Annual CPI inflation", "year to June 2027", 2.4, "down"),
            claim(v, 1, "Economic growth is forecast to be 1.2% in the year to March 2027", "gdp", "Economic growth",
                  "year to March 2027", 1.2, "up"),
            claim(v, 2, "Net core Crown debt is forecast to reach 43.5% of GDP in the year to June 2027",
                  "government_debt", "Net core Crown debt", "year to June 2027", 43.5, "up", unit="percent_of_gdp"),
        ],
    })  # fmt: skip


def tasman(conn) -> None:
    s = [SYN + "Annual CPI inflation is forecast to be 2.6% in the year to June 2027."]
    v = seed_version(conn, s, key="tasman", doc="tasman/weekly-commentary", published_on="2026-09-02")
    store_summary(conn, v, output={
        "outlook": {"text": "Inflation is forecast to keep easing.",
                    "evidence": [ev(v, 0, "Annual CPI inflation is forecast to be 2.6% in the year to June 2027")]},
        "indicators": ["cpi_inflation"],
        "forecasts": [claim(v, 0, "forecast to be 2.6% in the year to June 2027", "cpi_inflation",
                            "Annual CPI inflation", "year to June 2027", 2.6, "down")],
    })  # fmt: skip


TITLES = {
    "harbourside/quarterly-outlook": "Quarterly Economic Outlook, October 2026 (synthetic)",
    "harbourside/rejected": "Inflation Update, rejected draft (synthetic)",
    "harbourside/unreviewed": "Growth Update, unreviewed draft (synthetic)",
    "kauri/spring-forecasts": "Economic Forecasts, Spring 2026 (synthetic)",
    "southern/fiscal-update": "Fiscal and Economic Update 2026 (synthetic)",
    "tasman/weekly-commentary": "Weekly Market Commentary (synthetic)",
}


def retitle(conn) -> None:
    """Readable titles; the shared test helper names documents after their path."""
    for doc, title in TITLES.items():
        url = f"https://{HOST}/{doc}"
        conn.execute("UPDATE research_publication SET title = ? WHERE canonical_url = ?", (title, url))
        conn.execute("UPDATE research_document_version SET title = ? WHERE publication_id ="
                     " (SELECT id FROM research_publication WHERE canonical_url = ?)", (title, url))  # fmt: skip


def main(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    registry_file = target / "research_sources.synthetic.toml"
    registry_file.write_text(registry_toml(), encoding="utf-8")
    load_registry(registry_file)  # the loader's own checks, so a bad fixture fails here
    conn = connect(target / "nzstats.db")
    migrate(conn)
    for seed in (harbourside, kauri, southern, tasman):
        seed(conn)
    retitle(conn)
    statuses = [(r["institution"], r["status"], r["review_status"]) for r in ss.list_summaries(conn)]
    failed = [s for s in statuses if s[1] != "verified"]
    if failed:
        raise SystemExit(f"synthetic summaries failed verification: {failed}")
    print(f"seeded {len(statuses)} synthetic summaries ({NOW.date()}) and {registry_file.name}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
