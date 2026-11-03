"""Version-bound gold packs and offline verifier probes (SYNTHETIC FIXTURE: invented text, invented issuers)."""

import hashlib
from datetime import date

import pytest
from pydantic import ValidationError

from nzstats.research.contract import IssuerRole
from nzstats.research.gold_check import (
    AccuracyPack,
    GoldPackError,
    _has_number,
    _mutations,
    _period_conflict,
    _relative_candidates,
    _unsupported_year,
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
        (
            2.9,
            "Annual growth was -2.9%",
            False,
        ),  # a positive gold value must not match the unsigned tail of a negative
        (-2.9, "Annual growth was -2.9%", True),
        (-2.9, "Annual growth was 2.9%", False),
        (-2.9, "Annual growth was \u22122.9%", True),  # a typographic minus is still a minus
        (2.9, "Annual growth was \u22122.9%", False),
        (-2.9, "Annual growth was (2.9)%", False),
        (3.5, "growth of 3.0-3.5% a year", True),  # a range hyphen is not a sign
        (3.0, "growth of 3.0-3.5% a year", True),
        (-3.5, "growth of 3.0-3.5% a year", False),
        (0.0, "unchanged at 0.0%", True),
        (0.0, "unchanged at 0%", True),
        (0.0, "unchanged at 10.0%", False),
        (0.0, "unchanged at -0.5%", False),
        (-0.5, "unchanged at -0.5%", True),
        (0.5, "unchanged at -0.5%", False),
        (-3.0, "fell -3% on the year", True),
    ],
)
def test_a_value_matches_however_the_document_writes_it(value, quote, found):
    assert _has_number(value, quote) is found


@pytest.mark.parametrize(
    ("stated", "resolved", "conflict"),
    [
        ("September quarter 2025", "2024Q3", True),  # the year is stated and differs
        ("September quarter 2025", "2025Q3", False),
        ("September quarter 2025", "2025Q4", True),  # the quarter differs
        ("September quarter", "2024Q3", False),  # no year stated: none is invented
        ("September quarter", "2026Q3", False),
        ("the September 2025 quarter", "2026Q3", True),
        ("2025Q3", "2024Q3", True),
        ("2025Q3", "2025Q3", False),
        ("December quarter 2026", "2026Q4", False),
        (
            "year to September 2025",
            "2024Q3",
            False,
        ),  # not a quarter name, so not this check's business
    ],
)
def test_a_stated_year_must_agree_with_the_resolved_period(stated, resolved, conflict):
    assert _period_conflict(stated, resolved) is conflict


def seed_dated(conn, page_1):
    seed_version(conn, (page_1, PAGE_2, PAGE_3), published_on="2026-11-02")
    with transaction(conn):
        conn.execute("UPDATE research_publication SET title = 'Synthetic Update - 29 October 2026'")
    digest = hashlib.sha256("\n".join((page_1, PAGE_2, PAGE_3)).encode()).hexdigest()
    return {"text_sha256": digest, "content_sha256": digest}


def test_a_stated_year_that_contradicts_the_resolved_quarter_is_reported(conn):
    page = "Annual inflation was 2.9% in the September quarter 2025, Synthetic Statistics reported."
    hashes = seed_dated(conn, page)
    quote = "Annual inflation was 2.9% in the September quarter 2025, Synthetic Statistics reported"
    stated = "September quarter 2025"
    wrong = fact(quote=quote, period_as_stated=stated, period_resolved="2024Q3")
    right = fact(quote=quote, period_as_stated=stated, period_resolved="2025Q3")
    assert "period_resolved_mismatch" in codes(
        check_pack(conn, built(**hashes, items=[wrong], relative_dates=[]))
    )
    assert codes(check_pack(conn, built(**hashes, items=[right], relative_dates=[]))) == []


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


@pytest.mark.parametrize(
    ("phrase", "document", "expected"),
    [
        (
            "next Wednesday",
            date(2026, 10, 29),
            {date(2026, 11, 4)},
        ),  # Thursday: the coming Wednesday is next week's
        ("on Friday", date(2026, 10, 29), {date(2026, 10, 30)}),
        ("this Friday", date(2026, 10, 29), {date(2026, 10, 30)}),
        (
            "Thursday",
            date(2026, 10, 29),
            {date(2026, 11, 5)},
        ),  # the same weekday is a week on, never the document day
        (
            "next Wednesday",
            date(2026, 10, 26),
            {date(2026, 10, 28), date(2026, 11, 4)},
        ),  # Monday: both usages exist
        ("next Monday", date(2026, 11, 1), {date(2026, 11, 2)}),  # Sunday
        ("next week", date(2026, 10, 29), None),  # no weekday named, so nothing to resolve
        ("early next month", date(2026, 10, 29), None),
    ],
)
def test_a_relative_weekday_resolves_from_the_document_date(phrase, document, expected):
    assert _relative_candidates(phrase, document) == expected


def test_the_right_weekday_a_week_late_is_not_certified_by_the_window(stored):
    conn, _ = stored
    late = relative(
        resolved="2026-11-11"
    )  # a Wednesday within 14 days, but not the one 'next Wednesday' means
    assert "relative_date_mismatch" in codes(check_pack(conn, built(relative_dates=[late])))


def test_the_calendar_line_must_name_the_resolved_date(stored):
    conn, _ = stored
    wrong_line = relative(resolved="2026-11-11", calendar_quote="4 Nov Labour data")
    assert "calendar_date_mismatch" in codes(check_pack(conn, built(relative_dates=[wrong_line])))
    assert "calendar_date_mismatch" not in codes(
        check_pack(conn, built(relative_dates=[relative()]))
    )


def test_a_calendar_line_with_no_date_cannot_corroborate(conn):
    page_3 = "Coming up: Labour data. 30 Oct Survey."
    seed_version(conn, (PAGE_1, PAGE_2, page_3), published_on="2026-11-02")
    with transaction(conn):
        conn.execute("UPDATE research_publication SET title = 'Synthetic Update - 29 October 2026'")
    digest = hashlib.sha256("\n".join((PAGE_1, PAGE_2, page_3)).encode()).hexdigest()
    item = relative(calendar_quote="Labour data")
    report = check_pack(
        conn,
        built(text_sha256=digest, content_sha256=digest, items=[fact()], relative_dates=[item]),
    )
    assert "calendar_quote_has_no_date" in codes(report)


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


@pytest.mark.parametrize(
    ("key", "name"),
    [("rbnz", "Reserve Bank of New Zealand"), ("treasury", "The Treasury (New Zealand)")],
)
def test_a_third_party_forecast_is_relabelled_as_the_documents_actual_author(key, name):
    item = AccuracyPack.model_validate(
        pack(items=[forecast(issuer_role="third_party", issuer="Synthetic Statistics")])
    ).items[0]
    wrong = _mutations(item, "", key, name)["wrong_issuer"]
    assert wrong == {"issuer": name, "issuer_role": IssuerRole.AUTHOR}


@pytest.mark.parametrize("key", ["imf", "rba", "treasury"])
def test_an_author_forecast_is_relabelled_as_a_third_party_that_is_not_the_author(key):
    from nzstats.research.issuers import organisation_of

    item = AccuracyPack.model_validate(pack(items=[forecast()])).items[0]
    wrong = _mutations(item, "", key, "Whoever")["wrong_issuer"]
    assert wrong["issuer_role"] is IssuerRole.THIRD_PARTY
    assert organisation_of(wrong["issuer"]) not in (None, key)


def test_the_issuer_probe_is_skipped_when_the_author_has_no_name_the_verifier_knows():
    item = AccuracyPack.model_validate(
        pack(items=[forecast(issuer_role="third_party", issuer="Synthetic Statistics")])
    ).items[0]
    assert "wrong_issuer" not in _mutations(item, "", "example", "Example Institute")


def test_a_decision_with_no_recorded_vote_is_probed_without_a_vote_mutation(stored):
    conn, _ = stored
    item = decision(vote_for=None, vote_against=None)
    report = probe_pack(conn, built(items=[item], relative_dates=[]))  # must not raise
    mutations = {r.mutation for r in report.results}
    assert "wrong_vote" not in mutations and {"wrong_rate", "wrong_date"} <= mutations


@pytest.mark.parametrize("missing", ["action", "decided_on", "value"])
def test_a_decision_must_state_what_was_decided(missing):
    with pytest.raises(ValidationError):
        built(items=[decision(**{missing: None})])


def test_an_item_the_claim_contract_cannot_hold_is_refused_not_a_crash(stored):
    conn, _ = stored
    too_long = built(
        items=[forecast(text="x" * 201)]
    )  # the pack accepts it; ForecastClaim.indicator_label does not
    with pytest.raises(GoldPackError):
        check_pack(conn, too_long)
    with pytest.raises(GoldPackError):
        probe_pack(conn, too_long)


def test_a_pack_cannot_record_only_half_a_vote():
    with pytest.raises(ValidationError):
        built(items=[decision(vote_against=None)])


def test_a_period_already_at_the_wrong_period_is_not_probed_by_setting_it_again(conn):
    page = "Annual inflation was 2.9% in March 2031, Synthetic Statistics reported."
    hashes = seed_dated(conn, page)
    item = fact(quote=page.rstrip("."), period_as_stated="March 2031", period_resolved=None)
    report = probe_pack(conn, built(**hashes, items=[item], relative_dates=[]))
    wrong = [r for r in report.results if r.mutation == "wrong_period"]
    assert (
        wrong and wrong[0].codes != ()
    )  # a different, unsupported period, so the verifier does reject it
    assert report.missed == 0


def test_a_mutation_that_leaves_the_claim_unchanged_is_not_scored(stored):
    conn, _ = stored
    item = decision(decided_on="2031-03-03")  # the wrong_date probe would set exactly this
    report = probe_pack(conn, built(items=[item], relative_dates=[]))
    assert "wrong_date" not in {r.mutation for r in report.results}


def test_a_year_already_stated_is_not_probed_by_adding_it_again(conn):
    page = "Annual inflation was 2.9% in the September quarter 2025, Synthetic Statistics reported."
    hashes = seed_dated(conn, page)
    item = fact(
        quote=page.rstrip("."), period_as_stated="September quarter 2025", period_resolved="2025Q3"
    )
    report = probe_pack(conn, built(**hashes, items=[item], relative_dates=[]))
    assert "added_year" not in {r.mutation for r in report.results}
    assert report.false_rejections == 0 and {"wrong_period", "wrong_value"} <= {
        r.mutation for r in report.results
    }


def test_the_year_an_unstated_period_gains_is_one_the_document_never_states(conn):
    page = "Annual inflation was 2.9% in the September quarter, Synthetic Statistics reported. Prices in 2025 and 2024 differed."
    hashes = seed_dated(conn, page)
    item = fact(
        quote="Annual inflation was 2.9% in the September quarter, Synthetic Statistics reported"
    )
    report = probe_pack(conn, built(**hashes, items=[item], relative_dates=[]))
    (added,) = [r for r in report.results if r.mutation == "added_year"]
    assert added.measured and added.expected == "rejected"
    assert _unsupported_year(page + PAGE_2 + PAGE_3) not in {"2025", "2024", "2026"}


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
