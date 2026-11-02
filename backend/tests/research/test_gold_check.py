"""Version-bound gold packs and offline verifier probes (SYNTHETIC FIXTURE: invented text, invented issuers)."""

import hashlib

import pytest

from nzstats.research.gold_check import (
    AccuracyPack,
    GoldPackError,
    _has_number,
    check_pack,
    load_pack,
    probe_pack,
)
from nzstats.store.db import transaction

from .llm_support import seed_version

PAGE_1 = (
    "The Synthetic Bank's committee voted 5-2 to hold the OCR at 3.25% on 28 October 2026. "
    "Annual inflation was 2.9% in the September quarter, Synthetic Statistics reported. "
    "The committee expects inflation of 3.4% in the December quarter."
)
PAGE_2 = (
    "We forecast unemployment of 5.1% in the December quarter. "
    "Labour data will be released next Wednesday, and the survey follows on Friday."
)
PAGE_3 = "Coming up: 4 Nov Labour data. 30 Oct Survey."
TEXT = hashlib.sha256("\n".join((PAGE_1, PAGE_2, PAGE_3)).encode()).hexdigest()


def fact(**over):
    return {"id": "cpi", "kind": "fact", "issuer": "Synthetic Statistics", "issuer_role": "third_party",
            "named_as": "Synthetic Statistics", "page": 1,
            "quote": "Annual inflation was 2.9% in the September quarter, Synthetic Statistics reported", "text": "Annual inflation was 2.9%.",
            "value": 2.9, "unit": "percent", "period_as_stated": "September quarter",
            "period_resolved": "2026Q3", **over}  # fmt: skip


def forecast(**over):
    return {"id": "u", "kind": "forecast", "issuer": "The Author", "issuer_role": "author", "named_as": "We forecast",
            "page": 2, "quote": "We forecast unemployment of 5.1% in the December quarter", "text": "Unemployment",
            "value": 5.1, "unit": "percent", "period_as_stated": "December quarter", "period_resolved": "2026Q4",
            "indicator": "unemployment", "direction": "unclear", **over}  # fmt: skip


def decision(**over):
    return {"id": "ocr", "kind": "decision", "issuer": "Synthetic Bank", "issuer_role": "third_party",
            "named_as": "Synthetic Bank", "page": 1,
            "quote": "Synthetic Bank's committee voted 5-2 to hold the OCR at 3.25% on 28 October 2026", "text": "Held.", "value": 3.25,
            "unit": "percent", "action": "hold", "decided_on": "2026-10-28", "vote_for": 5, "vote_against": 2,
            "decision_maker": "The Synthetic Bank's committee", **over}  # fmt: skip


def relative(**over):
    return {"id": "labour", "page": 2, "quote": "Labour data will be released next Wednesday", "phrase": "next Wednesday",
            "resolved": "2026-11-04", "calendar_quote": "4 Nov Labour data", **over}  # fmt: skip


def pack(**over):
    return {"annotator": "Test Annotator", "annotated_on": "2026-11-02", "version_id": 1, "text_sha256": TEXT,
            "content_sha256": TEXT, "document_date": "2026-10-29", "published_on": "2026-11-02",
            "foreign_quote": "A sentence that only the earlier synthetic report contains.",
            "items": [fact(), forecast(), decision()], "relative_dates": [relative()], **over}  # fmt: skip


@pytest.fixture()
def stored(conn):
    version = seed_version(conn, (PAGE_1, PAGE_2, PAGE_3), published_on="2026-11-02")
    with transaction(conn):
        conn.execute("UPDATE research_publication SET title = 'Synthetic Update - 29 October 2026'")
    return conn, version


def built(**over):
    return AccuracyPack.model_validate(pack(**over))


def codes(report):
    return sorted(p.code for p in report.problems)


def test_a_true_pack_has_no_problems(stored):
    conn, _ = stored
    report = check_pack(conn, built())
    assert codes(report) == [] and report.items == 3 and report.relative_dates == 1


@pytest.mark.parametrize(
    "over",
    [
        {"version_id": 99},
        {"text_sha256": "a" * 64},
        {"content_sha256": "a" * 64},
    ],
)
def test_a_pack_written_for_another_document_is_refused(stored, over):
    conn, _ = stored
    with pytest.raises(GoldPackError):
        check_pack(conn, built(**over))


def test_a_pack_for_a_superseded_version_is_refused(stored):
    conn, _ = stored
    with transaction(conn):
        conn.execute("UPDATE research_document_version SET superseded_at = '2026-11-02T00:00:00Z'")
    with pytest.raises(GoldPackError):
        check_pack(conn, built())


@pytest.mark.parametrize(
    ("over", "code"),
    [
        ({"published_on": "2026-10-29"}, "published_on_mismatch"),
        ({"document_date": "2026-10-15"}, "document_date_not_in_title"),
        (
            {"document_date": "2026-11-03", "published_on": "2026-11-02"},
            "document_date_not_in_title",
        ),
    ],
)
def test_the_dates_must_match_the_stored_publication(stored, over, code):
    conn, _ = stored
    assert code in codes(check_pack(conn, built(**over)))


def test_a_document_date_after_publication_is_reported(stored):
    conn, _ = stored
    with transaction(conn):
        conn.execute("UPDATE research_publication SET title = 'Synthetic Update - 3 November 2026'")
    assert "document_date_after_publication" in codes(
        check_pack(conn, built(document_date="2026-11-03"))
    )


@pytest.mark.parametrize(
    ("over", "code"),
    [
        (
            {"quote": "Annual inflation was 9.9% in the September quarter, Synthetic"},
            "quote_not_found",
        ),
        ({"page": 2}, "quote_not_found"),
        ({"value": 3.9}, "value_not_in_quote"),
        ({"value": 2.0}, "value_not_in_quote"),  # 2.0 must not match the 2 inside 2.9
        ({"period_as_stated": "June quarter"}, "period_not_in_quote"),
        ({"period_resolved": "2026Q4"}, "period_resolved_mismatch"),
        ({"named_as": "Another Agency"}, "issuer_not_near_quote"),
    ],
)
def test_each_gold_fact_must_be_supported_by_the_stored_text(stored, over, code):
    conn, _ = stored
    assert code in codes(check_pack(conn, built(items=[fact(**over)])))


@pytest.mark.parametrize(
    ("value", "quote", "found"),
    [
        (3.0, "the CPI was 3.0% higher", True),
        (3.0, "the CPI was 3% higher", True),
        (3.0, "the CPI was 3.25% higher", False),
        (2.5, "rose 2.50 percent", True),
        (6.0, "over $6 billion", True),
        (6175.2, "a deficit of 6,175.2", True),
    ],
)
def test_a_value_matches_however_the_document_writes_it(value, quote, found):
    assert _has_number(value, quote) is found


def test_an_issuer_may_be_named_just_after_the_quote_as_a_source_line(stored):
    conn, _ = stored
    item = fact(
        quote="Annual inflation was 2.9% in the September quarter", named_as="Synthetic Statistics"
    )
    assert codes(check_pack(conn, built(items=[item]))) == []


def test_a_probe_of_an_item_with_no_stated_period_does_not_invent_one(stored):
    conn, _ = stored
    item = forecast(period_as_stated=None, period_resolved=None)
    mutations = {r.mutation for r in probe_pack(conn, built(items=[item])).results}
    assert "added_year" not in mutations and "wrong_period" not in mutations


def test_an_issuer_may_be_named_before_the_quote_on_the_same_page(stored):
    conn, _ = stored
    item = fact(id="expect", quote="expects inflation of 3.4% in the December quarter", value=3.4,
                period_as_stated="December quarter", period_resolved="2026Q4", named_as="Synthetic Bank")  # fmt: skip
    assert codes(check_pack(conn, built(items=[item]))) == []


@pytest.mark.parametrize(
    ("over", "code"),
    [
        ({"phrase": "next Thursday"}, "phrase_not_in_quote"),
        ({"resolved": "2026-11-03"}, "weekday_mismatch"),  # a Tuesday
        (
            {"resolved": "2026-10-28"},
            "relative_date_not_after_document",
        ),  # a Wednesday, before the document
        ({"resolved": "2027-02-03"}, "relative_date_too_far"),  # a Wednesday, months away
        ({"calendar_quote": "9 Nov Labour data"}, "calendar_quote_not_found"),
    ],
)
def test_relative_dates_resolve_from_the_document_date_not_the_publication_date(stored, over, code):
    conn, _ = stored
    assert code in codes(check_pack(conn, built(relative_dates=[relative(**over)])))


def test_friday_before_publication_is_valid_because_the_anchor_is_the_document_date(stored):
    conn, _ = stored
    item = relative(id="survey", quote="the survey follows on Friday", phrase="on Friday", resolved="2026-10-30",
                    calendar_quote="30 Oct Survey")  # fmt: skip
    assert codes(check_pack(conn, built(relative_dates=[item]))) == []


def test_the_foreign_quote_must_really_be_absent_from_this_document(stored):
    conn, _ = stored
    assert "foreign_quote_present" in codes(check_pack(conn, built(foreign_quote=PAGE_2[:60])))


def test_probes_keep_a_true_claim_and_report_each_corruption(stored):
    conn, _ = stored
    report = probe_pack(conn, built(items=[forecast()], relative_dates=[]))
    (baseline,) = [r for r in report.results if r.mutation == "baseline"]
    assert baseline.expected == "accepted" and baseline.caught is False
    by_name = {r.mutation: r for r in report.results}
    assert by_name["wrong_value"].caught is True
    assert by_name["foreign_evidence"].caught is True
    assert all(r.expected == "rejected" for r in report.results if r.mutation != "baseline")


def test_a_corruption_the_verifier_misses_is_reported_as_missed_not_dropped(stored):
    conn, _ = stored
    report = probe_pack(conn, built(items=[fact()], relative_dates=[]))
    assert report.caught + report.missed == sum(r.mutation != "baseline" for r in report.results)
    assert {r.mutation for r in report.results} >= {"baseline", "wrong_value", "wrong_period", "added_year",
                                                    "wrong_page", "foreign_evidence"}  # fmt: skip


def test_a_decision_probe_catches_a_changed_rate_and_vote(stored):
    conn, _ = stored
    report = probe_pack(conn, built(items=[decision()], relative_dates=[]))
    by_name = {r.mutation: r for r in report.results}
    assert by_name["baseline"].caught is False
    assert by_name["wrong_rate"].caught is True and by_name["wrong_vote"].caught is True


def test_a_colon_vote_is_measured_as_a_false_rejection_rather_than_hidden(conn):
    text = (
        "The Synthetic Bank's committee voted 5:2 to hold the OCR at 3.25% on 28 October 2026. " * 2
    )
    seed_version(conn, (text, PAGE_2, PAGE_3), published_on="2026-11-02")
    with transaction(conn):
        conn.execute("UPDATE research_publication SET title = 'Synthetic Update - 29 October 2026'")
    digest = hashlib.sha256("\n".join((text, PAGE_2, PAGE_3)).encode()).hexdigest()
    item = decision(
        quote="Synthetic Bank's committee voted 5:2 to hold the OCR at 3.25% on 28 October 2026"
    )
    report = probe_pack(
        conn, built(text_sha256=digest, content_sha256=digest, items=[item], relative_dates=[])
    )
    assert report.false_rejections == 1
    (baseline,) = [r for r in report.results if r.mutation == "baseline"]
    assert baseline.codes == ("vote_not_in_evidence",)


def test_a_corruption_is_not_credited_when_the_true_claim_was_already_rejected(stored):
    conn, _ = stored
    report = probe_pack(conn, built(items=[forecast(unit="not_a_unit")], relative_dates=[]))
    assert report.false_rejections == 1
    assert report.caught == 0 and report.missed == 0
    assert report.not_measured == sum(r.mutation != "baseline" for r in report.results)


def test_a_view_is_probed_as_a_statement_not_as_a_reported_figure(stored):
    conn, _ = stored
    view = {"id": "view", "kind": "view", "issuer": "The Author", "issuer_role": "author", "named_as": "We forecast",
            "page": 2, "quote": "We forecast unemployment of 5.1% in the December quarter",
            "text": "The author forecasts unemployment."}  # fmt: skip
    report = probe_pack(conn, built(items=[view], relative_dates=[]))
    by_name = {r.mutation: r for r in report.results}
    assert set(by_name) == {"baseline", "wrong_page", "foreign_evidence"}
    assert by_name["baseline"].caught is False and by_name["foreign_evidence"].caught is True


@pytest.mark.parametrize("missing", ["action", "value", "decided_on"])
def test_a_decision_item_must_be_complete(missing):
    item = decision()
    del item[missing]
    with pytest.raises(ValueError):
        built(items=[item])


def test_load_pack_refuses_a_malformed_file_with_a_fixed_message(tmp_path):
    path = tmp_path / "pack.json"
    path.write_text('{"annotator": "SECRET TEXT"}')
    with pytest.raises(GoldPackError) as err:
        load_pack(path)
    assert "SECRET TEXT" not in str(err.value)


def test_a_pack_with_an_unknown_field_is_refused(tmp_path):
    path = tmp_path / "pack.json"
    path.write_text('{"unexpected": 1}')
    with pytest.raises(GoldPackError):
        load_pack(path)
