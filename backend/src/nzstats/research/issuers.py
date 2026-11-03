"""Who made a forecast: the organisations a document names, and the wording that credits a figure to one (Phase 4I).

The checks are lexical, like the rest of the verifier. An organisation is *named* when its name or one of its
publications appears ("IMF", "World Economic Outlook"). A figure is *attributed* to it only by wording that makes
it the forecaster: a publication name, "the IMF expects/forecasts", "the IMF's forecast", "according to the IMF",
"Source: IMF". Naming an organisation as the subject of a forecast ("the RBNZ is expected to cut") does not
attribute the forecast to it. "We" and "our" are the document's author.

`reported` adds wording that names a forecaster in the past tense ("the MPC said it expected") or the market's view ("markets
expect"). It is narrow and separate: the verifier uses it only to block a claim, never to let one pass.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Organisation:
    key: str  # the research registry's institution key where there is one
    names: str  # regex alternatives for the organisation itself
    publications: str | None = None  # regex alternatives: naming one of these attributes the figure


ORGANISATIONS: tuple[Organisation, ...] = (
    Organisation("imf", r"\bIMF\b|International Monetary Fund",
                 r"\bWEO\b|World Economic Outlook"),
    Organisation("oecd", r"\bOECD\b|Organisation for Economic Co-operation and Development",
                 r"OECD Economic Outlook"),
    Organisation("world_bank", r"World Bank", r"Global Economic Prospects"),
    Organisation("rba", r"Reserve Bank of Australia|\bRBA\b"),
    Organisation("fed", r"Federal Reserve|\bthe Fed\b|\bFOMC\b"),
    Organisation("rbnz", r"Reserve Bank(?! of (?:Australia|India))|\bRBNZ\b|Monetary Policy Committee"
                 r"|\bMPC\b|Te Pūtea Matua",
                 r"Monetary Policy Statement|\bMPS\b|Monetary Policy Review|Financial Stability Report"),
    Organisation("treasury", r"Treasury|Te Tai Ōhanga",
                 r"\bPEU\b|\bPREFU\b|Pre-election (?:Economic and Fiscal )?Update|\bHYEFU\b|\bBEFU\b"
                 r"|Half Year Economic and Fiscal Update|Budget Economic and Fiscal Update"
                 r"|Fiscal Strategy Report|Economic and Fiscal Update"),
    Organisation("nzier", r"\bNZIER\b|New Zealand Institute of Economic Research",
                 r"\bQSBO\b|Quarterly Survey of Business Opinion"),
    Organisation("consensus", r"Consensus Economics|\bconsensus\b"),
    Organisation("anz", r"\bANZ\b"),
    Organisation("asb", r"\bASB\b"),
    Organisation("bnz", r"\bBNZ\b|Bank of New Zealand"),
    Organisation("westpac", r"Westpac"),
    Organisation("kiwibank", r"Kiwibank"),
    Organisation("infometrics", r"Infometrics"),
    Organisation("deloitte", r"Deloitte"),
    # Not an organisation, but a forecast all the same: what market prices imply.
    Organisation("market", r"(?!x)x",
                 r"market pricing|markets?\s+(?:are\s+|is\s+)?(?:now\s+|currently\s+)?pric\w*"
                 r"|market expectations|market[- ]implied"),
)  # fmt: skip

# Case matters: "US$96/b" is the United States, not "us".
SELF_REFERENCE = re.compile(r"\b(?:[Ww]e|[Oo]urs?|us)\b")
# Up to two words between the name and the forecasting word, but never a passive or infinitive.
_FILLER = r"(?:(?!(?:is|are|was|were|be|been|being|to)\b)[\w-]+\s+){0,2}"
_ACTIVE = (
    r"(?:forecasts?|projections?|estimates?|outlook|expects|projects|predicts|sees|anticipates"
    r"|(?:has\s+|have\s+)?(?:forecast|projected|predicted|estimated))\b"
)
_BEFORE = (
    r"(?:according\s+to|forecasts?\s+(?:by|from|of)|projections?\s+(?:by|from|of)|projected\s+by"
    r"|estimated\s+by|estimates?\s+(?:by|from)|sources?\s*:)\s+(?:the\s+)?"
)


# An issuer named as the market itself, for a claim that the market's wording may not block. A closed list: "Market Economics
# Ltd" and the "Financial Markets Authority" are not it. `organisation_of` keeps its existing answer for these names.
_MARKET_ISSUER = re.compile(
    r"^\s*(?:the\s+)?(?:financial\s+)?markets?(?:\s+participants)?\s*$", re.IGNORECASE
)
_REPORTED = (
    r"\s+(?:(?:said|says)\s+(?:that\s+)?(?:it|they)\s+)?expected(?!\s+(?:not\s+|never\s+)?to\b)\b"
)
# "Markets forecast growth" is the market's view; "market forecasts of 3%" and "markets expected to rise" are not.
_MARKET_EXPECTS = re.compile(
    r"\b(?:markets?|market\s+participants)\s+(?:(?:now|still)\s+)?"
    r"(?:expect(?:s\b|ed(?!\s+(?:not\s+|never\s+)?to\b)\b|\b)"
    r"|(?:forecasts?|forecasted|anticipates?|anticipated|predicts?|predicted|projects?|projected)"
    r"(?!\s+(?:of|for|from|that|to|is|are|was|were|by)\b)\b)",
    re.IGNORECASE,
)
# Words that may come directly before "markets expect". Anything else may be a sector: "the housing market expects".
_BEFORE_MARKET = {
    "the",
    "financial",
    "and",
    "but",
    "while",
    "that",
    "though",
    "although",
    "because",
    "since",
}
# A comparison up to this point, within one clause: "more than the RBNZ", "as both the RBNZ and the IMF". "As of June," is not.
_EXPECTED_BY = re.compile(r"\bexpected\s+by\s+", re.IGNORECASE)
_CLAUSE_END = re.compile(r"[,;:]")
_THE = re.compile(r"the\s+", re.IGNORECASE)
# Case-sensitive on purpose: "Market Economics Ltd" and the "Financial Markets Authority" are named organisations, not the market.
_MARKET_AGENT = re.compile(
    r"(?:the\s+)?(?:financial\s+)?markets?(?:\s+participants)?\b", re.IGNORECASE
)
_CAPITALISED_WORD = re.compile(r"\s+[A-Z][a-z]")
# An agent that is a proper name, not a date: "expected by Acme Research", never "expected by June".
_PROPER_AGENT = re.compile(
    r"(?:the\s+)?(?!(?:January|February|March|April|May|June|July|August|September|October|November|December"
    r"|Q[1-4]|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b)[A-Z]\w"
)
_WHICH = re.compile(r",\s*which\b", re.IGNORECASE)
_STAFF = re.compile(r"\b(?:staff|economists|officials)\s+expect\b", re.IGNORECASE)
_COMPARED_WITH = re.compile(
    r"\b(?:than|as(?!\s+of\b)|what|unlike|like)\s+(?:[^\s,;:]+\s+){0,5}$", re.IGNORECASE
)


def _compiled() -> dict[str, tuple[re.Pattern[str], re.Pattern[str]]]:
    out = {}
    for o in ORGANISATIONS:
        named = o.names + (f"|{o.publications}" if o.publications else "")
        credited = [rf"(?:{o.names})(?:['’]s)?\s+{_FILLER}{_ACTIVE}", rf"{_BEFORE}(?:{o.names})"]
        if o.publications:
            credited.append(o.publications)
        out[o.key] = (
            re.compile(named, re.IGNORECASE),
            re.compile("|".join(f"(?:{c})" for c in credited), re.IGNORECASE),
        )
    return out


_PATTERNS = _compiled()
_REPORTED_PATTERNS = {
    o.key: re.compile(rf"(?:{o.names}){_REPORTED}", re.IGNORECASE) for o in ORGANISATIONS
}


def organisation_of(name: str) -> str | None:
    """The known organisation an issuer name refers to, or None (an organisation this module does not know)."""
    for o in ORGANISATIONS:
        if _PATTERNS[o.key][0].search(name):
            return o.key
    return None


def named(text: str) -> set[str]:
    """Organisations whose name or publication appears in `text`."""
    return {key for key, (name, _) in _PATTERNS.items() if name.search(text)}


def credited(text: str) -> set[str]:
    """Organisations that `text` credits with a figure (see the module docstring)."""
    return {key for key, (_, credit) in _PATTERNS.items() if credit.search(text)}


def is_market_name(name: str) -> bool:
    return bool(_MARKET_ISSUER.match(name))


def _names_an_organisation(matched: str, rest: str) -> bool:
    """A title-case "Market" or "Markets" followed by another capitalised word is a name: "Market Economics Ltd"."""
    word = re.search(r"markets?\b", matched, re.IGNORECASE)
    token = matched[word.start() : word.end()] if word else ""
    return token[:1].isupper() and token[1:].islower() and bool(_CAPITALISED_WORD.match(rest))


def _agent_at(text: str, at: int) -> str | None:
    """The organisation whose name starts at `at`, with or without "the", if any."""
    market = _MARKET_AGENT.match(text, at)
    if market and not _names_an_organisation(market.group(), text[market.end() :]):
        return "market"
    the = _THE.match(text, at)
    starts = (at, the.end()) if the else (at,)
    return next(
        (
            key
            for start in starts
            for key, (name, _) in _PATTERNS.items()
            if name.match(text, start)
        ),
        None,
    )


def _expected_by(text: str) -> set[str]:
    """Organisations named as the agent of "expected by", outside a comparison."""
    agents = {
        _agent_at(text, m.end())
        for m in _EXPECTED_BY.finditer(text)
        if not _COMPARED_WITH.search(text[: m.start()])
    }
    return agents - {None}


def _unnamed_expected_by(text: str) -> bool:
    """Is a proper name that this module does not know the agent of "expected by", outside a comparison?"""
    return any(
        _agent_at(text, m.end()) is None
        and _PROPER_AGENT.match(text, m.end())
        and not _COMPARED_WITH.search(text[: m.start()])
        for m in _EXPECTED_BY.finditer(text)
    )


def reported(text: str) -> set[str]:
    """Organisations named as forecasters by reported wording. A comparison ("higher than the RBNZ expected") credits nobody."""
    text = re.sub(r"Reserve Bank of New Zealand", "Reserve Bank", text, flags=re.IGNORECASE)

    # "The RBNZ expected by the IMF to cut" is the IMF's view, so it counts for the IMF. "Expected by 2029" names no agent.
    def passive(m: re.Match[str]) -> bool:
        by = _EXPECTED_BY.match(text, m.end() - len("expected"))
        return by is not None and (
            _agent_at(text, by.end()) is not None or bool(_PROPER_AGENT.match(text, by.end()))
        )

    keys = {
        key
        for key, pattern in _REPORTED_PATTERNS.items()
        if any(
            not _COMPARED_WITH.search(text[: m.start()]) and not passive(m)
            for m in pattern.finditer(text)
        )
    }
    keys |= _expected_by(text)
    for m in _MARKET_EXPECTS.finditer(text):
        before = text[: m.start()]
        words = before.split()
        starts_clause = not words or words[-1][-1] in ",;:("
        if (
            not passive(m)
            and not _COMPARED_WITH.search(before)
            and (starts_clause or words[-1].lower() in _BEFORE_MARKET)
        ):
            keys.add("market")
    return keys


def since_author(before: str, author: str | None) -> str:
    """What `before` says after the author's last words, or all of it if the author says nothing."""
    last = [m.end() for m in SELF_REFERENCE.finditer(before)]
    if author in _PATTERNS:
        last += [m.end() for m in _PATTERNS[author][0].finditer(before)]
    return before[max(last, default=0) :]


def since_credit(before: str, who: str | None, author: str | None) -> str:
    """What `before` says after the last credit to `who`, the one the figure is credited to.

    An earlier forecaster's separate figure ("The RBNZ expected 2% but the IMF forecasts 3%") is not the credited
    forecaster's concern. For the author this is `since_author`.
    """
    if who in (None, "author"):
        return since_author(before, author)
    # Only wording that credits `who` ends the earlier forecaster's reach; a bare mention or a comparison does not.
    last = (
        [
            m.end()
            for m in _PATTERNS[who][1].finditer(before)
            if not _COMPARED_WITH.search(before[: m.start()])
        ]
        if who in _PATTERNS
        else []
    )
    return before[max(last, default=0) :]


def _credited_outside_comparison(text: str) -> set[str]:
    return {
        key
        for key, (_, credit) in _PATTERNS.items()
        if any(not _COMPARED_WITH.search(text[: m.start()]) for m in credit.finditer(text))
    }


# A figure with units. A bare year or count is not another assertion's figure.
_FIGURE = re.compile(
    r"\d[\d,.]*\s*(?:%|per\s?cent\b|percent\b|basis\s+points?\b|bps\b|b\b|bn\b|billion\b|million\b)|\$\s*\d[\d,]*(?:\.\d+)?",
    re.IGNORECASE,
)
# Only a contrast opens a new assertion. A bare "and" may coordinate figures under one credit, so it never ends one.
_NEXT_ASSERTION = re.compile(r";|,?\s*\b(?:while|whereas|but|then)\b", re.IGNORECASE)

# A relative clause ("…3% in 2029, which the IMF expects to be a challenging year") says something about its antecedent, and the
# antecedent need not be the figure: it may be the year, or a comparison benchmark. A credit in it belongs to the figure only when
# it could be the figure's own assertion. Two things show it is not, and both must be positive evidence, so any doubt still blocks:
# the clause's verb takes a complement that names no figure ("expects to be too optimistic"), or the clause states other figures
# and never the claimed one ("the IMF's forecast of 2%", "expects to be 2%").
_NAMES_ANY = "|".join(f"(?:{o.names})" for o in ORGANISATIONS if o.key != "market")
_ASSERTING_WORD = rf"(?:{_ACTIVE}|expected\b)"
_CREDIT_IN_CLAUSE = re.compile(
    rf"(?:the\s+)?(?:{_NAMES_ANY})(?:['’]s)?\s+{_FILLER}{_ASSERTING_WORD}(?P<rest>(?:[^,;:]|(?<=\d),(?=\d{{3}}\b))*)",
    re.IGNORECASE,
)
_COMPLEMENT = re.compile(
    r"\s*(?:to\s+(?:be|remain|prove|become|stay)|(?:will|would|should|could|might|may)\s+\w+)\b",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
_NUMBER_WORD = re.compile(
    r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|(?:thir|four|fif|six|seven|eight|nine)teen"
    r"|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|half|(?:a|an)\s+(?:hundred|thousand|million|billion))\b",
    re.IGNORECASE,
)
_YEAR = re.compile(r"(?:19|20)\d\d\Z")
# Straight after "which" the organisation is the one expecting, since "which" is what is expected: "which the IMF expected to be 3%"
# is the IMF's forecast, though "the RBNZ expected to cut" alone may be a passive.
_WHICH_EXPECTED = re.compile(
    rf"\s*(?:the\s+)?(?P<name>{_NAMES_ANY})\s+(?:(?:also|still|now)\s+)?expected\b", re.IGNORECASE
)


def _value(figure: str) -> float | None:
    number = _NUMBER.search(figure)
    try:
        return float(number.group().replace(",", "")) if number else None
    except ValueError:
        return None


def leading_figure(after: str) -> float | None:
    """The value of the figure `after` starts with (a sentence split at the figure), or None if it cannot be read."""
    m = _FIGURE.match(after)
    return _value(m.group()) if m else None


def _numbers(text: str) -> list[float | None]:
    """The numbers in `text` other than a bare year ("in 2029"), which dates a forecast but is no figure."""
    return [
        _value(m.group())
        for m in _NUMBER.finditer(text)
        if not (_YEAR.match(m.group()) and not _FIGURE.match(text, m.start()))
    ]


def _is_other_assertion(rest: str, figure: float | None) -> bool:
    """Does what a relative clause's forecaster says leave the claimed figure alone?

    Any number, or a number word, counts as a figure, whatever its unit: a figure that is not recognised must not look like none.
    """
    if _NUMBER_WORD.search(rest):
        return False  # "three per cent" cannot be compared with the claimed figure, so it blocks
    values = _numbers(rest)
    if values:
        return figure is not None and None not in values and figure not in values
    return _COMPLEMENT.match(rest) is not None


def without_other_assertions(text: str, figure: float | None) -> str:
    """`text` with the credits of a ", which" clause that are not about `figure` taken out (see above)."""
    which = _WHICH.search(text)
    if which is None:
        return text

    def drop(m: re.Match[str]) -> str:
        return " " if _is_other_assertion(m.group("rest"), figure) else m.group()

    return text[: which.end()] + _CREDIT_IN_CLAUSE.sub(drop, text[which.end() :])


def own_assertion(after: str) -> str:
    """What follows a figure, up to the next assertion that has a figure of its own.

    "…3% in 2029, while inflation will be 2%, which the IMF expects": the IMF belongs to the 2%.
    """
    for m in _NEXT_ASSERTION.finditer(after):
        if _FIGURE.search(after, m.end()):
            return after[: m.start()]
    return after


def third_parties_around(before: str, after: str, author: str | None) -> set[str]:
    """Third parties credited with a figure the author may be labelled with, given its sentence split at the figure.

    Credited since the author's last words before it, in a clause after it opening "which", or as the agent of "expected by" in
    its own clause after it. A name alone does not count, so
    "the RBNZ is expected to cut" stays beside the author's own forecast.
    """
    after = without_other_assertions(own_assertion(after), leading_figure(after))
    texts = [since_author(before, author)]
    which = _WHICH.search(after)
    if which is not None:
        texts.append(after[which.end() :])
    keys: set[str] = set()
    if which is not None and (agent := _WHICH_EXPECTED.match(after, which.end())):
        keys.add(organisation_of(agent.group("name")) or "other")
    for text in texts:
        if _unnamed_expected_by(text):
            keys.add("other")
        keys |= reported(text) | _credited_outside_comparison(
            _WHICH.sub(" ", _STAFF.sub("expects", text))
        )
    clause = _CLAUSE_END.split(after, maxsplit=1)[0]
    keys |= _expected_by(clause)
    if _unnamed_expected_by(clause):
        keys.add(
            "other"
        )  # someone else's forecast, though not one this module can name: never the author's
    return keys - {author}


# The author's own forecasting words, joined to the figure only by a short connective. No free word may sit between them.
_CONNECTIVE = r"(?:(?:of|at|to\s+be|that)\s+)?"
_OWN_FORECAST = re.compile(
    r"\b(?:we|our)\s+(?:(?:still|now|also|currently)\s+)?"
    r"(?:forecasts?|projections?|estimates?|expects?|projects?|anticipates?|predicts?|sees?)"
    rf"\s+{_CONNECTIVE}$",
    re.IGNORECASE,
)


_FORECAST_VERBS = (
    r"(?:forecasts?|projections?|estimates?|expects?|projects?|anticipates?|predicts?|sees?)"
)
_ADVERB = r"(?:(?:still|now|also|currently)\s+)?"
_OWN_WORDS = {
    o.key: re.compile(
        rf"\b(?:{o.names})(?:['’]s)?\s+{_ADVERB}{_FORECAST_VERBS}\s+{_CONNECTIVE}$", re.IGNORECASE
    )
    for o in ORGANISATIONS
    if o.key != "market"
}


def _author_speaks_just_before(before: str, author: str | None) -> bool:
    """The author's own forecasting words end `before`: "we forecast at", "the Treasury's forecast of". Nothing else counts."""
    if _OWN_FORECAST.search(before):
        return True
    return author in _OWN_WORDS and bool(_OWN_WORDS[author].search(before))


def author_governs(before: str, after: str, author: str | None) -> bool:
    """Is the figure the author's own, with the author's forecasting words directly before it and no third party after it?

    "The IMF expects 2%, less than we forecast at 3%": the figure is the author's even though that credit sits in a comparison.
    Nothing may stand between the author's words and the figure ("our rivals forecast at 3%", "unlike our forecast, growth of
    3%" do not qualify), and a third party's credit after the figure ("… 3% according to the IMF") ends it.
    """
    if not _author_speaks_just_before(before, author):
        return False
    own = without_other_assertions(own_assertion(after), leading_figure(after))
    trailing = _credited_outside_comparison(_WHICH.sub(" ", own)) | reported(own)
    return not trailing - {author}


def author_only_compared(text: str, author: str | None) -> bool:
    """Is every credit to the document's author inside a comparison, as in "more than we expected"?"""
    spans = [m.start() for m in SELF_REFERENCE.finditer(text)]
    if author in _PATTERNS:
        spans += [m.start() for m in _PATTERNS[author][1].finditer(text)]
    return bool(spans) and all(_COMPARED_WITH.search(text[:at]) for at in spans)


_DISPLAY = {"imf": "the IMF", "oecd": "the OECD", "world_bank": "the World Bank", "rba": "the RBA",
            "fed": "the Federal Reserve", "rbnz": "the RBNZ", "treasury": "the Treasury",
            "market": "market pricing"}  # fmt: skip


def display_name(key: str) -> str:
    return _DISPLAY.get(key, key.upper() if len(key) <= 4 else key.capitalize())
