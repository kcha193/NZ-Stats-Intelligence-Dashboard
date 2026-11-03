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
_REPORTED = r"\s+(?:(?:said|says)\s+(?:that\s+)?(?:it|they)\s+)?expected(?!\s+to\b)\b"
# "Markets forecast growth" is the market's view; "market forecasts of 3%" and "markets expected to rise" are not.
_MARKET_EXPECTS = re.compile(
    r"\b(?:markets?|market\s+participants)\s+(?:(?:now|still)\s+)?"
    r"(?:expect(?:s\b|ed(?!\s+to\b)\b|\b)"
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
_MARKET_AGENT = re.compile(
    r"(?:the\s+)?(?:financial\s+)?markets?(?:\s+participants)?\b", re.IGNORECASE
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


def _agent_at(text: str, at: int) -> str | None:
    """The organisation whose name starts at `at`, with or without "the", if any."""
    if _MARKET_AGENT.match(text, at):
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


def reported(text: str) -> set[str]:
    """Organisations named as forecasters by reported wording. A comparison ("higher than the RBNZ expected") credits nobody."""
    text = re.sub(r"Reserve Bank of New Zealand", "Reserve Bank", text, flags=re.IGNORECASE)

    # "The RBNZ expected by the IMF to cut" is the IMF's view, so it counts for the IMF. "Expected by 2029" names no agent.
    def passive(m: re.Match[str]) -> bool:
        by = _EXPECTED_BY.match(text, m.end() - len("expected"))
        return by is not None and _agent_at(text, by.end()) is not None

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
    """What `before` says after the last words of `who`, the one the figure is credited to.

    An earlier forecaster's separate figure ("The RBNZ expected 2% but the IMF forecasts 3%") is not the credited
    forecaster's concern. For the author this is `since_author`.
    """
    if who in (None, "author"):
        return since_author(before, author)
    last = [m.end() for m in _PATTERNS[who][0].finditer(before)] if who in _PATTERNS else []
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
_NEXT_ASSERTION = re.compile(r";|,?\s*\b(?:while|whereas|but|and|then)\b", re.IGNORECASE)


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
    after = own_assertion(after)
    texts = [since_author(before, author)]
    which = _WHICH.search(after)
    if which is not None:
        texts.append(after[which.end() :])
    keys: set[str] = set()
    for text in texts:
        keys |= reported(text) | _credited_outside_comparison(
            _WHICH.sub(" ", _STAFF.sub("expects", text))
        )
    keys |= _expected_by(_CLAUSE_END.split(after, maxsplit=1)[0])
    return keys - {author}


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
