"""Who made a forecast: the organisations a document names, and the wording that credits a figure to one (Phase 4I).

The checks are lexical, like the rest of the verifier. An organisation is *named* when its name or one of its
publications appears ("IMF", "World Economic Outlook"). A figure is *attributed* to it only by wording that makes
it the forecaster: a publication name, "the IMF expects/forecasts", "the MPC said it expected", "the IMF's forecast",
"according to the IMF", "Source: IMF". Naming an organisation as the subject of a forecast ("the RBNZ is expected to cut")
does not attribute the forecast to it. "We" and "our" are the document's author.
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


# The issuer named simply as the market: "Markets", "the market", "financial market participants".
_MARKET_ISSUER = re.compile(
    r"^\s*(?:the\s+)?(?:financial\s+)?markets?(?:\s+\w+)*\s*$", re.IGNORECASE
)
# A forecaster reported in the past tense, or the market's own view. Narrow on purpose: "the RBNZ rate cut expected in 2029"
# and "the RBNZ expected to cut" name a subject, and a comparison ("higher than the RBNZ expected") credits nobody.
_REPORTED = r"(?:['’]s)?\s+(?:(?:said|says)\s+(?:it|they)\s+)?expected(?!\s+to\b)\b"
_MARKET_EXPECTS = re.compile(r"\bmarkets?\s+expect(?:s|ed)?\b", re.IGNORECASE)
_COMPARED_WITH = re.compile(r"\b(?:than|as|what|unlike|like)\s+(?:\w+\s+){0,2}$", re.IGNORECASE)


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
_REPORTED_PATTERNS["market"] = _MARKET_EXPECTS


def organisation_of(name: str) -> str | None:
    """The known organisation an issuer name refers to, or None (an organisation this module does not know)."""
    if _MARKET_ISSUER.match(name):
        return "market"
    for o in ORGANISATIONS:
        if _PATTERNS[o.key][0].search(name):
            return o.key
    return None


def named(text: str) -> set[str]:
    """Organisations whose name or publication appears in `text`."""
    return {key for key, (name, _) in _PATTERNS.items() if name.search(text)}


def credited(text: str, *, reported: bool = True) -> set[str]:
    """Organisations that `text` credits with a figure (see the module docstring).

    `reported=False` leaves out the reported wording, for a sentence that a later figure would only inherit from.
    """
    keys = {key for key, (_, credit) in _PATTERNS.items() if credit.search(text)}
    if reported:
        keys |= {
            key
            for key, pattern in _REPORTED_PATTERNS.items()
            if any(not _COMPARED_WITH.search(text[: m.start()]) for m in pattern.finditer(text))
        }
    return keys


_DISPLAY = {"imf": "the IMF", "oecd": "the OECD", "world_bank": "the World Bank", "rba": "the RBA",
            "fed": "the Federal Reserve", "rbnz": "the RBNZ", "treasury": "the Treasury",
            "market": "market pricing"}  # fmt: skip


def display_name(key: str) -> str:
    return _DISPLAY.get(key, key.upper() if len(key) <= 4 else key.capitalize())
