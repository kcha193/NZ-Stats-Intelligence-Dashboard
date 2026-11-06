"""A generated attribution matrix with a semantic oracle (PR 46 convergence review). SYNTHETIC FIXTURE: invented sentences.

Each case is a sentence in which the true forecaster of every figure is known BY CONSTRUCTION, not read from the verifier. The matrix
crosses the classes the review rounds kept finding one at a time: several forecasts in one sentence, several organisations, several
figures and indicators, the author versus a third party, the author's own analysts, modified group names, passive and "according to"
attribution, speech verbs, comparisons, relative clauses, comments on the year, and a reporter's separate figure.

For a claimed figure and a label, the oracle says whether the label names that figure's forecaster. `outcome()` then classes what a
verifier did:

  correct       accepted a true label, or refused a wrong one
  over_reject   refused a true label (the whole summary fails: an availability defect, and it fails closed)
  under_reject  accepted a wrong label (a misattribution passes: a safety defect)

This module has no pytest and no verifier import, so a script can run the same cases against any revision of the code.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from itertools import permutations

AUTHOR_LABEL = ("author", "The Treasury")
STRANGER = ("third_party", "Kiwibank")  # named in no sentence: always refused
# Generic group labels. Documented residual: such a label answers every group block, and only its noun is compared with the evidence.
GENERIC_GROUP_LABELS = frozenset({"Analysts", "Banks", "Major banks"})


@dataclass(frozen=True)
class Entity:
    key: str
    subjects: tuple[str, ...]
    agents: tuple[str, ...]  # after "by" and "according to"
    singular: bool  # the verb takes an "s"
    labels: tuple[tuple[str, str], ...]  # (role, label) pairs that name this entity


_ANALYSTS_AT_ANZ = (("third_party", "ANZ"), ("third_party", "Analysts"))
ENTITIES: dict[str, Entity] = {
    e.key: e
    for e in (
        Entity(
            "author",
            (
                "We",
                "Our analysts",
                "Our market analysts",
                "Treasury forecasters",
                "The Treasury's economists",
            ),
            ("us", "our analysts", "the Treasury"),
            False,
            (AUTHOR_LABEL,),
        ),
        Entity(
            "author_group",
            ("Analysts at the Treasury",),
            ("analysts at the Treasury",),
            False,
            (AUTHOR_LABEL,),
        ),
        Entity(
            "imf",
            ("The IMF", "The International Monetary Fund"),
            ("the IMF", "the International Monetary Fund"),
            True,
            (("third_party", "International Monetary Fund"), ("third_party", "IMF")),
        ),
        Entity("oecd", ("The OECD",), ("the OECD",), True, (("third_party", "OECD"),)),
        Entity("anz", ("ANZ",), ("ANZ",), True, (("third_party", "ANZ"),)),
        Entity(
            "analysts",
            ("Analysts", "Market analysts", "Most analysts"),
            ("analysts", "market analysts"),
            False,
            (("third_party", "Analysts"),),
        ),
        Entity(
            "banks",
            ("The major banks", "Banks"),
            ("the major banks", "banks"),
            False,
            (("third_party", "Banks"), ("third_party", "Major banks")),
        ),
        Entity("anz_group", ("Analysts at ANZ",), ("analysts at ANZ",), False, _ANALYSTS_AT_ANZ),
    )
}

FORECAST_VERBS = ("expect", "forecast", "project", "predict", "anticipate")
COMMENTS = ("a challenging year", "a testing year", "too optimistic", "a tough year")


@dataclass(frozen=True)
class Figure:
    value: float
    horizon: str
    maker: str  # an Entity key


@dataclass(frozen=True)
class Case:
    id: str
    cls: str
    sentence: str
    figures: tuple[Figure, ...]

    @property
    def entities(self) -> set[str]:
        return {f.maker for f in self.figures}


# ---- one assertion ----------------------------------------------------------------------------------------------------------------


def _verb(verb: str, singular: bool) -> str:
    return verb + "s" if singular else verb


def _takes_s(entity: Entity, subject: str) -> bool:
    return entity.singular and subject != "We" and not subject.startswith("Our")


def assertions(key: str, ind: str, n: int) -> Iterator[tuple[str, str]]:
    """(form, text) for the surface forms of `key` saying that `ind` will be `n`% in 2029."""
    e = ENTITIES[key]
    for i, subject in enumerate(e.subjects):
        s = _takes_s(e, subject)
        for verb in FORECAST_VERBS[: 2 if i else len(FORECAST_VERBS)]:
            yield "active", f"{subject} {_verb(verb, s)} {ind} of {n}% in 2029"
        yield "active", f"{subject} {_verb('expect', s)} {ind} to be {n}% in 2029"
        yield "said", f"{subject} said {ind} would be {n}% in 2029"
    for agent in e.agents:
        yield "passive", f"{ind.capitalize()} of {n}% in 2029 is forecast by {agent}"
        yield "expected_by", f"{ind.capitalize()} of {n}% in 2029 is expected by {agent}"
        yield "according", f"According to {agent}, {ind} will be {n}% in 2029"


def _later(text: str) -> str:
    """`text` as the second part of a sentence: a proper name keeps its capital, an ordinary first word does not."""
    head = text.split(" ", 1)[0]
    return text if head.isupper() or head == "Treasury" else text[0].lower() + text[1:]


def _end(text: str) -> str:
    return text + "."


# ---- compositions -----------------------------------------------------------------------------------------------------------------

JOINERS = (", but ", ", while ", "; ", ", and ")


def _single() -> Iterator[Case]:
    for key in ENTITIES:
        for _, text in assertions(key, "growth", 3):
            yield Case(f"single/{key}/{text}", "single", _end(text), (Figure(3, "2029", key),))


def _two_forecasts() -> Iterator[Case]:
    """Several forecasts, organisations, figures and indicators in one sentence: each figure has its own forecaster."""
    wanted_first = ("active", "said", "passive", "according")
    wanted_second = ("active", "said", "passive", "expected_by")
    for a, b in permutations(ENTITIES, 2):
        first = [t for f, t in assertions(a, "growth", 3) if f in wanted_first][::3]
        second = [t for f, t in assertions(b, "inflation", 2) if f in wanted_second][::3]
        for t1 in first:
            for t2 in second:
                for join in JOINERS:
                    yield Case(
                        f"two/{a}+{b}/{t1}{join}{t2}",
                        "two_forecasts",
                        _end(t1 + join + _later(t2)),
                        (Figure(3, "2029", a), Figure(2, "2029", b)),
                    )


def _two_sentences() -> Iterator[Case]:
    for a, b in permutations(ENTITIES, 2):
        first = [t for f, t in assertions(a, "growth", 3) if f in ("active", "passive")][:2]
        second = [t for f, t in assertions(b, "inflation", 2) if f in ("active", "passive")][:2]
        for t1 in first:
            for t2 in second:
                yield Case(
                    f"sentences/{a}+{b}/{t1}. {t2}",
                    "two_sentences",
                    f"{_end(t1)} {_end(t2)}",
                    (Figure(3, "2029", a), Figure(2, "2029", b)),
                )


def _comparisons() -> Iterator[Case]:
    """A second party appears only as the other side of a comparison: it made nothing the sentence claims."""
    for a, b in permutations(ENTITIES, 2):
        eb = ENTITIES[b]
        subject, agent = eb.subjects[0], eb.agents[0]
        s = _takes_s(eb, subject)
        for t1 in [t for f, t in assertions(a, "growth", 3) if f == "active"][:2]:
            for tail in (
                f", higher than forecast by {agent}",
                f", lower than forecast by {agent}",
                f", above what {_later(subject)} {_verb('expect', s)}",
                f", below what {_later(subject)} {_verb('forecast', s)}",
                f", unlike {agent}",
                f", more than {agent} {_verb('expect', s)}",
            ):
                yield Case(
                    f"compare/{a}~{b}/{t1}{tail}",
                    "comparison",
                    _end(t1 + tail),
                    (Figure(3, "2029", a),),
                )
            tail = f", compared with 2% forecast by {agent}"
            yield Case(
                f"compare-figure/{a}~{b}/{t1}{tail}",
                "comparison_with_figure",
                _end(t1 + tail),
                (Figure(3, "2029", a), Figure(2, "2029", b)),
            )


def _year_comments() -> Iterator[Case]:
    """A relative clause that only comments on the year or the forecast credits nobody with the figure; one with a figure of its own does."""
    for a, b in permutations(ENTITIES, 2):
        eb = ENTITIES[b]
        for t1 in [t for f, t in assertions(a, "growth", 3) if f == "active"][:2]:
            for subject in eb.subjects[:2]:
                s = _takes_s(eb, subject)
                for verb in ("say", "expect", "said"):
                    for comment in COMMENTS:
                        sv = verb if verb == "said" else _verb(verb, s)
                        link = "to be" if verb == "expect" else "will be"
                        yield Case(
                            f"comment/{a}/{b}/{t1}, which {_later(subject)} {sv} {comment}",
                            "year_comment",
                            _end(f"{t1}, which {_later(subject)} {sv} {link} {comment}"),
                            (Figure(3, "2029", a),),
                        )
            subject = eb.subjects[0]
            sv = _verb("say", _takes_s(eb, subject))
            yield Case(
                f"which-figure/{a}/{b}/{t1}",
                "which_gives_figure",
                _end(f"{t1}, which {_later(subject)} {sv} will be 2%"),
                (Figure(3, "2029", a), Figure(2, "2029", b)),
            )


def _reporters() -> Iterator[Case]:
    """A reporter's separate figure earlier or later in the sentence does not reach another forecaster's figure."""
    for reporter in ("imf", "oecd"):
        said = f"{ENTITIES[reporter].subjects[0]} said growth would be 2% in 2029"
        for b in ENTITIES:
            if b == reporter:
                continue
            for t in [t for f, t in assertions(b, "growth", 3) if f in ("active", "said")][:3]:
                yield Case(
                    f"reporter-first/{reporter}/{b}/{t}",
                    "reporter_then_forecaster",
                    _end(f"{said}, but {_later(t)}"),
                    (Figure(2, "2029", reporter), Figure(3, "2029", b)),
                )
                yield Case(
                    f"reporter-last/{reporter}/{b}/{t}",
                    "forecaster_then_reporter",
                    _end(f"{t}, but {_later(said)}"),
                    (Figure(3, "2029", b), Figure(2, "2029", reporter)),
                )


def cases() -> list[Case]:
    out: list[Case] = []
    for part in (
        _single,
        _two_forecasts,
        _two_sentences,
        _comparisons,
        _year_comments,
        _reporters,
    ):
        out += list(part())
    return out


# ---- the oracle -------------------------------------------------------------------------------------------------------------------


def labels_for(case: Case) -> list[tuple[str, str]]:
    """The labels worth trying: the author's, those of every entity the sentence names, and one nobody in it is called."""
    seen: list[tuple[str, str]] = [AUTHOR_LABEL]
    lowered = case.sentence.lower()
    for key, e in ENTITIES.items():
        named = key in case.entities or any(t.lower() in lowered for t in (*e.subjects, *e.agents))
        if named:
            seen += [label for label in e.labels if label not in seen]
    return [*seen, STRANGER]


def truth(figure: Figure, label: tuple[str, str]) -> bool:
    """Does `label` name the forecaster of `figure`?"""
    return label in ENTITIES[figure.maker].labels


def outcome(expected_accept: bool, refused: bool) -> str:
    if expected_accept and refused:
        return "over_reject"
    if not expected_accept and not refused:
        return "under_reject"
    return "correct"


def documented_residual(label: tuple[str, str]) -> bool:
    """A wrong label accepted by the documented rule that a generic group label answers every group block."""
    return label[0] == "third_party" and label[1] in GENERIC_GROUP_LABELS
