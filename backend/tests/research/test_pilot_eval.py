"""Phase 3D-A: real-model evaluation of stored summaries against a human annotation file.

Everything here is SYNTHETIC FIXTURE data standing in for a real document; the point is the arithmetic and the
separation from the synthetic replay baseline, which these tests pin with independently counted expectations.
"""

from __future__ import annotations

import json

import pytest

from nzstats.research import summary_store as ss
from nzstats.research.pilot_eval import AnnotationError, evaluate_stored, load_annotations
from nzstats.store.db import transaction

from .llm_support import NOW, draft, seed_version
from .public_support import store_summary

GOLD = {
    "indicators": ["gdp", "cpi_inflation"],
    "forecasts": [
        {"indicator": "gdp", "horizon": "year to March 2027", "value": 2.5, "unit": "percent"},
        {
            "indicator": "cpi_inflation",
            "horizon": "year to June 2027",
            "value": 2.1,
            "unit": "percent",
        },
    ],
    "key_points": [["growth"], ["inflation", "ease"]],
}


def annotations(tmp_path, *docs):
    path = tmp_path / "annotations.json"
    path.write_text(
        json.dumps(
            {"annotator": "Test Annotator", "annotated_on": "2026-10-28", "documents": list(docs)}
        )
    )
    return load_annotations(path)


def usage(conn, summary_id, version_id, *, cost, latency, tokens=(1000, 200)):
    with transaction(conn):
        run = conn.execute(
            "SELECT run_id FROM research_summary WHERE id = ?", (summary_id,)
        ).fetchone()[0]
        ss.record_usage(conn, run_id=run, version_id=version_id, summary_id=summary_id, call_no=1, provider="fake",
                        model="fake-1", input_tokens=tokens[0], output_tokens=tokens[1], usage_estimated=False,
                        latency_ms=latency, cost_usd=cost, outcome="ok", error_class=None, now=NOW)  # fmt: skip


def test_a_faithful_summary_scores_full_marks_with_recorded_cost_and_latency(conn, tmp_path):
    version = seed_version(conn)
    sid = store_summary(conn, version, review=None, publish=False)
    usage(conn, sid, version, cost=0.0123, latency=850)
    report = evaluate_stored(conn, annotations(tmp_path, {"version_id": version, **GOLD}))
    (group,) = report.groups
    m = group.report.metrics
    assert (group.provider, group.model) == ("fake", "fake-1")
    assert group.documents == 1 and group.provider_errors == 0
    assert m["raw_precision"] == 1.0 and m["raw_recall"] == 1.0
    assert m["numerical_fidelity"] == 1.0 and m["citation_correctness"] == 1.0
    assert m["verified_rate"] == 1.0 and m["unsupported_item_rate"] == 0.0
    assert m["indicator_f1"] == 1.0
    assert m["completeness"] == 1.0  # "growth" and "inflation ... ease" are both in the outlook
    assert group.recorded_cost_usd == pytest.approx(0.0123)
    assert m["mean_latency_ms"] == 850


def test_a_wrong_number_is_unsupported_and_lowers_fidelity_and_accepted_recall(conn, tmp_path):
    version = seed_version(conn)
    bad = draft(version)
    bad["forecasts"][0]["value"] = 2.4  # the document says 2.5
    sid = store_summary(conn, version, output=bad, review=None, publish=False)
    usage(conn, sid, version, cost=0.01, latency=1000)
    m = (
        evaluate_stored(conn, annotations(tmp_path, {"version_id": version, **GOLD}))
        .groups[0]
        .report.metrics
    )
    # Independently counted: 2 predicted, 2 gold, both aligned on indicator and horizon, 1 of 2 values right.
    assert m["raw_precision"] == 1.0 and m["raw_recall"] == 1.0
    assert m["numerical_fidelity"] == 0.5
    assert m["verified_rate"] == 0.0
    assert m["accepted_recall"] == 0.0  # a failed summary contributes nothing accepted
    assert m["unsupported_item_rate"] == pytest.approx(
        1 / 3
    )  # outlook + 2 forecasts; one has an error


def test_a_missed_forecast_lowers_recall_only(conn, tmp_path):
    version = seed_version(conn)
    partial = draft(version)
    partial["forecasts"] = partial["forecasts"][:1]
    store_summary(conn, version, output=partial, review=None, publish=False)
    m = (
        evaluate_stored(conn, annotations(tmp_path, {"version_id": version, **GOLD}))
        .groups[0]
        .report.metrics
    )
    assert m["raw_precision"] == 1.0 and m["raw_recall"] == 0.5


def test_unannotated_versions_are_ignored_and_unsummarised_ones_counted(conn, tmp_path):
    annotated, other, bare = (
        seed_version(conn),
        seed_version(conn, doc="b"),
        seed_version(conn, doc="c"),
    )
    store_summary(conn, annotated, review=None, publish=False)
    store_summary(conn, other, review=None, publish=False)
    report = evaluate_stored(
        conn, annotations(tmp_path, {"version_id": annotated, **GOLD}, {"version_id": bare, **GOLD})
    )
    assert report.groups[0].documents == 1
    assert report.unsummarised == (bare,)


def test_the_report_is_labelled_real_and_kept_apart_from_the_replay_baseline(conn, tmp_path):
    version = seed_version(conn)
    store_summary(conn, version, review=None, publish=False)
    text = evaluate_stored(
        conn, annotations(tmp_path, {"version_id": version, **GOLD})
    ).to_markdown()
    assert "Real documents" in text and "not comparable with the synthetic replay" in text
    assert "Test Annotator" in text and "fake/fake-1" in text


def test_a_model_filter_selects_one_model(conn, tmp_path):
    version = seed_version(conn)
    store_summary(conn, version, review=None, publish=False)
    ann = annotations(tmp_path, {"version_id": version, **GOLD})
    assert evaluate_stored(conn, ann, model="other-model").groups == ()


@pytest.mark.parametrize("bad", [
    {"version_id": 1, "indicators": ["gdp"], "forecasts": [], "surprise": 1},
    {"version_id": 1, "indicators": ["not_an_indicator"], "forecasts": []},
    {"version_id": 0, "indicators": [], "forecasts": []},
])  # fmt: skip
def test_the_annotation_file_is_strict(tmp_path, bad):
    with pytest.raises(AnnotationError):
        annotations(tmp_path, bad)


def test_provider_errors_are_counted_and_costed_but_not_scored(conn, tmp_path):
    version = seed_version(conn)
    key = ss.SummaryKey(version, "fake", "fake-1", "outlook-v2", "3b-1", "b" * 64)
    for attempt in (1, 2):
        run = ss.start_run(conn, provider="fake", model="fake-1", hosted=False, prompt_version="outlook-v2",
                           processing_version="3b-1", limits={}, dry_run=False, now=NOW)  # fmt: skip
        with transaction(conn):
            failed = ss.insert_summary(conn, key, run_id=run, attempt=attempt, hosted=False, verifier_version="v",
                                       parameters={}, raw_output=None, output_json=None, status="provider_error",
                                       error_class="timeout", verification=None, now=NOW)  # fmt: skip
        usage(conn, failed, version, cost=0.002, latency=120_000)
    sid = store_summary(conn, version, review=None, publish=False)
    usage(conn, sid, version, cost=0.01, latency=900)
    (group,) = evaluate_stored(conn, annotations(tmp_path, {"version_id": version, **GOLD})).groups
    assert group.documents == 1 and group.provider_errors == 2
    assert group.recorded_cost_usd == pytest.approx(0.014)
    assert group.report.metrics["mean_latency_ms"] == 900  # the scored summary's own calls


def _provider_error(conn, version, model):
    key = ss.SummaryKey(version, "fake", model, "outlook-v2", "3b-1", "b" * 64)
    run = ss.start_run(conn, provider="fake", model=model, hosted=False, prompt_version="outlook-v2",
                       processing_version="3b-1", limits={}, dry_run=False, now=NOW)  # fmt: skip
    with transaction(conn):
        return ss.insert_summary(conn, key, run_id=run, attempt=1, hosted=False, verifier_version="v",
                                 parameters={}, raw_output=None, output_json=None, status="provider_error",
                                 error_class="timeout", verification=None, now=NOW)  # fmt: skip


def _two_models(conn, tmp_path):
    """Model A summarises both annotated documents; model B only the first."""
    first, second = seed_version(conn), seed_version(conn, doc="b")
    for version in (first, second):
        store_summary(conn, version, review=None, publish=False, model="model-a")
    store_summary(conn, first, review=None, publish=False, model="model-b")
    ann = annotations(tmp_path, {"version_id": first, **GOLD}, {"version_id": second, **GOLD})
    return first, second, ann


def test_coverage_is_calculated_for_the_requested_model_only(conn, tmp_path):
    _, second, ann = _two_models(conn, tmp_path)
    report = evaluate_stored(conn, ann, model="model-b")
    (group,) = report.groups
    assert group.model == "model-b" and group.documents == 1
    assert report.unsummarised == (second,)  # model A's summary of it must not count
    assert "Annotated but never summarised" in report.to_markdown()


def test_the_model_that_summarised_everything_reports_complete_coverage(conn, tmp_path):
    _, _, ann = _two_models(conn, tmp_path)
    report = evaluate_stored(conn, ann, model="model-a")
    assert report.groups[0].documents == 2 and report.unsummarised == ()


def test_without_a_model_filter_coverage_is_the_union_across_models(conn, tmp_path):
    first, second, ann = _two_models(conn, tmp_path)
    report = evaluate_stored(conn, ann)
    assert sorted((g.model, g.documents) for g in report.groups) == [("model-a", 2), ("model-b", 1)]
    assert report.unsummarised == ()
    bare = seed_version(conn, doc="c")  # summarised by nobody
    ann = annotations(tmp_path, {"version_id": first, **GOLD}, {"version_id": bare, **GOLD})
    assert evaluate_stored(conn, ann).unsummarised == (bare,)


def test_an_unknown_model_does_not_inherit_coverage_from_another_model(conn, tmp_path):
    first, second, ann = _two_models(conn, tmp_path)
    report = evaluate_stored(conn, ann, model="never-ran")
    assert report.groups == () and report.unsummarised == (first, second)


def test_a_models_provider_error_only_rows_do_not_count_as_summarised(conn, tmp_path):
    first, second, ann = _two_models(conn, tmp_path)
    _provider_error(conn, second, "model-b")  # B tried the second document and failed
    report = evaluate_stored(conn, ann, model="model-b")
    (group,) = report.groups
    assert group.documents == 1 and group.provider_errors == 1
    assert report.unsummarised == (second,)
    assert evaluate_stored(conn, ann).unsummarised == ()  # model A still covers it in aggregate


def test_a_model_with_only_provider_errors_has_no_coverage(conn, tmp_path):
    version = seed_version(conn)
    _provider_error(conn, version, "model-x")
    ann = annotations(tmp_path, {"version_id": version, **GOLD})
    report = evaluate_stored(conn, ann, model="model-x")
    (group,) = report.groups
    assert group.documents == 0 and group.provider_errors == 1
    assert report.unsummarised == (version,)


def test_filtering_by_model_leaves_that_models_scoring_cost_and_latency_unchanged(conn, tmp_path):
    first, second, ann = _two_models(conn, tmp_path)
    sid = conn.execute(
        "SELECT id FROM research_summary WHERE version_id = ? AND model = 'model-b'", (first,)
    ).fetchone()[0]
    usage(conn, sid, first, cost=0.02, latency=700)
    filtered = evaluate_stored(conn, ann, model="model-b").groups[0]
    unfiltered = next(g for g in evaluate_stored(conn, ann).groups if g.model == "model-b")
    assert filtered.recorded_cost_usd == unfiltered.recorded_cost_usd == pytest.approx(0.02)
    assert filtered.report.metrics == unfiltered.report.metrics
    assert filtered.report.metrics["mean_latency_ms"] == 700
