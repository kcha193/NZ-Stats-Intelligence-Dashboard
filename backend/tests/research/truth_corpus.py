"""Phase 4V: a synthetic, truth-labelled corpus for measuring verifier false acceptances and false rejections (SYNTHETIC FIXTURE).

Every example is one invented sentence and one claim about it, and its truth is known because it was written that way:

- `supported`      the sentence states what the claim says; accepting is right, rejecting is a FALSE REJECTION;
- `unsupported`    the sentence does not state it; rejecting is right, accepting is a FALSE ACCEPTANCE;
- `ambiguous`      a careful reader could go either way; reported, never scored;
- `inexpressible`  true, but the contract has no way to state it; accepting would be wrong, rejecting is the best available.

This measures the rules on constructed minimal pairs. It does not measure economic accuracy, a real model, or real documents, and a
corpus I wrote cannot show the rules generalise. A reduced error count here is not evidence the dashboard is more correct.

Run `python -m tests.research.truth_corpus` from backend/ to print the scorecard.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from nzstats.research.contract import PolicyDecision, ReportedFact, SectionText

from .verify_support import check, ref

PUBLISHED = {
    "treasury": date(2026, 10, 29),
    "rbnz": date(2026, 10, 28),
}  # a decision is dated the day it is published
TRUTHS = ("supported", "unsupported", "ambiguous", "inexpressible")


@dataclass(frozen=True)
class Example:
    id: str
    group: str
    truth: str
    sentence: str
    claim: Callable[[str], object]
    institution: str
    note: str = ""

    def accepted(self, version: str) -> bool:
        quote = self.sentence.rstrip(".")
        sections = {0: SectionText(f"SYNTHETIC FIXTURE. {self.sentence}")}
        claim = self.claim(quote)
        items = {"decisions": [claim]} if isinstance(claim, PolicyDecision) else {"facts": [claim]}
        report = check(
            sections, outlook_ref=ref(0, "SYNTHETIC FIXTURE"), institution=self.institution, published_on=PUBLISHED[self.institution],
            verifier=version, **items,
        )  # fmt: skip
        return not report.errors


def fact(id, group, truth, sentence, value, unit, period, note="", source="Stats NZ") -> Example:
    return Example(
        id, group, truth, sentence,
        lambda q: ReportedFact(text="A figure.", source=source, value=value, unit=unit, period=period, evidence=[ref(0, q)]),
        "treasury", note,
    )  # fmt: skip


def decision(
    id, group, truth, sentence, *, action="hold", rate=2.75, vote=None, on="2026-10-28", note=""
) -> Example:
    return Example(
        id, group, truth, sentence,
        lambda q: PolicyDecision(
            action=action, rate=rate, decided_on=on, decision_maker="Monetary Policy Committee",
            vote_for=vote[0] if vote else None, vote_against=vote[1] if vote else None, evidence=[ref(0, q)],
        ),
        "rbnz", note,
    )  # fmt: skip


S, J, M = "September 2026 quarter", "June 2026 quarter", "March 2026 quarter"
OCR = "the Official Cash Rate at 2.75 percent"
CPI = f"Annual CPI inflation was 3.7% in the {S}, up from 3.3% in the {J}."

CORPUS: tuple[Example, ...] = (
    # --- votes ---------------------------------------------------------------------------------------------------
    *(
        decision(
            f"vote-{name}-ok",
            "vote",
            "supported",
            f"The Monetary Policy Committee today voted {pair} to hold {OCR}.",
            vote=(4, 3),
        )
        for name, pair in (
            ("colon", "4:3"),
            ("spaced-colon", "4 : 3"),
            ("en-dash", "4–3"),
            ("hyphen", "4-3"),
            ("to", "4 to 3"),
            ("words", "four to three"),
        )
    ),  # fmt: skip
    decision(
        "vote-colon-reversed",
        "vote",
        "unsupported",
        f"The Monetary Policy Committee today voted 4:3 to hold {OCR}.",
        vote=(3, 4),
    ),
    decision(
        "vote-colon-wrong",
        "vote",
        "unsupported",
        f"The Monetary Policy Committee today voted 4:3 to hold {OCR}.",
        vote=(5, 2),
    ),
    decision(
        "vote-dash-wrong",
        "vote",
        "unsupported",
        f"The Monetary Policy Committee today voted 4–3 to hold {OCR}.",
        vote=(5, 2),
    ),
    decision(
        "vote-clock-time",
        "vote",
        "unsupported",
        f"The Committee voted at 4:30 to hold {OCR}.",
        vote=(4, 3),
        note="a time, not a vote",
    ),
    decision(
        "vote-ratio",
        "vote",
        "unsupported",
        f"The Committee voted to hold {OCR}, a 3:1 ratio of members to staff.",
        vote=(3, 1),
    ),
    decision(
        "vote-score",
        "vote",
        "unsupported",
        f"The Committee agreed to hold {OCR}. The score was 4:3 at half time.",
        vote=(4, 3),
        note="a colon pair outside a vote sentence",
    ),  # fmt: skip
    # --- periods beside a comparison ------------------------------------------------------------------------------
    fact(
        "period-up-from-ok",
        "period",
        "supported",
        CPI,
        3.7,
        "percent",
        S,
        "the figure's own period precedes 'up from'",
    ),
    fact(
        "period-rose-from-ok",
        "period",
        "supported",
        f"Annual CPI inflation rose to 3.7% in the {S} from 3.3% in the {J}.",
        3.7,
        "percent",
        S,
    ),  # fmt: skip
    fact(
        "period-compared-with-ok",
        "period",
        "supported",
        "Net migration was 3,190 in July 2026, compared with 1,530 in June 2026.",
        3190,
        "persons",
        "July 2026",
    ),  # fmt: skip
    fact(
        "period-single-ok",
        "period",
        "supported",
        f"Annual CPI inflation was 3.7% in the {S}.",
        3.7,
        "percent",
        S,
    ),
    fact(
        "period-base-figure",
        "period",
        "supported",
        CPI,
        3.3,
        "percent",
        J,
        "TRUE but still rejected: the base figure's own side is the second half of the clause (a documented limit)",
    ),  # fmt: skip
    fact(
        "period-wrong-base",
        "period",
        "unsupported",
        CPI,
        3.7,
        "percent",
        J,
        "the base's period given to the figure",
    ),
    fact(
        "period-wrong-other", "period", "unsupported", CPI, 3.7, "percent", "December 2026 quarter"
    ),
    fact(
        "period-other-figure",
        "period",
        "unsupported",
        "Imports rose 4% in June with exports at 6.3% compared with 5.9% in September.",
        6.3,
        "percent",
        "June",
        "June belongs to the imports figure",
    ),  # fmt: skip
    fact(
        "period-other-figure-null",
        "period",
        "supported",
        "Imports rose 4% in June with exports at 6.3% compared with 5.9% in September.",
        6.3,
        "percent",
        None,
        "a null period is what the prompt asks for here",
    ),  # fmt: skip
    fact(
        "period-other-figure-own",
        "period",
        "supported",
        "Imports rose 4% in June with exports at 6.3% compared with 5.9% in September.",
        4,
        "percent",
        "June",
        "TRUE: June is the 4% figure's period; rejected because the clause is ambiguous to the rules",
    ),  # fmt: skip
    fact(
        "period-two-months-one-figure",
        "period",
        "ambiguous",
        "Net migration was 3,190 in July 2026 and August 2026.",
        3190,
        "persons",
        "July 2026",
        "one figure, two months",
    ),  # fmt: skip
    # --- forecast wording ----------------------------------------------------------------------------------------------
    fact(
        "fc-measured-expectation",
        "forecast_wording",
        "supported",
        f"Inflation expectations rose to 2.4% in the {S}.",
        2.4,
        "percent",
        S,
    ),  # fmt: skip
    fact(
        "fc-expectation-index",
        "forecast_wording",
        "supported",
        "The business expectations index fell to 12 in October 2026.",
        12,
        "index",
        "October 2026",
    ),  # fmt: skip
    fact(
        "fc-survey-measure",
        "forecast_wording",
        "supported",
        f"The two-year-ahead inflation expectations measure was 2.3% in the survey for the {J}.",
        2.3,
        "percent",
        J,
    ),  # fmt: skip
    fact(
        "fc-expectation-as-forecast",
        "forecast_wording",
        "unsupported",
        "Inflation expectations are for 2.4% in 2027.",
        2.4,
        "percent",
        "2027",
    ),  # fmt: skip
    fact(
        "fc-market-expectation",
        "forecast_wording",
        "unsupported",
        "Market expectations are for unemployment to peak at 5.4% in 2027.",
        5.4,
        "percent",
        "2027",
    ),  # fmt: skip
    fact(
        "fc-forecast-control",
        "forecast_wording",
        "unsupported",
        "Unemployment is forecast to rise to 5.4% in 2027.",
        5.4,
        "percent",
        "2027",
    ),  # fmt: skip
    fact(
        "fc-nowcast-of-completed-quarter",
        "forecast_wording",
        "ambiguous",
        f"The Treasury expects unemployment to be 5.1% in the {J}.",
        5.1,
        "percent",
        J,
        "an estimate for a quarter that has ended",
    ),  # fmt: skip
    # --- units and currency --------------------------------------------------------------------------------------------
    fact(
        "unit-nzd-billion",
        "unit",
        "supported",
        "The deficit was $4.2 billion in the year to June 2026.",
        4.2,
        "nzd_billion",
        "year to June 2026",
    ),  # fmt: skip
    fact(
        "unit-nz-prefixed",
        "unit",
        "supported",
        "The deficit was NZ$4.2 billion in the year to June 2026.",
        4.2,
        "nzd_billion",
        "year to June 2026",
    ),  # fmt: skip
    fact(
        "unit-percent",
        "unit",
        "supported",
        f"Annual CPI inflation was 3.7% in the {S}.",
        3.7,
        "percent",
        S,
    ),
    fact(
        "unit-missing-nzd",
        "unit",
        "unsupported",
        "The deficit was $4.2 billion in the year to June 2026.",
        4.2,
        None,
        "year to June 2026",
        "the unit is shown beside the figure and was left null",
    ),  # fmt: skip
    fact(
        "unit-us-as-nzd",
        "unit",
        "unsupported",
        "Brent crude averaged US$82 a barrel in October 2026.",
        82,
        "nzd",
        "October 2026",
        "another currency relabelled as New Zealand dollars",
    ),  # fmt: skip
    fact(
        "unit-aus-as-nzd-billion",
        "unit",
        "unsupported",
        "The Australian deficit was A$4.2 billion in October 2026.",
        4.2,
        "nzd_billion",
        "October 2026",
    ),  # fmt: skip
    fact(
        "unit-us-null",
        "unit",
        "inexpressible",
        "Brent crude averaged US$82 a barrel in October 2026.",
        82,
        None,
        "October 2026",
        "the contract has no US-dollar unit",
    ),  # fmt: skip
    fact(
        "unit-us-invented",
        "unit",
        "inexpressible",
        "Brent crude averaged US$82 a barrel in October 2026.",
        82,
        "usd_per_barrel",
        "October 2026",
        "the contract has no US-dollar unit",
    ),  # fmt: skip
    # --- decisions ------------------------------------------------------------------------------------------------------
    decision(
        "dec-plain-ok",
        "decision",
        "supported",
        f"The Monetary Policy Committee agreed to hold {OCR}.",
    ),
    decision(
        "dec-dated-ok",
        "decision",
        "supported",
        f"On 28 October 2026 the Monetary Policy Committee agreed to hold {OCR}.",
    ),
    decision(
        "dec-commentary",
        "decision",
        "unsupported",
        "Markets expect the OCR to be cut to 2.5 percent in 2027.",
        action="decrease",
        rate=2.5,
        note="commentary about a future move",
    ),  # fmt: skip
    decision(
        "dec-expects-to-hold",
        "decision",
        "unsupported",
        "Looking ahead, the Committee expects to hold the OCR at 2.75 percent.",
    ),
    decision(
        "dec-wrong-rate",
        "decision",
        "unsupported",
        f"The Monetary Policy Committee agreed to hold {OCR}.",
        rate=3.0,
    ),
    decision(
        "dec-wrong-action",
        "decision",
        "unsupported",
        f"The Monetary Policy Committee agreed to hold {OCR}.",
        action="decrease",
    ),
    decision(
        "dec-forward-first",
        "decision",
        "supported",
        f"The Committee expects inflation to ease after it agreed to hold {OCR}.",
        note="TRUE but rejected: a forward word precedes the decision verb, so the rule fails closed",
    ),  # fmt: skip
    decision(
        "dec-double-action",
        "decision",
        "ambiguous",
        f"The Committee agreed to hold {OCR}, having raised it earlier in the year.",
        note="two action words in one clause",
    ),  # fmt: skip
)


def score(version: str) -> dict[str, object]:
    """Counts for one verifier version over the corpus, with the ids behind every error."""
    rows = [(e, e.accepted(version)) for e in CORPUS]
    ids = lambda pred: sorted(e.id for e, ok in rows if pred(e, ok))  # noqa: E731
    return {
        "version": version,
        "supported": sum(e.truth == "supported" for e, _ in rows),
        "unsupported": sum(e.truth == "unsupported" for e, _ in rows),
        "ambiguous": sum(e.truth == "ambiguous" for e, _ in rows),
        "inexpressible": sum(e.truth == "inexpressible" for e, _ in rows),
        "false_rejections": ids(lambda e, ok: e.truth == "supported" and not ok),
        "false_acceptances": ids(lambda e, ok: e.truth == "unsupported" and ok),
        "ambiguous_accepted": ids(lambda e, ok: e.truth == "ambiguous" and ok),
        "ambiguous_rejected": ids(lambda e, ok: e.truth == "ambiguous" and not ok),
        "inexpressible_accepted": ids(lambda e, ok: e.truth == "inexpressible" and ok),
    }


def main() -> None:
    results = [score(v) for v in ("verify-4", "verify-5")]
    print(f"{len(CORPUS)} synthetic examples: " + ", ".join(f"{t} {results[0][t]}" for t in TRUTHS))
    for r in results:
        print(f"\n{r['version']}")
        print(
            f"  false rejections  {len(r['false_rejections'])}/{r['supported']}: {', '.join(r['false_rejections']) or '-'}"
        )
        print(
            f"  false acceptances {len(r['false_acceptances'])}/{r['unsupported']}: {', '.join(r['false_acceptances']) or '-'}"
        )
        print(
            f"  ambiguous accepted {len(r['ambiguous_accepted'])}, rejected {len(r['ambiguous_rejected'])} (not scored)"
        )
        print(
            f"  inexpressible accepted {len(r['inexpressible_accepted'])} of {r['inexpressible']}"
        )


if __name__ == "__main__":
    main()
