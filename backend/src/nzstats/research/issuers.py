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
# Phase 4R: wording that makes a group of outside forecasters, or a reporter, the forecaster. It lives apart from `reported` on
# purpose: the verifier may only ADD a rejection with it. It never credits the author, and it never waives a block that the earlier
# wording raised (a third party's claim passes only on the strength of the older wording). "Economists", "staff" and "officials" are
# left out of the groups: a document's own economists can be its author, and wording cannot tell them from outsiders (`_STAFF`).
_GROUP_NOUN = (
    r"(?:(?:market|bank|private[- ]sector|independent|sell-side)\s+)?(?:analysts|forecasters)"
    r"|(?:market|bank|private[- ]sector)\s+economists"
    r"|investors|traders|commentators|banks|rating\s+agencies|survey\s+respondents"
)
_GROUP_MODIFIER = r"(?:(?:the|most|many|some|major|big|leading|local|domestic|australian|four)\s+)*"
_GROUP = rf"{_GROUP_MODIFIER}(?:{_GROUP_NOUN})"
_OTHER_PEOPLE = rf"(?:{_GROUP_NOUN}|economists|staff|officials)"
_OWN_PEOPLE = re.compile(
    rf"(?:['’]s)?\s*{_OTHER_PEOPLE}(?:\s*(?:,|and)\s*{_OTHER_PEOPLE})*\b", re.IGNORECASE
)
_AT_AN_ORGANISATION = r"(?:\s+(?:at|from)\s+(?:the\s+)?[A-Z][\w&]*(?:\s+[A-Z][\w&]*)*)?"
_GROUP_EXPECTS = re.compile(
    rf"\b{_GROUP}{_AT_AN_ORGANISATION}\s+(?:(?:now|still|also|currently|mostly)\s+)?"
    r"(?:expect(?:s\b|ed(?!\s+(?:not\s+|never\s+)?to\b)\b|\b)"
    r"|(?:are\s+|is\s+|have\s+|has\s+)?(?:expecting|forecasting|predicting|projecting|anticipating|estimating)\b"
    r"|(?:forecasts?|forecasted|anticipates?|anticipated|predicts?|predicted|projects?|projected|sees?|saw"
    r"|estimates?|estimated|reckons?|reckoned|says?|said)(?!\s+(?:of|for|from|to|is|are|was|were|by)\b)\b)",
    re.IGNORECASE,
)
_GROUP_ISSUER = re.compile(rf"^\s*(?:the\s+)?(?:{_GROUP_NOUN})\s*$", re.IGNORECASE)
_GROUP_PASSIVE = re.compile(
    rf"\b(?:expected|forecast|projected|predicted|anticipated|estimated)\s+by\s+{_GROUP}\b",
    re.IGNORECASE,
)
_ACCORDING_TO_GROUP = re.compile(
    rf"\baccording\s+to\s+(?:an?\s+(?:survey|range|poll)\s+of\s+)?{_GROUP}\b", re.IGNORECASE
)
_GROUP_IN_CLAUSE = re.compile(
    rf"\b{_GROUP}\s+(?:also\s+|still\s+)?(?:expect|forecast|predict|project|anticipate|see|estimate)\w*(?P<rest>[^,;:]*)",
    re.IGNORECASE,
)
# "The IMF said growth will be 3%": the reporter is the forecaster, though no forecasting verb follows its name.
_SAID = (
    r"(?:['’]s)?(?:\s+(?:staff|economists|officials|governor|managing\s+director))?"
    r"\s+(?:has\s+|have\s+)?(?:said|says|stated|states|noted|notes|warned|warns|suggested|suggests|believes?|thinks?|reckons?)\b"
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
# An agent that is a proper name, not a date: "expected by Acme Research", never "expected by June". Every date form must end where
# the date does: not inside a longer word ("Decker", "H2O") and not before a capitalised word that continues a name ("Mar Capital",
# "H2 Capital", "March Capital"). "Early", "Mid", "Late" and "End" are dates only before the year or month they qualify.
_MONTH = r"January|February|March|April|May|June|July|August|September|October|November|December"
_MONTH_ABBREVIATED = r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept?|Oct|Nov|Dec"
_WEEKDAY = r"Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday"
_ENDS_THE_DATE = r"(?!\w)(?!\.?\s*[A-Z])"
_DATE_WORD = (
    rf"(?:{_MONTH}|{_MONTH_ABBREVIATED}|{_WEEKDAY}|Q[1-4]|H[12]|(?:FY|CY)\s?\d{{2,4}}){_ENDS_THE_DATE}"
    rf"|(?:Early|Mid|Late|End)(?=[-\s]+(?:of\s+)?(?:\d|(?:{_MONTH})\b|Q[1-4]))"
)
_PROPER_AGENT = re.compile(rf"(?:the\s+)?(?!{_DATE_WORD})[A-Z]\w")
_WHICH = re.compile(r",\s*which\b", re.IGNORECASE)
_STAFF = re.compile(r"\b(?:staff|economists|officials)\s+expect\b", re.IGNORECASE)
_COMPARED_WITH = re.compile(
    r"\b(?:than|as(?!\s+of\b)|what|unlike|like|above|below|versus|vs\.?|compared\s+with|relative\s+to|exceeds?|exceeding)\s+(?:[^\s,;:]+\s+){0,5}$",
    re.IGNORECASE,
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


_SAID_PATTERNS = {
    o.key: re.compile(rf"(?:{o.names}){_SAID}", re.IGNORECASE)
    for o in ORGANISATIONS
    if o.key != "market"
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


def is_group_name(name: str) -> bool:
    """An issuer named as one of the closed list of outside groups ("Analysts"), which may be a third party's own label."""
    return bool(_GROUP_ISSUER.match(name))


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


_LEAD_IN = {
    "currently",
    "meanwhile",
    "now",
    "overall",
    "instead",
    "so",
    "yet",
    "also",
    "today",
    "however",
    "still",
    "then",
    "and",
}


def _since_author_and_people(before: str, author: str | None) -> str:
    """`since_author`, also past the author's own people: "our analysts and forecasters expect" is the author speaking."""
    last = [m.end() for m in SELF_REFERENCE.finditer(before)]
    if author in _PATTERNS:
        last += [m.end() for m in _PATTERNS[author][0].finditer(before)]
    start = max(last, default=0)
    people = _OWN_PEOPLE.match(before, start) if last else None
    return before[people.end() if people else start :]


def reported_more(text: str) -> set[str]:
    """Outside groups and reporters that `text` makes the forecaster, by the wording above. Rejection only: see the note there."""
    keys: set[str] = set()
    for m in _GROUP_EXPECTS.finditer(text):
        before = text[: m.start()]
        words = before.split()
        starts_clause = not words or words[-1][-1] in ",;:("
        if not _COMPARED_WITH.search(before) and (
            starts_clause or words[-1].lower() in _BEFORE_MARKET | _LEAD_IN
        ):
            keys.add("group")
    for pattern in (_GROUP_PASSIVE, _ACCORDING_TO_GROUP):
        if any(not _COMPARED_WITH.search(text[: m.start()]) for m in pattern.finditer(text)):
            keys.add("group")
    keys |= {
        key
        for key, pattern in _SAID_PATTERNS.items()
        if any(not _COMPARED_WITH.search(text[: m.start()]) for m in pattern.finditer(text))
    }
    return keys


def more_around(before: str, after: str, who: str | None, author: str | None) -> set[str]:
    """`reported_more` for the wording that leads to a figure (since the credited forecaster's last words) and its own "which" clause.

    A "which" clause that only comments on the year or the forecast ("which analysts expect to be a testing year") credits nobody.
    """
    lead = (
        _since_author_and_people(before, author)
        if who in (None, "author")
        else since_credit(before, who, author)
    )
    keys = reported_more(lead)
    after = own_assertion(after)
    # After the figure only the passive and "according to" forms can name who made it.
    if any(p.search(after) for p in (_GROUP_PASSIVE, _ACCORDING_TO_GROUP)):
        keys.add("group")
    which = _WHICH.search(after)
    if which is not None:
        clause = _GROUP_IN_CLAUSE.sub(
            lambda m: " " if _COMMENT.match(m.group("rest")) else m.group(), after[which.end() :]
        )
        keys |= reported_more(clause)
    return keys - {author}


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
    r"\d[\d,.]*\s*(?:%|per\s?cent\b|percent\b|basis\s+points?\b|bps\b|b\b|bn\b|billion\b|million\b)|\$\s*\d",
    re.IGNORECASE,
)
# Only a contrast opens a new assertion. A bare "and" may coordinate figures under one credit, so it never ends one.
_NEXT_ASSERTION = re.compile(r";|,?\s*\b(?:while|whereas|but|then)\b", re.IGNORECASE)

# A relative clause ("…3% in 2029, which the IMF expects to be a challenging year") says something about its antecedent, and the
# antecedent need not be the figure: it may be the year. A credit in it belongs to the figure unless the clause is positively a
# comment, and a comment is a closed list: on the horizon ("to be a challenging year") or on the forecast ("to be too optimistic"),
# and nothing more. Anything else keeps the credit, however it is worded: "to remain unchanged for 2 years", "to be the same this
# year" and "to be 2%" all forecast something this module cannot tell from the figure. No number is read to decide it. Telling
# a forecast value from a duration, a year, a count or a spelled-out number is where earlier versions kept leaking, both ways.
_NAMES_ANY = "|".join(f"(?:{o.names})" for o in ORGANISATIONS if o.key != "market")
_ASSERTING_WORD = rf"(?:{_ACTIVE}|expected\b)"
_CREDIT_IN_CLAUSE = re.compile(
    rf"(?:the\s+)?(?:{_NAMES_ANY})(?:['’]s)?\s+{_FILLER}{_ASSERTING_WORD}(?P<rest>[^,;:]*)",
    re.IGNORECASE,
)
_ADJECTIVE = (
    r"(?:optimistic|pessimistic|ambitious|conservative|cautious|generous|modest|challenging|difficult|tough|uncertain"
    r"|volatile|risky|demanding|testing|turbulent)"
)
_INTENSIFIER = r"(?:(?:too|very|rather|quite|fairly|somewhat|overly|extremely|particularly)\s+)?"
_COMMENT_ON_YEAR = rf"(?:an?|the)\s+{_INTENSIFIER}{_ADJECTIVE}(?:\s+and\s+{_ADJECTIVE})?\s+(?:year|period|quarter|time|test)"
_COMMENT = re.compile(
    r"\s*(?:to|will|would|should|could|might|may)\s+(?:be|prove)\s+"
    rf"{_INTENSIFIER}(?:{_COMMENT_ON_YEAR}|{_ADJECTIVE})"
    r"(?:\s+(?:in\s+(?:19|20)\d\d|ahead|overall))?[.!?)\s]*\Z",
    re.IGNORECASE,
)
# Straight after "which" the organisation is the one expecting, since "which" is what is expected: "which the IMF expected to be 3%"
# is the IMF's forecast, though "the RBNZ expected to cut" alone may be a passive.
_WHICH_EXPECTED = re.compile(
    rf"\s*(?:the\s+)?(?P<name>{_NAMES_ANY})\s+(?:(?:also|still|now)\s+)?expected\b", re.IGNORECASE
)


def without_commentary(text: str) -> str:
    """`text` with the credits of a ", which" clause that only comment on the year or the forecast taken out (see above)."""
    which = _WHICH.search(text)
    if which is None:
        return text

    def drop(m: re.Match[str]) -> str:
        return " " if _COMMENT.match(m.group("rest")) else m.group()

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
    after = without_commentary(own_assertion(after))
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
    own = without_commentary(own_assertion(after))
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
            "market": "market pricing", "group": "a group of outside forecasters"}  # fmt: skip


def display_name(key: str) -> str:
    return _DISPLAY.get(key, key.upper() if len(key) <= 4 else key.capitalize())
