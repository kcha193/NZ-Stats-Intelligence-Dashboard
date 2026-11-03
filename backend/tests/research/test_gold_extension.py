"""Human-reviewed gold extension and scoring with honest denominators (SYNTHETIC FIXTURE: invented text and figures)."""

import hashlib
import json
import sqlite3

import pytest

from nzstats.research.contract import OutlookSummary
from nzstats.research.gold_extension import (
    ExtensionItem,
    GoldExtension,
    GoldExtensionError,
    _Emitted,
    _score,
    load_extension,
    score_extension,
    write_worksheet,
)
from nzstats.research.verify import VerificationContext
from nzstats.store.db import transaction

from .llm_support import seed_version
from .verify_support import PROV

PAGE = (
    "Output rose 6.3% in the September quarter. The IMF expects growth of 2.9% in 2027. "
    "We forecast unemployment of 5.1% in the December quarter. The trend was 40 at some point."
)
DIGEST = hashlib.sha256(PAGE.encode()).hexdigest()


def gold(id="output", category="accepted_eligible", kind="fact", terms=("output",), value=6.3, period="September quarter",
         role=None, issuer=None, reason=None):  # fmt: skip
    return {"id": id, "category": category, "kind": kind, "terms": list(terms), "value": value, "unit": "percent",
            "period_as_stated": period, "issuer_role": role, "issuer": issuer, "expected_reason": reason}  # fmt: skip


def extension(version=1, **over):
    return {"annotator": "Test Person", "reviewed_by": "Test Reviewer", "reviewed_on": "2026-11-03",
            "written_without_model_output": True, "version_id": version, "text_sha256": DIGEST,
            "items": [gold(),
                      gold("imf", "third_party_forecast", "forecast", ("growth",), 2.9, "2027", "third_party", "IMF"),
                      gold("own", "accepted_eligible", "forecast", ("unemployment",), 5.1, "December quarter", "author", "Treasury"),
                      gold("cell", "expected_rejection", "fact", ("trend",), 40, None, reason="no_period"),
                      gold("unclear", "ambiguous", "fact", ("vague",), 7.0, None)],
            **over}  # fmt: skip


def fact(
    value=6.3,
    period="September quarter",
    text="Output rose.",
    quote="Output rose 6.3% in the September quarter",
):
    return {"text": text, "source": "Synthetic Statistics", "value": value, "unit": "percent", "period": period,
            "evidence": [{"version_id": 1, "section_ordinal": 0, "page": 1, "quote": quote}]}  # fmt: skip


def fc(value, horizon, issuer, role, label, quote, indicator="gdp"):
    return {"indicator": indicator, "indicator_label": label, "horizon": horizon, "value": value, "unit": "percent",
            "direction": "up", "issuer": issuer, "issuer_role": role,
            "evidence": [{"version_id": 1, "section_ordinal": 0, "page": 1, "quote": quote}]}  # fmt: skip


IMF = fc(2.9, "2027", "IMF", "third_party", "growth", "The IMF expects growth of 2.9% in 2027")
OWN = fc(5.1, "December quarter", "The Treasury", "author", "unemployment",
         "We forecast unemployment of 5.1% in the December quarter", "unemployment")  # fmt: skip


def summary(facts=(), forecasts=()):
    outlook = {
        "text": "Probe.",
        "evidence": [
            {"version_id": 1, "section_ordinal": 0, "page": 1, "quote": "Output rose 6.3%"}
        ],
    }
    return OutlookSummary(version_id=1, contract_version=2, provenance=PROV, outlook=outlook, facts=list(facts),
                          forecasts=list(forecasts), indicators=["gdp", "unemployment"])  # fmt: skip


@pytest.fixture()
def stored(conn):
    version = seed_version(conn, (PAGE,), published_on="2026-11-02")
    return conn, version


def scored(conn, s, **over):
    ext = GoldExtension.model_validate(extension(**over))
    ctx = VerificationContext(published_on=None, institution="treasury")
    return score_extension(conn, s, ext, ctx)


def test_an_extension_must_be_reviewed_by_a_person_and_written_blind(tmp_path):
    for change in (
        {"reviewed_by": ""},
        {"written_without_model_output": False},
        {"reviewed_on": None},
    ):
        with pytest.raises(ValueError):
            GoldExtension.model_validate(extension(**change))


def test_an_empty_extension_is_refused():
    with pytest.raises(ValueError):
        GoldExtension.model_validate(extension(items=[]))


def test_an_extension_for_another_document_is_refused(stored):
    conn, _ = stored
    with pytest.raises(GoldExtensionError):
        scored(conn, summary([fact()]), text_sha256="a" * 64)


def test_an_expected_rejection_must_say_why():
    with pytest.raises(ValueError):
        GoldExtension.model_validate(
            extension(items=[gold("x", "expected_rejection", reason=None)])
        )


def test_load_refuses_a_malformed_file_without_repeating_it(tmp_path):
    path = tmp_path / "x.json"
    path.write_text('{"annotator": "SECRET"}')
    with pytest.raises(GoldExtensionError) as err:
        load_extension(path)
    assert "SECRET" not in str(err.value)


def test_nothing_emitted_is_unmeasured_never_a_pass(stored):
    conn, _ = stored
    report = scored(conn, summary())
    view = report.views["accepted"]
    assert (view.precision.numerator, view.precision.denominator) == (
        0,
        0,
    ) and view.precision.text == "unmeasured (0/0)"
    assert view.numerical_accuracy.text == "unmeasured (0/0)"
    assert view.recall.text == "0/3"


def test_a_whole_failed_summary_has_an_empty_accepted_view_but_keeps_raw_counts(stored):
    conn, _ = stored
    bad = fact(value=6.3, period="September quarter 2026")
    report = scored(conn, summary([bad], [IMF, OWN]))
    assert report.passed is False
    assert report.views["accepted"].claims == 0 and report.views["accepted"].recall.text == "0/3"
    assert report.views["raw"].claims == 3 and report.views["raw"].recall.text == "3/3"


def test_the_clean_view_is_a_labelled_hypothetical_and_excludes_failed_claims(stored):
    conn, _ = stored
    report = scored(conn, summary([fact(period="September quarter 2026")], [IMF, OWN]))
    clean = report.views["clean_claims_hypothetical"]
    assert clean.claims == 2 and clean.recall.text == "2/3"
    assert "hypothetical" in report.to_json()["views"]["clean_claims_hypothetical"]["label"]


def test_a_passing_summary_scores_precision_recall_and_numbers_on_real_denominators(stored):
    conn, _ = stored
    report = scored(conn, summary([fact()], [IMF, OWN]))
    assert report.passed is True
    view = report.views["accepted"]
    assert (
        view.precision.text == "3/3"
        and view.recall.text == "3/3"
        and view.numerical_accuracy.text == "3/3"
    )
    assert view.issuer_accuracy.text == "2/2" and view.period_exact.text == "3/3"


def test_a_wrong_number_on_the_right_claim_is_a_numerical_error_not_a_miss_of_the_key(stored):
    conn, _ = stored
    report = scored(
        conn, summary([fact(value=9.9, quote="Output rose 6.3% in the September quarter")])
    )
    raw = report.views["raw"]
    assert (
        raw.numerical_accuracy.text == "0/1"
        and raw.recall.text == "0/3"
        and raw.precision.text == "0/1"
    )


def test_an_added_year_counts_against_period_exactness_but_still_matches_the_claim(stored):
    conn, _ = stored
    raw = scored(conn, summary([fact(period="September quarter 2026")])).views["raw"]
    assert raw.recall.text == "1/3" and raw.period_exact.text == "0/1"


def test_a_third_party_forecast_labelled_as_the_author_fails_issuer_accuracy(stored):
    conn, _ = stored
    wrong = {**IMF, "issuer": "The Treasury", "issuer_role": "author"}
    raw = scored(conn, summary([], [wrong])).views["raw"]
    assert raw.issuer_accuracy.text == "0/1"


def test_a_claim_outside_the_gold_lowers_precision_and_is_counted_as_unmatched(stored):
    conn, _ = stored
    raw = scored(conn, summary([fact(), fact(value=2.0, text="Something else.")])).views["raw"]
    assert raw.precision.text == "1/2" and raw.unmatched == 1


def test_an_ambiguous_gold_item_is_outside_every_denominator(stored):
    conn, _ = stored
    report = scored(conn, summary([fact(value=7.0, text="Vague thing.", period=None)]))
    raw = report.views["raw"]
    assert raw.ambiguous == 1 and raw.precision.denominator == 0 and raw.recall.denominator == 3


def test_an_expected_rejection_that_was_accepted_is_reported(stored):
    conn, _ = stored
    report = scored(
        conn,
        summary(
            [fact(value=40, text="The trend.", period=None, quote="The trend was 40 at some point")]
        ),
    )
    assert report.expected_rejections_emitted == 1


def test_the_score_never_contains_document_or_model_text(stored):
    conn, _ = stored
    body = json.dumps(scored(conn, summary([fact()], [IMF, OWN])).to_json())
    for text in ("Output rose", "The IMF expects", "Synthetic Statistics", "September quarter"):
        assert text not in body


def _deny_model_output(action, table, column, *_):
    if action == sqlite3.SQLITE_READ and table in {
        "research_summary",
        "research_llm_run",
        "research_llm_usage",
        "research_forecast_claim",
    }:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def test_the_worksheet_is_built_from_the_document_and_cannot_read_model_output(stored, tmp_path):
    conn, version = stored
    conn.set_authorizer(_deny_model_output)
    out = tmp_path / "sheet.html"
    count = write_worksheet(conn, version, out)
    conn.set_authorizer(None)
    html = out.read_text()
    assert count == 4  # the sentences with a number or a forecast word
    assert (
        "accepted_eligible" in html
        and "third_party_forecast" in html
        and "Written without seeing model output" in html
    )
    assert "The IMF expects growth of 2.9% in 2027" in html


def test_the_worksheet_escapes_document_text(conn, tmp_path):
    version = seed_version(
        conn,
        ("Output of 6.3% <script>alert(1)</script> was recorded in 2026.",),
        published_on="2026-11-02",
    )
    out = tmp_path / "sheet.html"
    write_worksheet(conn, version, out)
    assert "<script>" not in out.read_text() and "&lt;script&gt;" in out.read_text()


def test_the_worksheet_refuses_an_unknown_version(conn, tmp_path):
    with pytest.raises(GoldExtensionError):
        write_worksheet(conn, 99, tmp_path / "x.html")


def test_the_worksheet_refuses_a_superseded_version(stored, tmp_path):
    conn, version = stored
    with transaction(conn):
        conn.execute("UPDATE research_document_version SET superseded_at = '2026-11-02T00:00:00Z'")
    with pytest.raises(GoldExtensionError):
        write_worksheet(conn, version, tmp_path / "x.html")


def test_the_worksheet_refuses_a_purged_version(stored, tmp_path):
    conn, version = stored
    with transaction(conn):
        purge_id = conn.execute(
            "INSERT INTO research_purge(institution_id, reason, scope, purged_by, note, versions, sections,"
            " summaries, claims, withdrawn, artifacts, purged_at)"
            " SELECT id, 'other', '{}', 'x', 'x', 1, 0, 0, 0, 0, 0, '2026-11-02T00:00:00Z' FROM research_institution"
        ).lastrowid
        conn.execute(
            "UPDATE research_document_version SET purged_at = '2026-11-02T00:00:00Z', purge_id = ?",
            (purge_id,),
        )
    with pytest.raises(GoldExtensionError):
        write_worksheet(conn, version, tmp_path / "x.html")


def test_the_worksheet_is_private_from_the_moment_it_exists(stored, tmp_path):
    conn, version = stored
    out = tmp_path / "sheet.html"
    write_worksheet(conn, version, out)
    assert out.stat().st_mode & 0o777 == 0o600
    out.chmod(0o644)
    write_worksheet(conn, version, out)
    assert out.stat().st_mode & 0o777 == 0o600


# Found by independent review.
@pytest.mark.parametrize(
    "change",
    [
        {"reviewed_by": "   "},
        {"annotator": "   "},
        {"reviewed_on": "2099-01-01"},
        {"reviewed_by": "Claude Code"},
        {"reviewed_by": "codex"},
        {"reviewed_by": "GPT reviewer"},
    ],
)
def test_review_must_be_by_a_named_person_and_already_done(change):
    with pytest.raises(ValueError):
        GoldExtension.model_validate(extension(**change))


def test_blank_terms_and_repeated_ids_are_refused():
    with pytest.raises(ValueError):
        GoldExtension.model_validate(extension(items=[gold(terms=("",))]))
    with pytest.raises(ValueError):
        GoldExtension.model_validate(extension(items=[gold(), gold()]))


def test_a_year_only_period_must_match_its_year(stored):
    conn, _ = stored
    wrong = {**IMF, "horizon": "2031"}
    raw = scored(conn, summary([], [wrong])).views["raw"]
    assert raw.recall.text == "0/3" and raw.unmatched == 1


def test_a_gold_item_with_no_number_does_not_bless_a_claim_with_one(stored):
    conn, _ = stored
    items = [gold("view", kind="fact", terms=("output",), value=None, period="September quarter")]
    raw = scored(conn, summary([fact(value=99)]), items=items).views["raw"]
    assert raw.precision.text == "0/1" and raw.recall.text == "0/1"


def test_repeating_a_claim_does_not_inflate_precision(stored):
    conn, _ = stored
    raw = scored(conn, summary([fact(), fact(), fact()])).views["raw"]
    assert raw.precision.text == "1/3" and raw.duplicates == 2 and raw.recall.text == "1/3"


def test_an_emitted_expected_rejection_counts_against_precision(stored):
    conn, _ = stored
    rejected = fact(
        value=40, text="The trend.", period=None, quote="The trend was 40 at some point"
    )
    raw = scored(conn, summary([fact(), rejected])).views["raw"]
    assert raw.precision.text == "1/2" and raw.expected_rejections == 1


# Found by the second independent review.
def test_a_period_with_a_year_must_match_that_year(stored):
    conn, _ = stored
    item = gold(period="September quarter 2029")
    raw = scored(conn, summary([fact(period="September quarter 2031")]), items=[item]).views["raw"]
    assert raw.unmatched == 1 and raw.recall.text == "0/1"


def test_an_ambiguous_item_cannot_swallow_a_wrong_number(stored):
    conn, _ = stored
    items = [gold("broad", "ambiguous", terms=("output",), value=None, period=None), gold()]
    raw = scored(conn, summary([fact(value=9.9)]), items=items).views["raw"]
    assert (
        raw.precision.text == "0/1" and raw.numerical_accuracy.text == "0/1" and raw.ambiguous == 0
    )


def test_the_wrong_unit_is_not_a_right_number(stored):
    conn, _ = stored
    raw = scored(conn, summary([{**fact(), "unit": "nzd_billion"}]), items=[gold()]).views["raw"]
    assert raw.numerical_accuracy.text == "0/1" and raw.recall.text == "0/1"


def test_a_number_on_an_item_with_none_counts_against_numbers(stored):
    conn, _ = stored
    items = [gold("view", terms=("output",), value=None)]
    raw = scored(conn, summary([fact(value=99)]), items=items).views["raw"]
    assert raw.numerical_accuracy.text == "0/1"


def test_a_third_party_forecast_must_name_its_issuer():
    with pytest.raises(ValueError):
        GoldExtension.model_validate(
            extension(
                items=[
                    gold("x", "third_party_forecast", "forecast", role="third_party", issuer=None)
                ]
            )
        )


def test_the_raw_label_says_what_it_covers(stored):
    conn, _ = stored
    label = scored(conn, summary([fact()])).to_json()["views"]["raw"]["label"]
    assert "facts, forecasts and decisions" in label and "not scored" in label


# Found by the third independent review.
def test_a_tie_with_an_expected_rejection_counts_as_the_rejection(stored):
    conn, _ = stored
    items = [gold("eligible"), gold("rejected", "expected_rejection", reason="no_period")]
    for order in (items, items[::-1]):
        raw = scored(conn, summary([fact()]), items=order).views["raw"]
        assert raw.expected_rejections == 1 and raw.precision.text == "0/1"
        assert raw.recall.text == "0/1"


def test_the_order_of_the_gold_does_not_change_the_score(stored):
    conn, _ = stored
    items = [gold("a"), gold("b", period=None)]
    first = scored(conn, summary([fact()]), items=items).to_json()
    assert first == scored(conn, summary([fact()]), items=items[::-1]).to_json()


def test_a_broad_ambiguous_item_cannot_absorb_a_wrong_number_alone(stored):
    conn, _ = stored
    items = [gold("broad", "ambiguous", value=None, period=None)]
    raw = scored(conn, summary([fact(value=9.9)]), items=items).views["raw"]
    assert raw.ambiguous == 0 and raw.unmatched == 1 and raw.precision.text == "0/1"


def test_an_ambiguous_item_still_takes_a_claim_it_is_right_for(stored):
    conn, _ = stored
    items = [gold("unclear", "ambiguous", period=None)]
    raw = scored(conn, summary([fact()]), items=items).views["raw"]
    assert raw.ambiguous == 1 and raw.precision.text == "unmeasured (0/0)"


def test_a_claim_with_no_unit_is_not_right_for_gold_with_one(stored):
    conn, _ = stored
    raw = scored(conn, summary([{**fact(), "unit": None}]), items=[gold()]).views["raw"]
    assert raw.numerical_accuracy.text == "0/1" and raw.recall.text == "0/1"


def test_a_decision_has_no_unit_field_so_its_rate_alone_decides():
    item = ExtensionItem.model_validate(
        gold("ocr", kind="decision", terms=("hold",), value=9.5, period=None)
    )
    decision = _Emitted("decision", "hold", 9.5, None, None, "Bank", None, False)
    assert _score([decision], (item,)).numerical_accuracy.text == "1/1"


@pytest.mark.parametrize("role", ["author", None])
def test_a_third_party_forecast_must_have_the_third_party_role(role):
    with pytest.raises(ValueError):
        ExtensionItem.model_validate(
            gold("x", "third_party_forecast", "forecast", role=role, issuer="IMF")
        )


def test_repeating_a_right_number_does_not_raise_numerical_accuracy(stored):
    conn, _ = stored
    raw = scored(conn, summary([fact(), fact(), fact(value=9.9)]), items=[gold()]).views["raw"]
    assert raw.numerical_accuracy.text == "1/2" and raw.duplicates == 1


# Found by the fourth review.
def test_being_right_for_an_ambiguous_item_does_not_excuse_a_wrong_number(stored):
    conn, _ = stored
    items = [gold("eligible"), gold("unclear", "ambiguous", value=9.9)]
    raw = scored(conn, summary([fact(value=9.9)]), items=items).views["raw"]
    assert raw.precision.text == "0/1" and raw.ambiguous == 0


def test_the_wrong_issuer_is_not_a_correct_forecast(stored):
    conn, _ = stored
    wrong = fc(
        2.9, "2027", "The Treasury", "author", "growth", "The IMF expects growth of 2.9% in 2027"
    )
    raw = scored(conn, summary(forecasts=[wrong]), items=[extension()["items"][1]]).views["raw"]
    assert raw.precision.text == "0/1" and raw.recall.text == "0/1"
    assert raw.numerical_accuracy.text == "1/1" and raw.issuer_accuracy.text == "0/1"


def test_a_wrong_issuer_then_the_right_one_counts_the_number_once(stored):
    conn, _ = stored
    wrong = fc(
        2.9, "2027", "The Treasury", "author", "growth", "The IMF expects growth of 2.9% in 2027"
    )
    raw = scored(conn, summary(forecasts=[wrong, IMF]), items=[extension()["items"][1]]).views[
        "raw"
    ]
    assert raw.precision.text == "1/2" and raw.recall.text == "1/1"
    assert raw.numerical_accuracy.text == "1/1"


def test_a_third_party_forecast_must_be_a_forecast():
    with pytest.raises(ValueError):
        ExtensionItem.model_validate(
            gold("x", "third_party_forecast", "fact", role="third_party", issuer="IMF")
        )


# Phase 4Q review round: issuer-aware matching, the decision date and qualitative direction.
TREASURY_PAGE = "We forecast growth of 2.9% in 2027. The IMF expects growth of 2.9% in 2027."
TWO_ISSUERS = [
    gold("a-imf", "third_party_forecast", "forecast", ("growth",), 2.9, "2027", "third_party", "IMF"),
    gold("b-own", "accepted_eligible", "forecast", ("growth",), 2.9, "2027", "author", "The Treasury"),
]  # fmt: skip
OWN_GROWTH = fc(
    2.9, "2027", "The Treasury", "author", "growth", "We forecast growth of 2.9% in 2027"
)
IMF_GROWTH = fc(
    2.9, "2027", "IMF", "third_party", "growth", "The IMF expects growth of 2.9% in 2027"
)


@pytest.mark.parametrize("flip", [False, True])
@pytest.mark.parametrize("claims", [(OWN_GROWTH, IMF_GROWTH), (IMF_GROWTH, OWN_GROWTH)])
def test_equal_forecasts_by_different_issuers_each_match_their_own_gold_in_any_order(
    stored, claims, flip
):
    conn, _ = stored
    items = TWO_ISSUERS[::-1] if flip else TWO_ISSUERS
    raw = scored(conn, summary([], claims), items=items).views["raw"]
    assert raw.precision.text == "2/2" and raw.recall.text == "2/2"
    assert raw.issuer_accuracy.text == "2/2" and raw.duplicates == 0


def test_a_repeated_forecast_cannot_cover_the_other_issuers_gold(stored):
    conn, _ = stored
    raw = scored(conn, summary([], [OWN_GROWTH, OWN_GROWTH]), items=TWO_ISSUERS).views["raw"]
    assert raw.recall.text == "1/2" and raw.duplicates == 1 and raw.precision.text == "1/2"


def test_a_forecast_with_the_wrong_issuer_for_every_gold_item_earns_no_credit(stored):
    conn, _ = stored
    wrong = {**IMF_GROWTH, "issuer": "OECD"}
    raw = scored(conn, summary([], [wrong]), items=TWO_ISSUERS).views["raw"]
    assert raw.recall.text == "0/2" and raw.issuer_accuracy.text == "0/1"


def hold(decided_on="2026-11-03", action="hold", rate=2.75):
    return {"instrument": "ocr", "action": action, "rate": rate, "decided_on": decided_on,
            "decision_maker": "Monetary Policy Committee",
            "evidence": [{"version_id": 1, "section_ordinal": 0, "page": 1, "quote": "Output rose 6.3% in the September"}]}  # fmt: skip


def decision_gold(period="2026-11-03"):
    return gold("hold", kind="decision", terms=("hold",), value=2.75, period=period)


def with_decisions(*decisions):
    s = summary()
    return OutlookSummary.model_validate(
        {**s.model_dump(mode="json"), "decisions": list(decisions)}
    )


@pytest.mark.parametrize("period", ["2026-11-03", "3 November 2026", "3 Nov 2026"])
def test_a_decision_with_the_gold_date_earns_credit_however_the_gold_writes_it(stored, period):
    conn, _ = stored
    raw = scored(conn, with_decisions(hold()), items=[decision_gold(period)]).views["raw"]
    assert (
        raw.precision.text == "1/1" and raw.recall.text == "1/1" and raw.period_exact.text == "1/1"
    )


def test_a_decision_with_another_date_is_not_the_gold_decision(stored):
    conn, _ = stored
    raw = scored(conn, with_decisions(hold("2026-10-28")), items=[decision_gold()]).views["raw"]
    assert raw.recall.text == "0/1" and raw.unmatched == 1


def test_a_decision_gold_must_state_a_date_it_can_be_compared_on():
    with pytest.raises(ValueError):
        GoldExtension.model_validate(extension(items=[decision_gold("October")]))


def qualitative(direction, label="growth"):
    return {**fc(None, "2027", "The Treasury", "author", label, "We forecast growth of 2.9% in 2027"),
            "direction": direction, "unit": None}  # fmt: skip


def qualitative_gold(direction="up"):
    return {**gold("dir", "accepted_eligible", "forecast", ("growth",), None, "2027", "author", "The Treasury"),
            "unit": None, "direction": direction}  # fmt: skip


def test_a_reversed_qualitative_forecast_earns_no_credit(stored):
    conn, _ = stored
    raw = scored(conn, summary([], [qualitative("down")]), items=[qualitative_gold("up")]).views[
        "raw"
    ]
    assert raw.recall.text == "0/1" and raw.precision.text == "0/1"


@pytest.mark.parametrize("direction", ["up", "down", "flat", "unclear"])
def test_only_the_gold_direction_earns_credit(stored, direction):
    conn, _ = stored
    raw = scored(conn, summary([], [qualitative("up")]), items=[qualitative_gold(direction)]).views[
        "raw"
    ]
    assert raw.recall.text == ("1/1" if direction == "up" else "0/1")


def test_a_qualitative_forecast_gold_must_state_its_direction():
    with pytest.raises(ValueError):
        GoldExtension.model_validate(extension(items=[{**qualitative_gold(), "direction": None}]))
