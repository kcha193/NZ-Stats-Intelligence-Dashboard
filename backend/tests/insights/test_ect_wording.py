"""ECT insight sentences: natural wording grounded in verified observations (audit finding F2)."""

import re

import pytest

from nzstats.insights.ect import build_ect_dashboard
from nzstats.pipeline.ingest import ingest_release
from nzstats.store import repo
from tests.ect_support import NOW, seed_ect


@pytest.fixture
def analysis(rt, site):
    _, key, _ = seed_ect(rt, site)
    assert ingest_release(rt, key, now_fn=lambda: NOW).outcome == "ingested"
    return build_ect_dashboard(rt.conn).analysis


def texts(analysis):
    return {i.id: i.text for i in analysis.executive_summary + analysis.context}


def test_monthly_headlines_are_plain_sentences_with_adjustment_period_and_units(analysis):
    t = texts(analysis)
    assert t["retail"] == (
        "Seasonally adjusted retail card spending decreased 0.4% in September 2026 "
        "(NZD 6,976.0 million, down NZD 30.0 million from August 2026)."
    )
    assert t["core"].startswith(
        "Seasonally adjusted core retail card spending decreased 0.7% in September 2026"
    )
    assert t["total"].startswith(
        "Seasonally adjusted total electronic card spending decreased 0.5% in September 2026"
    )


def test_quarterly_headlines_name_the_quarter_and_adjustment(analysis):
    t = texts(analysis)
    assert t["quarter-retail"] == (
        "Retail card spending increased 0.1% in the September 2026 quarter "
        "(seasonally adjusted), compared with the June 2026 quarter."
    )
    assert t["quarter-core"].startswith(
        "Core retail card spending increased 0.4% in the September 2026 quarter (seasonally adjusted)"
    )


def test_industry_actual_and_context_sentences(analysis):
    t = texts(analysis)
    assert t["industry"] == (
        "Seasonally adjusted monthly card spending rose most in Fuel (+2.9%) and fell most in "
        "Hospitality (-2.3%) in September 2026."
    )
    assert t["actual"] == (
        "Unadjusted (actual) card spending totalled $9.19 billion across 166.8 million "
        "transactions in September 2026, with a mean transaction value of $55.1."
    )
    assert t["history"].startswith(
        "Seasonally adjusted retail card spending was NZD 6,976.0 million in September 2026."
    )
    assert "nominal" in t["history"] and "price changes" in t["history"]
    assert t["trend"] == (
        "Retail card spending trend was NZD 7,000.2 million in September 2026, "
        "down 0.2% from August 2026."
    )


def test_no_series_label_fragments_or_raw_timestamps_in_sentences(analysis):
    for text in texts(analysis).values():
        assert ", value" not in text, text
        assert not re.search(r"\d{4}-\d{2}-\d{2}T", text), text


def test_unchanged_headline_does_not_claim_a_direction(rt, site):
    _, key, _ = seed_ect(rt, site)
    assert ingest_release(rt, key, now_fn=lambda: NOW).outcome == "ingested"
    vid = repo.list_vintages(rt.conn, "ect.m.sa.retail.value")[-1].vintage_id
    rt.conn.execute(
        "UPDATE observation SET value=(SELECT value FROM observation WHERE vintage_id=? "
        "AND period='2026-08') WHERE vintage_id=? AND period='2026-09'",
        (vid, vid),
    )
    text = texts(build_ect_dashboard(rt.conn).analysis)["retail"]
    assert text.startswith(
        "Seasonally adjusted retail card spending was unchanged in September 2026"
    )
    assert "increased" not in text and "decreased" not in text
