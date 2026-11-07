"""Phase 4V: a stored summary is always re-checked by the verifier that produced it (SYNTHETIC FIXTURE).

`verify-5` changes what one check means (a colon vote is read). The internal and public gates re-verify stored output when they
display it, so without pinning, introducing `verify-5` would silently re-grade a `verify-4` result such as summary 4 and the
dashboard would stop showing the findings it was stored with. The label on a row selects the rules it is shown under.
"""

import pytest

from nzstats.research import drafts, public
from nzstats.research.contract import OutlookSummary
from nzstats.research.drafts import draft_summaries
from nzstats.research.verify import (
    BASELINE_VERIFIER,
    VERIFIER_VERSION,
    VerificationContext,
    resolve_verifier,
    verify,
)

from . import test_drafts_auto as auto_support
from .llm_support import seed_version
from .public_support import registry, store_summary
from .support import institution

REG = registry(institution())


def test_the_current_verifier_is_the_one_after_the_baseline():
    assert (BASELINE_VERIFIER, VERIFIER_VERSION) == ("verify-4", "verify-5")


@pytest.mark.parametrize(
    ("stored", "used"),
    [("verify-4", "verify-4"), ("verify-5", "verify-5"), ("verify-3", "verify-4"), ("verify-2", "verify-4"),
     ("verify-99", "verify-4"), ("", "verify-4"), (None, "verify-4")],
)  # fmt: skip
def test_a_stored_label_selects_its_own_rules_and_an_unknown_one_keeps_the_baseline(stored, used):
    assert resolve_verifier(stored) == used


def test_replaying_under_a_named_version_labels_the_report_with_it(conn):
    version_id = seed_version(conn)
    store_summary(conn, version_id, review=None, publish=False)
    summary_sections = public.load_sections(conn, version_id)
    stored = conn.execute("SELECT output_json FROM research_summary").fetchone()[0]
    summary = OutlookSummary.model_validate_json(stored)
    assert verify(summary, summary_sections, version="verify-4").version == "verify-4"
    assert verify(summary, summary_sections).version == VERIFIER_VERSION
    with pytest.raises(ValueError, match="unknown verifier"):
        verify(summary, summary_sections, version="verify-99")


@pytest.fixture
def spy(monkeypatch):
    """Record the verifier version each gate passes to `verify` and otherwise behave exactly as before."""
    seen: list[str] = []

    def wrap(real):
        def spied(*args, version=VERIFIER_VERSION, **kwargs):
            seen.append(version)
            return real(*args, version=version, **kwargs)

        return spied

    monkeypatch.setattr(drafts, "verify", wrap(drafts.verify))
    monkeypatch.setattr(public, "verify", wrap(public.verify))
    return seen


@pytest.mark.parametrize(
    ("stored", "used"),
    [("verify-4", "verify-4"), ("verify-5", "verify-5"), ("verify-3", "verify-4")],
)
def test_the_internal_draft_gate_replays_a_row_under_its_own_verifier(
    conn, monkeypatch, spy, stored, used
):
    monkeypatch.setattr(auto_support, "VERIFIER_VERSION", stored)
    auto_support.store_hosted(conn, seed_version(conn))
    assert draft_summaries(conn, REG, auto_support.auto())
    assert spy == [used]


@pytest.mark.parametrize(("stored", "used"), [("verify-4", "verify-4"), ("verify-5", "verify-5")])
def test_the_public_gate_replays_a_row_under_its_own_verifier(conn, monkeypatch, spy, stored, used):
    from . import public_support

    monkeypatch.setattr(public_support, "VERIFIER_VERSION", stored)
    store_summary(conn, seed_version(conn))
    public.public_summaries(conn, registry())
    assert spy and set(spy) == {used}


# --- found by the independent review: every other place that re-grades or grades a stored summary ---------------------------
def test_real_model_evaluation_re_scores_a_row_under_its_own_verifier(conn, monkeypatch, tmp_path):
    from nzstats.research import pilot_eval

    from . import public_support
    from .test_pilot_eval import GOLD, annotations, usage

    seen: list[str] = []
    real = pilot_eval.verify

    def spied(*args, version=VERIFIER_VERSION, **kwargs):
        seen.append(version)
        return real(*args, version=version, **kwargs)

    monkeypatch.setattr(pilot_eval, "verify", spied)
    monkeypatch.setattr(public_support, "VERIFIER_VERSION", "verify-4")
    version = seed_version(conn)
    sid = store_summary(conn, version, review=None, publish=False)
    usage(conn, sid, version, cost=0.01, latency=1000)
    pilot_eval.evaluate_stored(conn, annotations(tmp_path, {"version_id": version, **GOLD}))
    assert seen == ["verify-4"]


def test_gold_scoring_labels_the_verifier_and_replays_the_one_it_is_given(conn):
    from nzstats.research.gold_extension import score_extension

    from .test_gold_extension import PAGE, GoldExtension, extension, fact, summary

    seed_version(conn, (PAGE,), published_on="2026-11-02")
    ext = GoldExtension.model_validate(extension())
    ctx = VerificationContext(published_on=None, institution="treasury")
    old = score_extension(conn, summary([fact()]), ext, ctx, verifier="verify-4")
    new = score_extension(conn, summary([fact()]), ext, ctx)
    assert (old.verifier, new.verifier) == ("verify-4", VERIFIER_VERSION)
    assert old.to_json()["verifier"] == "verify-4"


def test_summarise_stamps_and_grades_with_the_verifier_it_is_told_to_use(conn):
    import json

    from nzstats.research.contract import LlmLimits
    from nzstats.research.providers import FakeProvider
    from nzstats.research.summarise import summarise_versions

    from .llm_support import NOW, draft_json
    from .test_summarise import PRICING, Sleeps
    from .test_summarise import registry as summarise_registry

    seed_version(conn)
    summarise_versions(
        conn, summarise_registry(), FakeProvider(lambda req: draft_json(req.version_id)), pricing=PRICING,
        limits=LlmLimits(), sleep=Sleeps(), now_fn=lambda: NOW, verifier="verify-4",
    )  # fmt: skip
    (row,) = conn.execute("SELECT verifier_version, verification FROM research_summary").fetchall()
    assert row[0] == "verify-4" and json.loads(row[1])["version"] == "verify-4"


def test_the_phase_4s_pilot_runs_the_pipeline_under_its_frozen_verifier():
    import inspect

    from nzstats.research import pilot

    # Phase 4W: the pipeline grades with the plan's verifier (the dry run and the real run); Phase 4N and 4S plans keep verify-4.
    assert inspect.getsource(pilot).count("verifier=plan.verifier") == 2
    assert {p.verifier for p in pilot.PLANS.values()} == {"verify-4"}
