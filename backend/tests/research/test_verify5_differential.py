"""Phase 4V: `verify-5` against the previous verifier over the whole synthetic evaluation corpus (SYNTHETIC FIXTURE).

The change from `verify-4` is meant to be narrow: it may only remove a period error on a figure that is compared with a base,
add the rejection of another currency's dollar sign claimed as New Zealand dollars, and read the colon vote. This runs every
candidate and probe in the corpus through both and requires exactly that, nothing more.
"""

from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from nzstats.research.contract import ModelProvenance, assemble, parse_draft
from nzstats.research.evaluate import expand_output, load_eval_set
from nzstats.research.prompt import injection_findings
from nzstats.research.verify import VerificationContext, verify

EVAL_DIR = Path(__file__).parent / "eval_set"
CASES = load_eval_set(EVAL_DIR)
PROV = ModelProvenance(
    provider="fake", model="m", prompt_version="outlook-v5", processing_version="eval",
    input_text_sha256="0" * 64, created_at=datetime(2026, 11, 7, tzinfo=UTC),
)  # fmt: skip
ALLOWED_REMOVED = {"period_not_supported"}
ALLOWED_ADDED = {"unit_mismatch"}


def both(case, candidate, swap: tuple[str, str] | None = None):
    """(verify-4 report, verify-5 report) for a candidate, optionally with `swap` applied to the text and the quotes."""
    text = expand_output(candidate.output, case.version_ids, candidate.version)
    sections = case.versions[candidate.version]
    if swap:
        text = text.replace(*swap).replace(
            swap[0].encode("unicode_escape").decode(), swap[1]
        )  # JSON escapes the dash
        sections = {k: replace(v, text=v.text.replace(*swap)) for k, v in sections.items()}
    try:
        draft = parse_draft(text)
    except ValueError:
        return None
    summary = assemble(draft, version_id=case.version_ids[candidate.version], provenance=PROV)
    ctx = VerificationContext(
        published_on=date.fromisoformat(case.published_on) if case.published_on else None,
        injection_ordinals=tuple(injection_findings(sections)), institution=case.institution,
    )  # fmt: skip
    return verify(summary, sections, ctx, version="verify-4"), verify(
        summary, sections, ctx, version="verify-5"
    )


def codes(report) -> tuple[set[str], set[str]]:
    return {p.code for p in report.errors}, {p.code for p in report.warnings}


ALL = [(c, k) for c in CASES for k in c.candidates]


def test_the_corpus_is_the_one_the_other_suites_use():
    assert len(CASES) == 13 and len(ALL) == 52


@pytest.mark.parametrize(("case", "candidate"), ALL, ids=[f"{c.id}:{k.id}" for c, k in ALL])
def test_verify_5_differs_from_verify_4_only_in_the_three_intended_ways(case, candidate):
    got = both(case, candidate)
    if got is None:
        pytest.skip("the candidate is deliberately not valid JSON for the contract")
    (old_e, old_w), (new_e, new_w) = codes(got[0]), codes(got[1])
    assert old_e - new_e <= ALLOWED_REMOVED, f"verify-5 stopped reporting {old_e - new_e}"
    assert new_e - old_e <= ALLOWED_ADDED, f"verify-5 started reporting {new_e - old_e}"
    assert old_w == new_w  # no warning changed


def test_no_candidate_in_the_corpus_contains_the_changed_shapes_so_the_corpus_is_unchanged():
    # The corpus predates the three changes, so verify-5 must reproduce verify-4 on all of it. If a later case adds one of the
    # shapes, this test should be replaced by an explicit expectation for that case, not loosened.
    different = []
    for case, candidate in ALL:
        got = both(case, candidate)
        if got is not None and (codes(got[0]) != codes(got[1])):
            different.append(f"{case.id}:{candidate.id}")
    assert different == []


# --- the colon twin of every dash vote ---------------------------------------------------------------------
VOTE_CASES = [
    (c, k)
    for c, k in ALL
    if "4–3" in k.output.__repr__() or any("4–3" in s.text for s in c.versions[k.version].values())
]


def test_the_corpus_has_dash_votes_to_twin():
    assert VOTE_CASES


@pytest.mark.parametrize(
    ("case", "candidate"), VOTE_CASES, ids=[f"{c.id}:{k.id}" for c, k in VOTE_CASES]
)
def test_a_colon_twin_of_a_dash_vote_gets_the_dash_verdict_under_verify_5(case, candidate):
    dash = both(case, candidate)
    colon = both(case, candidate, swap=("4–3", "4:3"))
    if dash is None:
        pytest.skip("not a valid summary")
    # verify-5 reads the colon exactly as verify-4 read the dash ...
    assert codes(colon[1]) == codes(dash[0])
    # ... and verify-4 was blind to it: it can only differ by the vote codes.
    assert codes(colon[0])[0] ^ codes(dash[0])[0] <= {"vote_not_in_evidence", "vote_not_captured"}
