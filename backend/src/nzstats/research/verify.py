"""Deterministic verification of a model's summary against the stored document text.

Every rule is a fixed, explainable test on the cited text: verbatim quotes, numbers, units, horizons,
period basis, versions, pages, forward-looking language and scenario wording. From verify-3 (Phase 4I)
also: who issued a forecast, where a number sits on the page (a sentence, a table cell under a column
heading, or chart-axis residue), monetary policy decisions (rate, date, vote), reported facts and the
statistical definition the document gives them, forward guidance and assumptions. An *error* blocks
approval; a *warning* is shown to the reviewer. The checks are lexical. Passing them means nothing
contradicted the evidence that these rules can see; it is not a judgement of economic accuracy,
completeness or interpretation, which stays with the human reviewer (`SCOPE` says so wherever a
result is shown).
"""

from __future__ import annotations

import re
from bisect import bisect_right
from calendar import monthrange
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from functools import cached_property
from typing import Any, Literal

from nzstats.research import issuers
from nzstats.research.contract import (
    Adjustment,
    Assumption,
    EvidenceRef,
    ForecastClaim,
    Guidance,
    Indicator,
    IssuerRole,
    OutlookSummary,
    PolicyAction,
    PolicyDecision,
    ReportedFact,
    SectionText,
    Statement,
)
from nzstats.research.prompt import INJECTION_PATTERN

VERIFIER_VERSION = "verify-3"
SCOPE = (
    "Deterministic evidence checks only: quotes, numbers, units, horizons, versions and pages were"
    " matched against the stored text. This is not a check of economic accuracy, completeness or"
    " interpretation; a reviewer must read the cited evidence."
)
UNITS = frozenset({"percent", "percentage_points", "basis_points", "percent_of_gdp", "nzd",
                   "nzd_million", "nzd_billion", "index", "persons", "ratio"})  # fmt: skip

_NUM = re.compile(r"(?<![\w.])(?P<sign>[-−])?(?P<int>\d+(?:,\d{3})*(?:\.\d+)?)?(?P<frac>[½¼¾])?")
# PDF extraction can leave a minus sign at the end of one line and its number at the start of the next.
_SPLIT_SIGN = re.compile(
    r"(?<!\S)([-−])[ \t]*(?:\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029])\s*(?=\d)"
)
_SPACED_SIGN = re.compile(r"(?<!\S)([-−]) (?=\d)")  # how a quote may render that line break
# Table cells: numbers, or the placeholders tables use for an empty cell.
_NUMBER_CELL = re.compile(r"[-−]?\d+(?:,\d{3})*(?:\.\d+)?%?")
_EMPTY_CELL = re.compile(r"[-−–—]{1,2}|n/?a|\.\.|…", re.IGNORECASE)
_YEAR_CELL = re.compile(r"(?:19|20)\d{2}(?:[/–-]\d{2})?[a-z*]?", re.IGNORECASE)
_TITLED = re.compile(r"^(?:table|figure|chart|graph|exhibit)\s+[\w.]+\s*[:.–-]", re.IGNORECASE)
_SOURCE_LINE = re.compile(r"^sources?\b", re.IGNORECASE)
_PERCENT_WORD = re.compile(r"%|per\s*cent|percent", re.IGNORECASE)
_SHARE_OF_GDP = re.compile(
    r"(?:%|per\s*cent|percent)\s+of\s+(?:nominal\s+)?gdp|\bto[-\s]+gdp\b", re.I
)
_POINTS = {
    "percentage_points": re.compile(r"percentage\s+points?|\bppts?\b|\bpp\b", re.IGNORECASE),
    "basis_points": re.compile(r"basis\s+points?|\bbps?\b", re.IGNORECASE),
}
# A monetary policy decision: what was decided, as opposed to what is expected.
_DECISION = re.compile(
    r"\b(?:agreed|decided|resolved|voted)\s+to\b|\bvoted\b"
    r"|\b(?:held|kept|left|maintained|cut|lowered|reduced|raised|increased|hiked)\s+(?:the\s+)?"
    r"(?:ocr|official\s+cash\s+rate|cash\s+rate|policy\s+rate)\b"
    r"|\b(?:ocr|official\s+cash\s+rate|cash\s+rate|policy\s+rate)\s+(?:was\s+|has\s+been\s+|is\s+)?"
    r"(?:held|kept|left|unchanged|cut|lowered|raised|increased|reduced)\b",
    re.IGNORECASE,
)
_ACTIONS = {
    PolicyAction.HOLD: re.compile(
        r"\b(?:hold|holds|held|unchanged|kept|keep|left|leave|maintain\w*|steady)\b", re.I),
    PolicyAction.INCREASE: re.compile(r"\b(?:rais\w*|increas\w*|hik\w*|tighten\w*)", re.I),
    PolicyAction.DECREASE: re.compile(r"\b(?:cut|cuts|cutting|lower\w*|reduc\w*|decreas\w*)", re.I),
}  # fmt: skip
_COUNT = r"(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)"
_COUNT_WORDS = {w: i for i, w in enumerate(
    "one two three four five six seven eight nine ten".split(), start=1)}  # fmt: skip
_VOTE_WORD = re.compile(
    r"\bvot(?:e|ed|es|ing)\b|\bmajority\b|\bpreferred\b|\bfavoured\b|\bdissent", re.I
)
_VOTE_PAIR = re.compile(rf"\b{_COUNT}\s*(?:[–—-]|\bto\b)\s*{_COUNT}\b", re.IGNORECASE)
_MEMBERS = re.compile(rf"\b{_COUNT}\s+(?:[a-z]+\s+)?members?\b", re.IGNORECASE)
# Survey respondents' expectations reported as a result ("a net 40% of respondents expected …") are an outturn.
_SURVEY_EXPECTATION = re.compile(
    r"\b(?:respondents|firms|businesses|households|consumers)\b[^.;]{0,60}?\bexpect", re.IGNORECASE
)
_CONDITIONAL = re.compile(
    r"\b(?:if|unless|provided|conditional|depend\w*|would|could|may|might)\b", re.IGNORECASE
)
_ADJUSTMENT = {
    Adjustment.SEASONALLY_ADJUSTED: re.compile(
        r"(?<!not )(?<!non-)seasonally[- ]adjusted|\bs\.a\.(?!\w)|\(sa\)", re.I),
    Adjustment.UNADJUSTED: re.compile(
        r"\bunadjusted\b|not seasonally adjusted|non-seasonally adjusted|\bnsa\b|actual (?:basis|terms)", re.I),
    Adjustment.TREND: re.compile(r"\btrend\b", re.IGNORECASE),
}  # fmt: skip
_FRACTIONS = {"½": 0.5, "¼": 0.25, "¾": 0.75}
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_CLAUSE = re.compile(r";|,\s*(?:and|but|while|whereas|then)\b")
_FORWARD = re.compile(
    r"forecast|expect|project|predict|anticipat|outlook|assum|\bwill\b|\bwould\b|\bshould\b"
    r"|\blikely\b|\bsees?\b|\bseen\b|pencil|\bplan|scenario|\bpath\b|\bestimated? to\b"
    r"|\bto (?:rise|fall|grow|increase|decrease|decline|ease|peak|reach|remain|average|be|slow"
    r"|pick up|recover|contract|improve|edge|lift)\b",
    re.IGNORECASE,
)
# Past-tense or outturn wording: a heading's forecast context must not turn these into forecasts.
_HISTORICAL = re.compile(
    r"\b(?:was|were|had|rose|fell|grew|dropped|climbed|declined|increased|decreased|contracted"
    r"|recorded|reached|averaged|totall?ed|stood|came in|reported|actual|outturn|provisional)\b",
    re.IGNORECASE,
)
_SCENARIO = re.compile(
    r"scenario|alternative (?:path|projection|forecast)|sensitivity|illustrative|stress test",
    re.IGNORECASE,
)
# "baseline scenario" / "central scenario" name the central forecast, not an alternative path.
_BASELINE_QUALIFIER = re.compile(
    r"(?<!non )(?<![-\w])(?:baseline|central|base|main|reference)\s+$", re.IGNORECASE
)
# "fall to 2.25%" gives a level; only "fall by 0.4%" / "contract 0.4%" is a negative change.
_LEVEL_AFTER_TO = re.compile(
    r"\bto\s+(?:about\s+|around\s+|roughly\s+|approximately\s+|nearly\s+|just\s+(?:under|over)\s+)?\$?$",
    re.IGNORECASE,
)
# A share of GDP stated before the number: "debt-to-GDP ratio of 43.1%", "net debt to GDP is 43.1%".
# "contribution to GDP growth" is a growth rate, not a share.
_GDP_RATIO_BEFORE = re.compile(
    r"(?:\bto[-\s]+|/\s*|\b(?:share|percentage|proportion)\s+of\s+)(?:nominal\s+)?gdp\b"
    r"(?!\s+(?:growth|per\s+capita|deflator))",
    re.IGNORECASE,
)
# Spaced hyphens are checked for consecutive years by _fiscal_text. Line boundaries are retained when checking
# evidence so a following chart-axis label cannot become part of a fiscal-year pair.
_YEAR_PAIR = r"\b(?:19|20)\d{2}[ \t]*[/–-][ \t]*\d{2}\b"
_FISCAL = re.compile(
    r"fiscal|financial year|june\s+(?:20\d{2}\s+)?year|year\s+(?:to|ending|ended)\s+june"
    rf"|{_YEAR_PAIR}|\bfy\s*\d",
    re.IGNORECASE,
)
_CALENDAR = re.compile(
    r"calendar|december\s+(?:20\d{2}\s+)?year|year\s+(?:to|ending|ended)\s+december", re.IGNORECASE
)
_ANNUAL = re.compile(
    r"annual|year[- ]on[- ]year|\by/y\b|\byoy\b|\byear\s+(?:to|ending|ended)\b|\bper year\b"
    r"|\b(?:march|june|september|december)\s+(?:20\d{2}\s+)?year\b|calendar|" + _YEAR_PAIR,
    re.IGNORECASE,
)
_QUARTERLY = re.compile(r"\bquarter(?:ly)?\b|\bq/q\b|\bqoq\b|\bq[1-4]\b", re.IGNORECASE)
# A quarter named as the reference period ("the December quarter", "June 2027 quarter", "Q4"), not a change basis.
_QUARTER_PERIOD = re.compile(
    r"\b(?:march|june|september|december)\s+(?:(?:19|20)\d{2}\s+)?quarter\b|\bq[1-4]\b",
    re.IGNORECASE,
)
_UP = re.compile(
    r"\b(?:ris|rose|increas|grow|grew|higher|climb|accelerat|lift|strengthen|pick(?:s|ed)? up|hike"
    r"|peak|improv|recover)", re.IGNORECASE)  # fmt: skip
_DOWN = re.compile(
    r"\b(?:fall|fell|declin|decreas|lower|eas(?:e|es|ed|ing)\b|cut|contract|weaken|slow|drop|reduc"
    r"|deteriorat)", re.IGNORECASE)  # fmt: skip
_FLAT = re.compile(r"\b(?:steady|unchanged|flat|stable|hold|remain)", re.IGNORECASE)
_EARLIER_BEFORE = re.compile(
    r"(?:\b(?:down|up|revised|lowered|raised|cut|increased|changed)\s+from|\bpreviously"
    r"|\b(?:previous|prior|earlier|last)\s+(?:forecast|projection|estimate)\s+(?:of|was))\s*\(?\s*$",
    re.IGNORECASE,
)
_EARLIER_AFTER = re.compile(
    r"^\s*(?:%|per\s*cent|percent)?\s*\)?\s*,?\s*(?:previously|in (?:our|the) (?:previous|prior|last|earlier))",
    re.IGNORECASE,
)
_CERTAIN = re.compile(
    r"\b(?:certain(?:ly)?|definitely|guarantee[ds]?|inevitabl[ey]|undoubtedly|no doubt)\b", re.I
)
_YEAR = re.compile(r"\b((?:19|20)\d{2})(?:\s*[/–-]\s*(\d{2}))?\b")
_MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september",
           "october", "november", "december")  # fmt: skip
_MONTH = re.compile(r"\b(" + "|".join(m[:3] for m in _MONTHS) + r")[a-z]*\b", re.IGNORECASE)
_QUARTER_LABEL = re.compile(r"\bq([1-4])\b", re.IGNORECASE)
_WORD = re.compile(r"[a-z]+")
_STOP = frozenset(
    "this that with from have will been were their there which would could should into over than"
    " then also more most some such they them these those about after before while year years"
    " expected expect forecast forecasts outlook document report says said".split()
)
_UNIT_SUFFIX = {
    "percentage_points": re.compile(r"^\s*(?:percentage\s+points?|ppts?\b|pp\b|%\s*(?:pts?|points?)\b)", re.I),
    "basis_points": re.compile(r"^\s*(?:basis\s+points?|bps?\b)", re.I),
    "percent": re.compile(r"^\s*(?:%|per\s*cent|percent|pc\b)", re.I),
    "nzd_billion": re.compile(r"^\s*(?:billion|bn\b|b\b)", re.I),
    "nzd_million": re.compile(r"^\s*(?:million|mn?\b)", re.I),
}  # fmt: skip
_OF_GDP = re.compile(r"^\s*(?:%|per\s*cent|percent)\s+of\s+(?:nominal\s+)?gdp", re.IGNORECASE)
_DOLLAR_PREFIX = re.compile(r"(?:\$|nzd\s?|nz\$)\s?$", re.IGNORECASE)
# A scale word or abbreviation straight after a dollar amount: plain NZD must not match these.
_MONEY_SCALE = re.compile(
    r"^\s*(?:thousand|k\b|million|mn?\b|billion|bn\b|b\b|trillion|tn\b|t\b)", re.IGNORECASE
)
_INDICATOR_WORDS: dict[Indicator, re.Pattern[str]] = {
    Indicator.GDP: re.compile(r"\bgdp\b|gross domestic|economic growth|\beconomy\b|\boutput\b", re.I),
    Indicator.CPI_INFLATION: re.compile(r"\bcpi\b|inflation|consumers?\s+price", re.I),
    Indicator.UNEMPLOYMENT: re.compile(r"unemploy|jobless", re.I),
    Indicator.EMPLOYMENT: re.compile(r"(?<!un)employ|\bjobs?\b", re.I),
    Indicator.WAGES: re.compile(r"\bwage|earnings|labour cost|salar", re.I),
    Indicator.OCR: re.compile(r"\bocr\b|official cash rate|\bcash rate|policy rate", re.I),
    Indicator.INTEREST_RATES: re.compile(
        r"interest rate|mortgage rate|bond yield|\byields?\b|swap rate|lending rate|deposit rate", re.I),
    Indicator.HOUSE_PRICES: re.compile(r"house price|housing|dwelling|property price|home price", re.I),
    Indicator.EXCHANGE_RATE: re.compile(r"exchange rate|\bnzd\b|kiwi dollar|\btwi\b|trade[- ]weighted", re.I),
    Indicator.FISCAL_BALANCE: re.compile(
        r"fiscal balance|obegal|surplus|deficit|operating balance|budget balance", re.I),
    Indicator.GOVERNMENT_DEBT: re.compile(r"\bdebt\b", re.I),
    Indicator.MIGRATION: re.compile(r"migra|arrivals|departures", re.I),
    Indicator.TRADE: re.compile(r"export|import|current account|terms of trade|trade balance", re.I),
}  # fmt: skip

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class Problem:
    code: str
    path: str
    message: str
    severity: Severity = "error"

    def to_json(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


@dataclass(frozen=True)
class VerificationContext:
    published_on: date | None = None  # the publication's own date, for the historical check
    injection_ordinals: tuple[int, ...] = ()  # sections that read like instructions to a model
    institution: str | None = None  # the document's institution (registry key), for issuer checks


@dataclass(frozen=True)
class VerificationReport:
    errors: tuple[Problem, ...]
    warnings: tuple[Problem, ...]
    scope: str = SCOPE
    version: str = VERIFIER_VERSION

    @property
    def passed(self) -> bool:
        return not self.errors

    def to_json(self) -> dict[str, Any]:
        return {"version": self.version, "passed": self.passed, "scope": self.scope,
                "errors": [p.to_json() for p in self.errors],
                "warnings": [p.to_json() for p in self.warnings]}  # fmt: skip


@dataclass(frozen=True)
class _Row:
    label: str  # the words before the cells ("Treasury (PEU)"); empty on a line of numbers only
    cells: tuple[tuple[str, int, int], ...]  # each cell and its span in the normalised text


@dataclass(frozen=True)
class _Table:
    years: (
        tuple[str, ...] | None
    )  # the row of years heading the cells, one per cell; None if none matches
    caption: str  # the nearest titled caption above the table and its source lines ("" if none)
    context: str  # caption, header fragments and labels after the rows: where the unit is stated


class _Layout:
    """A section's normalised text with its source lines kept, so table rows and loose numbers can be seen.

    `text` is exactly `_norm` of the section. Lines are classified as a row of years (a table header), a table
    row (a label and at least three cells, or two under a matching header), a line of numbers only, or text.
    Numbers-only lines that run three
    or more deep, or hold three or more numbers, are residue: chart-axis labels or a row without its label.
    """

    def __init__(self, raw: str) -> None:
        pieces: list[str] = []
        spans: list[tuple[int, int]] = []
        pos = 0
        for line in _join_split_signs(raw).splitlines():
            words = line.split()
            if not words:
                continue
            if pieces:
                pos += 1
            joined = " ".join(words)
            spans.append((pos, pos + len(joined)))
            pieces.append(joined)
            pos += len(joined)
        self.text = " ".join(pieces)
        self.lines = tuple(spans)
        self._starts = [a for a, _ in spans]

    def line_text(self, i: int) -> str:
        a, b = self.lines[i]
        return self.text[a:b]

    def line_at(self, offset: int) -> int:
        return bisect_right(self._starts, offset) - 1

    @cached_property
    def kinds(self) -> tuple[tuple[str, _Row | None, tuple[str, ...] | None], ...]:
        out: list[tuple[str, _Row | None, tuple[str, ...] | None]] = []
        for line_index, (a, b) in enumerate(self.lines):
            tokens = [
                (m.group(), a + m.start(), a + m.end()) for m in re.finditer(r"\S+", self.text[a:b])
            ]
            if len(tokens) >= 2 and all(_YEAR_CELL.fullmatch(t) for t, _, _ in tokens):
                out.append(("header", None, tuple(t for t, _, _ in tokens)))
                continue
            k = len(tokens)
            while k and (
                _NUMBER_CELL.fullmatch(tokens[k - 1][0]) or _EMPTY_CELL.fullmatch(tokens[k - 1][0])
            ):
                k -= 1
            cells = tuple(tokens[k:])
            numbers = sum(bool(_NUMBER_CELL.fullmatch(t)) for t, _, _ in cells)
            if k == 0 and numbers:
                out.append(("numbers", _Row("", cells), None))
            elif numbers >= 2 and (
                len(cells) >= 3
                or (
                    len(cells) == 2
                    and line_index > 0
                    and (
                        (
                            out[line_index - 1][0] == "header"
                            and len(out[line_index - 1][2] or ()) == 2
                        )
                        or (
                            out[line_index - 1][0] == "row"
                            and len(out[line_index - 1][1].cells) == 2
                        )
                    )
                )
            ):
                out.append(("row", _Row(self.text[tokens[0][1] : tokens[k - 1][2]], cells), None))
            else:
                out.append(("text", None, None))
        return tuple(out)

    @cached_property
    def residue(self) -> frozenset[int]:
        kinds, out, i = self.kinds, set(), 0
        while i < len(kinds):
            j = i
            while j < len(kinds) and kinds[j][0] == "numbers":
                j += 1
            run = range(i, j)
            if len(run) >= 3:
                out.update(run)
            else:
                out.update(
                    n
                    for n in run
                    if sum(bool(_NUMBER_CELL.fullmatch(c)) for c, _, _ in kinds[n][1].cells) >= 3
                )
            i = max(j, i + 1)
        return frozenset(out)

    def place(self, offset: int) -> tuple[str, int]:
        """("residue" | "cell" | "text", line index) for a number starting at `offset`."""
        i = self.line_at(offset)
        if i < 0:
            return "text", i
        if i in self.residue:
            return "residue", i
        kind, row, _ = self.kinds[i]
        if kind == "row" and row is not None and any(a <= offset < b for _, a, b in row.cells):
            return "cell", i
        return "text", i

    def row(self, i: int) -> _Row:
        row = self.kinds[i][1]
        assert row is not None
        return row

    def cell_index(self, i: int, offset: int) -> int:
        return next(n for n, (_, a, b) in enumerate(self.row(i).cells) if a <= offset < b)

    def table(self, i: int) -> _Table:
        kinds, width = self.kinds, len(self.row(i).cells)

        def same(j: int) -> bool:
            row = kinds[j][1]
            return kinds[j][0] == "row" and row is not None and len(row.cells) == width

        top = i
        while top > 0 and same(top - 1):
            top -= 1
        years = None
        header = kinds[top - 1] if top > 0 else None
        if header is not None and header[0] == "header" and header[2] and len(header[2]) == width:
            years, top = header[2], top - 1
        bottom = i
        while bottom + 1 < len(kinds) and same(bottom + 1):
            bottom += 1
        fragments: list[int] = []  # lines between the table and its titled caption, nearest first
        caption: list[str] = []
        for j in range(top - 1, max(top - 21, -1), -1):
            if j in self.residue:
                continue
            if _TITLED.match(self.line_text(j)):
                caption = [self.line_text(j)]
                break
            fragments.append(j)
        fragments = fragments[:5]
        after = [n for n in range(bottom + 1, min(bottom + 4, len(kinds))) if kinds[n][0] == "text"]
        caption += [
            self.line_text(n)
            for n in sorted(fragments) + after
            if _SOURCE_LINE.match(self.line_text(n))
        ]
        context = " ".join(caption + [self.line_text(n) for n in sorted(fragments) + after])
        return _Table(years, " ".join(caption), context)


@dataclass(frozen=True)
class _Located:
    """A quote found in its section: the sentences around it, for checks that need context."""

    text: str  # the normalised section text
    start: int  # quote offset in `text`
    end: int
    sentences: tuple[tuple[int, int], ...]
    first: int  # indices into `sentences` covering the quote
    last: int
    heading: str
    quote: str  # the quote as matched in `text` (normalised)
    layout: _Layout

    def sentence_text(self) -> str:
        a, b = self.sentences[self.first][0], self.sentences[self.last][1]
        return self.text[a:b]

    def previous_sentence(self) -> str:
        return self.text[slice(*self.sentences[self.first - 1])] if self.first else ""

    def near_text(self) -> str:
        lo, hi = max(self.first - 1, 0), min(self.last + 1, len(self.sentences) - 1)
        return f"{self.heading} {self.text[self.sentences[lo][0] : self.sentences[hi][1]]}"

    def with_lines(self, start: int, end: int) -> str:
        """Keep line breaks where a year and a chart label must not form a fiscal pair."""
        text = self.text[start:end]
        for _, line_end in reversed(self.layout.lines):
            if start <= line_end < end and self.text[line_end : line_end + 1] == " ":
                pos = line_end - start
                text = text[:pos] + "\n" + text[pos + 1 :]
        return text

    def _clause_span(self, offset: int) -> tuple[int, int]:
        a, b = self.sentences[self.first][0], self.sentences[self.last][1]
        start = a
        for sep in _CLAUSE.finditer(self.text[a:b]):
            end = a + sep.start()
            if offset < end:
                return start, end
            start = a + sep.end()
        return start, b

    def clause_at(self, offset: int) -> str:
        """The clause of the quote's sentence that contains `offset` (section coordinates)."""
        return self.text[slice(*self._clause_span(offset))]

    def lead_to(self, offset: int) -> str:
        """The text of `offset`'s clause up to `offset`: what the section says before a number."""
        return self.text[self._clause_span(offset)[0] : offset]


def _join_split_signs(text: str) -> str:
    """ "-\n7%" is -7%: a sign left alone at a line end belongs to the number that starts the next line."""
    return _SPLIT_SIGN.sub(r"\1", text)


def _norm(text: str) -> str:
    return " ".join(_join_split_signs(text).split())


def _number_spans(text: str) -> list[tuple[float, int, int]]:
    out = []
    for m in _NUM.finditer(text):
        whole, frac = m.group("int"), m.group("frac")
        if whole is None and frac is None:
            continue
        value = float(whole.replace(",", "")) if whole else 0.0
        value += _FRACTIONS.get(frac or "", 0.0)
        out.append((-value if m.group("sign") else value, m.start(), m.end()))
    return out


def _alternative_scenario(text: str) -> bool:
    """Whether `text` names a scenario other than one introduced as the baseline or central one."""
    return any(
        not _BASELINE_QUALIFIER.search(text[max(m.start() - 25, 0) : m.start()])
        for m in _SCENARIO.finditer(text)
    )


def _numbers(text: str) -> set[float]:
    return {v for v, _, _ in _number_spans(text)}


def _same(a: float, b: float) -> bool:
    return abs(a - b) < 1e-9


def _value_spans(value: float, quote: str) -> list[tuple[int, int]]:
    """Where `value` is stated in the quote; a negative value may be an unsigned number + decline word."""
    spans = [(s, e) for v, s, e in _number_spans(quote) if _same(v, value)]
    if not spans and value < 0 and _DOWN.search(quote):
        spans = [
            (s, e)
            for v, s, e in _number_spans(quote)
            if _same(v, -value) and not _LEVEL_AFTER_TO.search(quote[max(s - 40, 0) : s])
        ]
    return spans


def _sentences(text: str) -> tuple[tuple[int, int], ...]:
    spans, start = [], 0
    for m in _SENTENCE_END.finditer(text):
        spans.append((start, m.start()))
        start = m.end()
    spans.append((start, len(text)))
    return tuple(spans)


def _starts_inside_number(text: str, start: int, quote: str) -> bool:
    """Does the quote begin partway through a number: after its decimal point, thousands comma or sign?"""
    before = text[start - 1] if start else " "
    earlier = text[start - 2] if start > 1 else " "
    if quote[0].isdigit():
        if before in ".," and earlier.isdigit():
            return True
        # a sign, by the rule `_NUM` uses: not a hyphen joining "2026-27" or "non-0.5"
        return before in "-−" and not (earlier.isalnum() or earlier in "._")
    return quote[0] in ".," and before.isdigit() and quote[1:2].isdigit()


def _ends_inside_number(text: str, end: int, quote: str) -> bool:
    """Does the quote stop partway through a number: on its separator, or just before one and its digits?"""
    after = text[end] if end < len(text) else " "
    if quote[-1] in ".," and len(quote) > 1 and quote[-2].isdigit():
        return after.isdigit()
    return quote[-1].isdigit() and after in ".," and text[end + 1 : end + 2].isdigit()


def _locate(
    quote: str, section: SectionText, layout: _Layout | None = None
) -> tuple[_Located | None, str | None]:
    """The best clean occurrence of the quote, or a truncation problem with the first occurrence."""
    layout = layout or _Layout(section.text)
    text, q = layout.text, _norm(quote)
    if q and q not in text and _SPACED_SIGN.sub(r"\1", q) in text:
        q = _SPACED_SIGN.sub(r"\1", q)  # "- 7%" for the "-\n7%" a PDF line break left
    if not q or q not in text:
        return None, None
    sentences = _sentences(text)
    problem, best = None, None
    for m in re.finditer(re.escape(q), text):
        start, end = m.start(), m.end()
        before = text[start - 1] if start else " "
        after = text[end] if end < len(text) else " "
        issue = None
        if before.isalnum() and q[0].isalnum():
            issue = "quote starts mid-word"
        elif _starts_inside_number(text, start, q):
            issue = "quote starts mid-number"
        elif after.isalnum() and q[-1].isalnum():
            issue = "quote ends mid-word"
        elif _ends_inside_number(text, end, q):
            issue = "quote ends mid-number"
        first = next(i for i, (a, b) in enumerate(sentences) if a <= start <= b)
        last = next(i for i, (a, b) in enumerate(sentences) if a <= end <= b)
        located = _Located(
            text, start, end, sentences, first, last, _norm(section.heading or ""), q, layout
        )
        if issue is None:
            return located, None
        if best is None:
            best, problem = located, issue
    return best, problem


def _content_stems(text: str) -> set[str]:
    return {w[:4] for w in _WORD.findall(text.lower()) if len(w) >= 4 and w not in _STOP}


def _horizon_years(horizon: str) -> list[int]:
    years = []
    for m in _YEAR.finditer(horizon):
        first = int(m.group(1))
        years.append(first)
        if m.group(2):
            years.append(first // 100 * 100 + int(m.group(2)))
    return years


def _year_stated(year: int, text: str) -> bool:
    pair = rf"\b{year - 1}[ \t]*[/–-][ \t]*{year % 100:02d}\b"
    return bool(re.search(rf"\b{year}\b", text) or re.search(pair, text))


def _unstated_period(period: str, near: str) -> list[str]:
    """The years, months and quarters of `period` that `near` does not state."""
    years, months = _horizon_years(period), {m.lower()[:3] for m in _MONTH.findall(period)}
    quarters = set(_QUARTER_LABEL.findall(period))
    near_months = {m.lower()[:3] for m in _MONTH.findall(near)}
    missing = [str(y) for y in dict.fromkeys(years) if not _year_stated(y, near)]
    missing += [m for m in sorted(months) if m not in near_months]
    missing += [f"Q{q}" for q in sorted(quarters) if f"q{q}" not in near.lower()]
    return missing


def _decision_wording(text: str) -> bool:
    """Says what was decided, before any forward-looking word ("we expect the RBNZ to have cut" does not)."""
    decided = _DECISION.search(text)
    if decided is None:
        return False
    forward = _FORWARD.search(text)
    return forward is None or forward.start() > decided.start()


def _date_stated(day: date, text: str) -> bool:
    month = _MONTHS[day.month - 1]
    d = rf"0?{day.day}(?:st|nd|rd|th)?"
    pattern = rf"\b(?:{d}\s+{month}|{month}\s+{d})(?:,?\s+((?:19|20)\d{{2}}))?\b"
    return bool(re.search(rf"\b{day.isoformat()}\b", text)) or any(
        not match.group(1) or int(match.group(1)) == day.year
        for match in re.finditer(pattern, text, re.I)
    )


def _date_conflicts(day: date, text: str) -> bool:
    month = _MONTHS[day.month - 1]
    d = rf"0?{day.day}(?:st|nd|rd|th)?"
    pattern = rf"\b(?:{d}\s+{month}|{month}\s+{d}),?\s+((?:19|20)\d{{2}})\b"
    iso = rf"\b((?:19|20)\d{{2}})-{day.month:02d}-{day.day:02d}\b"
    return any(
        int(match.group(1)) != day.year
        for pattern_to_check in (pattern, iso)
        for match in re.finditer(pattern_to_check, text, re.I)
    )


def _explicit_date(text: str) -> bool:
    months = "|".join(_MONTHS)
    day = r"\d{1,2}(?:st|nd|rd|th)?"
    return bool(
        re.search(
            rf"\b(?:{day}\s+(?:{months})|(?:{months})\s+{day}|(?:19|20)\d{{2}}-\d{{2}}-\d{{2}})\b",
            text,
            re.I,
        )
    )


def _count(token: str) -> int:
    return int(token) if token.isdigit() else _COUNT_WORDS[token.lower()]


def _votes(text: str, action: PolicyAction) -> set[tuple[int, int]]:
    """Vote counts stated in sentences about a vote: "voted 4–3", "four members preferred …, three …"."""
    out = set()
    for sentence in _SENTENCE_END.split(text):
        if not _VOTE_WORD.search(sentence):
            continue
        out |= {(_count(m[1]), _count(m[2])) for m in _VOTE_PAIR.finditer(sentence)}
        members = list(_MEMBERS.finditer(sentence))
        if len(members) == 2:
            preferences = []
            for i, member in enumerate(members):
                clause = sentence[member.end() : members[i + 1].start() if i == 0 else None]
                actions = {a for a, words in _ACTIONS.items() if words.search(clause)}
                preferences.append(actions)
            if all(len(p) == 1 for p in preferences) and preferences[0] != preferences[1]:
                counts = [_count(m[1]) for m in members]
                if action in preferences[0]:
                    out.add((counts[0], counts[1]))
                elif action in preferences[1]:
                    out.add((counts[1], counts[0]))
    return out


def _survey_result(text: str, value: float | None) -> bool:
    if value is None or not _SURVEY_EXPECTATION.search(text):
        return False
    spans = _value_spans(value, text)
    return bool(spans) and all(
        re.match(
            r"\s*(?:%|per\s*cent|percent)\s+of\s+"
            r"(?:respondents|firms|businesses|households|consumers)\b",
            text[end:],
            re.I,
        )
        for _, end in spans
    )


def _who(key: str) -> str:
    return "the author" if key == "author" else issuers.display_name(key)


def _fiscal_text(text: str) -> str:
    """A spaced hyphen is a fiscal pair only when its years are consecutive."""

    def keep(match: re.Match[str]) -> str:
        first, second = int(match.group(1)), int(match.group(3))
        return match.group() if second == (first + 1) % 100 else f"{first} {match.group(3)}"

    return re.sub(r"\b((?:19|20)\d{2})([ \t]+-[ \t]*)(\d{2})\b", keep, text)


def _basis(text: str) -> str | None:
    if _ANNUAL.search(_fiscal_text(text)):
        return "annual"
    if _QUARTERLY.search(text):
        return "quarterly"
    return None


class _Checker:
    def __init__(
        self, summary: OutlookSummary, sections: Mapping[int, SectionText], ctx: VerificationContext
    ) -> None:
        self.summary, self.sections, self.ctx = summary, sections, ctx
        self.errors: list[Problem] = []
        self.warnings: list[Problem] = []
        self._layouts: dict[int, _Layout] = {}

    def layout(self, ordinal: int, section: SectionText) -> _Layout:
        if ordinal not in self._layouts:
            self._layouts[ordinal] = _Layout(section.text)
        return self._layouts[ordinal]

    def error(self, code: str, path: str, message: str) -> None:
        self.errors.append(Problem(code, path, f"{path}: {message}", "error"))

    def warn(self, code: str, path: str, message: str) -> None:
        self.warnings.append(Problem(code, path, f"{path}: {message}", "warning"))

    # -- evidence -------------------------------------------------------------------------------
    def evidence(
        self, path: str, refs: tuple[EvidenceRef, ...]
    ) -> list[tuple[EvidenceRef, _Located]]:
        found = []
        for i, ref in enumerate(refs):
            where = f"{path}.evidence[{i}]"
            if ref.version_id != self.summary.version_id:
                self.error("wrong_version", where,
                           f"cites version {ref.version_id}, not {self.summary.version_id}")  # fmt: skip
                continue
            section = self.sections.get(ref.section_ordinal)
            if section is None:
                self.error("unknown_section", where, f"unknown section {ref.section_ordinal}")
                continue
            located, truncation = _locate(
                ref.quote, section, self.layout(ref.section_ordinal, section)
            )
            if located is None:
                self.error(
                    "quote_not_found", where, f"quote not found in section {ref.section_ordinal}"
                )
            if "..." in ref.quote or "…" in ref.quote:
                self.error(
                    "quote_truncated", where, "quote contains an ellipsis (spliced or partial)"
                )
            elif truncation:
                self.error("quote_truncated", where, truncation)
            self.page(where, ref, section)
            if located is not None:
                if INJECTION_PATTERN.search(located.sentence_text()):
                    self.error("instruction_like_evidence", where,
                               "evidence reads like an instruction to a model")  # fmt: skip
                found.append((ref, located))
        return found

    def page(self, where: str, ref: EvidenceRef, section: SectionText) -> None:
        if ref.page is None:
            return
        if section.page_start is None:
            self.error(
                "page_without_pages", where, f"page {ref.page} cited for a section without pages"
            )
        elif not section.page_start <= ref.page <= (section.page_end or section.page_start):
            self.error("page_outside_section", where,
                       f"page {ref.page} is outside section {ref.section_ordinal}")  # fmt: skip

    def numbers_in(self, path: str, label: str, text: str | None, pool: str) -> None:
        if not text:
            return
        supported = _numbers(pool)
        for value in sorted(_numbers(text)):
            if not any(_same(value, n) or _same(-value, n) for n in supported):
                self.error("number_not_in_evidence", path,
                           f"number {value:g} in the {label} does not appear in its evidence")  # fmt: skip

    def residue_numbers(
        self, path: str, text: str, found: list[tuple[EvidenceRef, _Located]]
    ) -> None:
        """A number supported only by chart-axis labels or an unlabelled row is not a stated figure."""
        for value in sorted(_numbers(text)):
            spots = [(loc, loc.start + s) for _, loc in found for v, s, _ in _number_spans(loc.quote)
                     if _same(abs(v), abs(value))]  # fmt: skip
            if spots and all(loc.layout.place(at)[0] == "residue" for loc, at in spots):
                self.error("axis_residue", path,
                           f"number {value:g} appears only among unlabelled numbers (chart-axis labels or a"
                           " table row without its labels)")  # fmt: skip

    # -- statements -----------------------------------------------------------------------------
    def statement(
        self, path: str, statement: Statement | ReportedFact | Guidance | Assumption
    ) -> list[tuple[EvidenceRef, _Located]]:
        found = self.evidence(path, statement.evidence)
        pool = " ".join(
            [r.quote for r in statement.evidence] + [loc.sentence_text() for _, loc in found]
        )
        self.numbers_in(path, "text", statement.text, pool)
        self.residue_numbers(path, statement.text, found)
        context = " ".join(loc.near_text() for _, loc in found)
        stems = _content_stems(statement.text)
        if found and stems and len(stems & _content_stems(context)) / len(stems) < 0.5:
            self.warn("weak_lexical_support", path,
                      "under half of the text's content words appear around its quotes")  # fmt: skip
        if _CERTAIN.search(statement.text) and not _CERTAIN.search(pool):
            self.warn("certainty_escalation", path, "states more certainty than its evidence")
        return found

    # -- forecasts ------------------------------------------------------------------------------
    def forecast(self, path: str, claim: ForecastClaim) -> None:
        found = self.evidence(path, claim.evidence)
        quotes = " ".join(r.quote for r in claim.evidence)
        sentences = " ".join(loc.sentence_text() for _, loc in found)
        self.numbers_in(path, "indicator label", claim.indicator_label, f"{quotes} {sentences}")
        self.numbers_in(path, "qualification", claim.qualification, f"{quotes} {sentences}")
        value_at: list[tuple[_Located, int]] = []  # where the value sits, in section coordinates
        superseded = []
        if claim.value is not None:
            for _, loc in found:
                for s, e in _value_spans(claim.value, loc.quote):
                    value_at.append((loc, loc.start + s))
                    before = loc.text[max(0, loc.start + s - 30) : loc.start + s]
                    after = loc.text[loc.start + e : loc.start + e + 30]
                    superseded.append(
                        bool(_EARLIER_BEFORE.search(before) or _EARLIER_AFTER.match(after))
                    )
            if not value_at:  # only quotes actually found in the document can support a value
                self.error("value_not_in_evidence", path,
                           f"value {claim.value:g} does not appear in its evidence")  # fmt: skip
            elif all(superseded):
                self.error("superseded_value", path,
                           f"value {claim.value:g} is described as an earlier forecast")  # fmt: skip
            self.unit(path, claim.value, claim.unit, found)
            self.placement(path, claim.value, value_at, claim.horizon, "forecast")
        if claim.issuer is None and self.summary.contract_version >= 2:
            self.error(
                "missing_issuer", path, "the forecast does not name its issuer (who made it)"
            )
        if not found:
            return
        self.horizon(path, claim, found, value_at)
        self.history_and_scenario(path, claim, found)
        self.direction(path, claim, quotes)
        self.indicator(path, claim)
        if claim.issuer is not None or self.summary.contract_version < 2:
            self.issuer(path, claim, found, value_at)
        if claim.indicator is Indicator.OCR:
            clauses = [loc.clause_at(at) for loc, at in value_at] or [
                loc.sentence_text() for _, loc in found
            ]
            if any(_decision_wording(c) for c in clauses):
                self.error("decision_as_forecast", path,
                           "the evidence describes a policy decision (what was decided), not a forecast")  # fmt: skip

    def unit(
        self, path: str, value: float, unit: str | None, found: list[tuple[EvidenceRef, _Located]]
    ) -> None:
        if unit is None:
            self.error("missing_unit", path, f"value {value:g} has no unit")
            return
        if unit not in UNITS:
            self.error("unknown_unit", path, f"unit {unit!r} is not a recognised unit")
            return
        checked = []
        for _, loc in found:
            quote = loc.quote
            for s, e in _value_spans(value, quote):
                place, line = loc.layout.place(loc.start + s)
                if (
                    place == "cell"
                ):  # a table states its unit in the caption and headings, not the cell
                    checked.append(self._table_unit(unit, loc.layout.table(line).context))
                    continue
                # the section may carry on past a quote that stops at the number: "$25" | " billion"
                beyond = loc.text[loc.start + e : loc.start + e + 30]
                lead = loc.lead_to(loc.start + s)  # the quote may start after "debt-to-GDP ratio"
                checked.append(self._unit_matches(unit, quote[:s], quote[e:], beyond, lead))
        if checked and not any(checked):
            self.error("unit_mismatch", path,
                       f"unit {unit!r} is not what the evidence states next to {value:g}")  # fmt: skip

    @staticmethod
    def _table_unit(unit: str, context: str) -> bool:
        if unit in ("percent", "percent_of_gdp"):
            points = any(p.search(context) for p in _POINTS.values())
            share = bool(_SHARE_OF_GDP.search(context))
            return (
                bool(_PERCENT_WORD.search(context))
                and not points
                and share == (unit == "percent_of_gdp")
            )
        if unit in _POINTS:
            return bool(_POINTS[unit].search(context))
        if unit in ("nzd_billion", "nzd_million"):
            scale = "billion|bn" if unit == "nzd_billion" else "million|m"
            return bool(re.search(rf"\$\s*(?:{scale})\b|\b(?:{scale})\b", context, re.I))
        if unit == "nzd":
            return "$" in context and not _MONEY_SCALE.search(context.split("$", 1)[1])
        return True  # index, persons, ratio: no unit marker to compare

    # -- where a number sits on the page ----------------------------------------------------------
    def placement(
        self, path: str, value: float, value_at: list[tuple[_Located, int]], period: str | None,
        what: str,
    ) -> None:  # fmt: skip
        """A value must be stated in a sentence, or in a table cell whose column heading matches its period.

        Only the row of years directly above a table's rows is trusted as a column heading. Labels for groups
        of columns (GDP, inflation) that the extraction detached from the rows are not: in the Phase 4H Treasury
        file they come out in the opposite order to the columns.
        """
        if not value_at:
            return
        places = [(loc, at, *loc.layout.place(at)) for loc, at in value_at]
        if all(p == "residue" for _, _, p, _ in places):
            self.error("axis_residue", path,
                       f"{value:g} appears only among unlabelled numbers (chart-axis labels or a table row"
                       f" without its labels), not as a stated {what}")  # fmt: skip
            return
        if any(p == "text" for _, _, p, _ in places):
            return
        wanted = set(_horizon_years(period or ""))
        verdicts: list[tuple[str, str]] = []
        for loc, at, p, line in places:
            if p != "cell":
                continue
            years = loc.layout.table(line).years
            if years is None:
                verdicts.append(("unverified", "no row of years heads the table"))
                continue
            heading = years[loc.layout.cell_index(line, at)]
            if wanted and set(_horizon_years(heading)) != wanted:
                verdicts.append(("mismatch", f"its column is headed {heading}"))
            elif len(set(years)) < len(years):
                verdicts.append(("unverified", f"the {heading} heading repeats across groups of columns"
                                               " whose labels are detached from the rows"))  # fmt: skip
            else:
                verdicts.append(("heading", heading))
        found = {
            kind: reason for kind, reason in reversed(verdicts)
        }  # the first reason of each kind
        if "heading" in found:
            self.warn("table_heading_unverified", path,
                      f"{value:g} is a table cell under {found['heading']}: confirm in the original that"
                      f" its column measures this {what}")  # fmt: skip
        elif "unverified" in found:
            self.error("table_column_unverified", path,
                       f"{value:g} is a table cell whose column cannot be confirmed from the extracted text:"
                       f" {found['unverified']}")  # fmt: skip
        elif "mismatch" in found:
            self.error("table_column_mismatch", path,
                       f"{value:g} is a table cell, but {found['mismatch']}, not {period!r}")  # fmt: skip

    def cell_years(self, value_at: list[tuple[_Located, int]]) -> list[int]:
        """The latest year heading each table cell the value occupies (for the outturn-or-forecast test)."""
        out = []
        for loc, at in value_at:
            p, line = loc.layout.place(at)
            years = loc.layout.table(line).years if p == "cell" else None
            if years:
                out.append(max(_horizon_years(years[loc.layout.cell_index(line, at)]) or [0]))
        return out

    # -- who made a forecast --------------------------------------------------------------------
    def _credited(self, loc: _Located, at: int) -> str | None:
        """Who the evidence credits with the figure at `at`: "author", an organisation key, or None."""
        author = self.ctx.institution

        def one(keys: set[str], self_reference: bool = False) -> str | None:
            keys = {"author" if k == author else k for k in keys} | (
                {"author"} if self_reference else set()
            )
            return next(iter(keys)) if len(keys) == 1 else None  # none, or several: unclear

        place, line = loc.layout.place(at)
        if place == "cell":
            label = loc.layout.row(line).label
            who = one(issuers.named(label), bool(issuers.SELF_REFERENCE.search(label)))
            if who is None:
                who = one(issuers.named(loc.layout.table(line).caption))
            if who is not None:
                return who
        for text in (loc.clause_at(at), loc.sentence_text()):
            credited, own = issuers.credited(text), bool(issuers.SELF_REFERENCE.search(text))
            if credited or own:
                return one(credited, own)
        # A sentence that names nobody continues the one before it: "…in the IMF's World Economic Outlook (WEO).
        # The outlook for growth in 2026 has been revised to 3.1%" is the IMF's figure.
        previous = loc.previous_sentence()
        if not issuers.named(loc.sentence_text()) and not issuers.SELF_REFERENCE.search(previous):
            return one({k for k in issuers.credited(previous) if k != author})
        return None

    def issuer(
        self,
        path: str,
        claim: ForecastClaim,
        found: list[tuple[EvidenceRef, _Located]],
        value_at: list[tuple[_Located, int]],
    ) -> None:
        # A version 1 forecast has no issuer: it was presented as the author's own, so check it as that.
        role = claim.issuer_role or IssuerRole.AUTHOR
        name = claim.issuer or "the author"
        key, author = (
            (issuers.organisation_of(claim.issuer) if claim.issuer else None),
            self.ctx.institution,
        )
        if role is IssuerRole.AUTHOR and key is not None and author is not None and key != author:
            self.error(
                "issuer_mismatch", path, f"issuer {name!r} is not the document's author ({author})"
            )
            return
        if role is IssuerRole.THIRD_PARTY and key is not None and key == author:
            self.error(
                "issuer_mismatch",
                path,
                f"issuer {name!r} is the document's author, not a third party",
            )
            return
        claimed = "author" if role is IssuerRole.AUTHOR else key
        spots = value_at or [(loc, loc.start) for _, loc in found]
        credited = {self._credited(loc, at) for loc, at in spots} - {None}
        if claimed is not None and claimed in credited:
            return
        if credited:
            who = ", ".join(sorted(_who(c) for c in credited if c))
            self.error(
                "issuer_mismatch",
                path,
                f"the evidence credits this forecast to {who}, not {name!r}",
            )
            return
        captions = [loc.layout.table(line).caption for loc, at in spots
                    for place, line in [loc.layout.place(at)] if place == "cell"]  # fmt: skip
        context = " ".join([loc.near_text() for _, loc in found] + captions)
        mentioned = {"author" if k == author else k for k in issuers.named(context)}
        if role is IssuerRole.AUTHOR:
            others = sorted(_who(k) for k in mentioned - {"author"})
            if others:
                self.warn("issuer_unclear", path,
                          f"the evidence names {', '.join(others)} nearby but does not say who made this"
                          " forecast")  # fmt: skip
        elif (
            (claimed not in mentioned)
            if claimed
            else not _content_stems(name) & _content_stems(context)
        ):
            self.error(
                "issuer_not_in_evidence",
                path,
                f"issuer {name!r} is not named in or near the evidence",
            )

    @staticmethod
    def _unit_matches(unit: str, before: str, after: str, beyond: str = "", lead: str = "") -> bool:
        def stated(name: str, text: str = after) -> bool:
            return bool(_UNIT_SUFFIX[name].match(text))

        # A quote can stop at the number; what the stored text says next still qualifies it.
        following = (after, beyond)
        other_percentish = any(
            stated(name, text)
            for name in ("percentage_points", "basis_points")
            for text in following
        )
        if unit == "percent":
            return (
                stated("percent")
                and not other_percentish
                and not any(_OF_GDP.match(text) for text in following)
                and not _GDP_RATIO_BEFORE.search(lead)
            )
        if unit == "percent_of_gdp":  # the GDP qualifier must belong to this number
            share = any(_OF_GDP.match(text) for text in following) or bool(
                _GDP_RATIO_BEFORE.search(before[-80:]) or _GDP_RATIO_BEFORE.search(lead)
            )
            return stated("percent") and not other_percentish and share
        if unit in ("percentage_points", "basis_points"):
            return stated(unit)
        if unit in ("nzd_billion", "nzd_million"):
            return bool(_DOLLAR_PREFIX.search(before)) and stated(unit)
        if unit == "nzd":  # plain dollars: "$25 billion" is not 25 dollars
            if _MONEY_SCALE.match(after) or _MONEY_SCALE.match(beyond):
                return False
            return bool(_DOLLAR_PREFIX.search(before)) or after.lower().lstrip().startswith(
                "dollar"
            )
        return True  # index, persons, ratio: no unit marker to compare

    def horizon(
        self,
        path: str,
        claim: ForecastClaim,
        found: list[tuple[EvidenceRef, _Located]],
        value_at: list[tuple[_Located, int]],
    ) -> None:
        horizon = claim.horizon
        if not (
            _horizon_years(horizon) or _MONTH.search(horizon) or _QUARTER_LABEL.search(horizon)
        ):
            self.warn("horizon_without_period", path, f"horizon {horizon!r} names no period")
        near = " ".join(
            loc.heading
            + " "
            + loc.with_lines(
                loc.sentences[max(loc.first - 1, 0)][0],
                loc.sentences[min(loc.last + 1, len(loc.sentences) - 1)][1],
            )
            for _, loc in found
        )
        missing = _unstated_period(horizon, near)
        if missing:
            self.error("horizon_not_supported", path,
                       f"horizon {horizon!r} is not stated near the quote ({', '.join(missing)})")  # fmt: skip
        clauses = [loc.clause_at(at) for loc, at in value_at] or [
            loc.sentence_text() for _, loc in found
        ]
        horizon_fiscal = bool(_FISCAL.search(_fiscal_text(horizon)))
        fiscal_clauses = [loc.with_lines(*loc._clause_span(at)) for loc, at in value_at] or clauses
        if (
            any(_FISCAL.search(_fiscal_text(c)) for c in fiscal_clauses)
            and not horizon_fiscal
            and not any(_CALENDAR.search(c) for c in clauses)
        ):
            self.error("fiscal_calendar_mismatch", path,
                       f"evidence states a fiscal year but horizon {horizon!r} does not")  # fmt: skip
        elif horizon_fiscal and any(_CALENDAR.search(c) for c in clauses):
            self.error("fiscal_calendar_mismatch", path,
                       f"evidence states a calendar year but horizon {horizon!r} is fiscal")  # fmt: skip
        if claim.value is None:
            return
        evidence_basis = {_basis(c) for c in fiscal_clauses} - {None}
        horizon_basis = _basis(horizon)
        if _QUARTER_PERIOD.search(horizon) and any(_QUARTER_PERIOD.search(c) for c in clauses):
            # "annual inflation ... in the December quarter": the horizon names the evidence's own period, so the
            # change basis is in the label ("Annual CPI inflation"), not the word "quarter".
            horizon_basis = _basis(_QUARTER_PERIOD.sub("", horizon))
        claim_basis = horizon_basis or _basis(
            f"{claim.indicator_label} {claim.qualification or ''}"
        )
        if len(evidence_basis) == 1:
            (stated,) = evidence_basis
            if claim_basis is not None and claim_basis != stated:
                self.error("period_basis_mismatch", path,
                           f"evidence describes a {stated} change; horizon {horizon!r} does not")  # fmt: skip

    def _looks_forward(self, claim: ForecastClaim, loc: _Located) -> bool:
        """Forward-looking by its own sentence, or by the heading of the section it was quoted from.

        A heading ("GDP forecasts") only qualifies a figure the sentence itself leaves unqualified, so it
        is accepted when the sentence is free of past-tense/outturn wording and the horizon is a stated
        year not before publication. Limit: a verbless historical figure for the publication year, under
        a forecast heading, cannot be told from a forecast; the human review requirement covers it.
        """
        sentence = loc.sentence_text()
        if _FORWARD.search(sentence):
            return True
        if not _FORWARD.search(loc.heading) or _HISTORICAL.search(sentence):
            return False
        years, published = _horizon_years(claim.horizon), self.ctx.published_on
        return bool(years) and published is not None and max(years) >= published.year

    def history_and_scenario(
        self, path: str, claim: ForecastClaim, found: list[tuple[EvidenceRef, _Located]]
    ) -> None:
        if not any(self._looks_forward(claim, loc) for _, loc in found):
            self.error("historical_not_forecast", path,
                       "no forward-looking language in the cited sentence or its section heading (a historical observation?)")  # fmt: skip
        else:
            years = _horizon_years(claim.horizon)
            published = self.ctx.published_on
            if years and published is not None and max(years) < published.year:
                self.error("historical_not_forecast", path,
                           f"horizon {claim.horizon!r} ends before publication ({published.isoformat()})")  # fmt: skip
        scenario_context = " ".join(f"{loc.heading} {loc.sentence_text()}" for _, loc in found)
        if claim.scenario is None and _alternative_scenario(scenario_context):
            self.error(
                "scenario_as_baseline", path, "evidence describes a scenario, not the baseline"
            )
        if claim.scenario is not None:
            words = _content_stems(claim.scenario)
            section_words = set().union(
                *(_content_stems(f"{loc.heading} {loc.text}") for _, loc in found)
            )
            if not words or not words & section_words:
                self.error("scenario_not_in_text", path,
                           f"scenario {claim.scenario!r} is not named in the cited section")  # fmt: skip

    def direction(self, path: str, claim: ForecastClaim, quotes: str) -> None:
        up, down, flat = (bool(p.search(quotes)) for p in (_UP, _DOWN, _FLAT))
        contradiction = (
            (claim.direction == "up" and down and not up)
            or (claim.direction == "down" and up and not down)
            or (claim.direction == "flat" and (up or down) and not flat)
        )
        if contradiction:
            self.error("direction_contradiction", path,
                       f"direction {claim.direction!r} contradicts the quoted wording")  # fmt: skip

    def indicator(self, path: str, claim: ForecastClaim) -> None:
        label = claim.indicator_label
        own = _INDICATOR_WORDS.get(claim.indicator)
        if own is not None and own.search(label):
            return
        others = [
            i.value for i, p in _INDICATOR_WORDS.items() if i != claim.indicator and p.search(label)
        ]
        if others:
            self.error("indicator_mismatch", path,
                       f"label {label!r} reads as {', '.join(others)}, not {claim.indicator.value}")  # fmt: skip


class _RecordChecker(_Checker):
    """Contract version 2 records: policy decisions, reported facts, forward guidance, assumptions."""

    def value_spots(
        self, value: float, found: list[tuple[EvidenceRef, _Located]]
    ) -> list[tuple[_Located, int]]:
        return [(loc, loc.start + s) for _, loc in found for s, _ in _value_spans(value, loc.quote)]

    def decision(self, path: str, d: PolicyDecision) -> None:
        found = self.evidence(path, d.evidence)
        value_at = self.value_spots(d.rate, found)
        if found and not value_at:
            self.error(
                "value_not_in_evidence", path, f"rate {d.rate:g} does not appear in its evidence"
            )
        elif value_at:
            self.unit(path, d.rate, "percent", found)
            self.placement(path, d.rate, value_at, None, "rate")
        if not found:
            return
        if not any(_decision_wording(loc.sentence_text()) for _, loc in found):
            self.error("decision_not_in_evidence", path,
                       "the cited sentences do not describe a policy decision (what was decided)")  # fmt: skip
        sentences = [
            loc.sentence_text() for _, loc in found if _decision_wording(loc.sentence_text())
        ]
        for sentence in sentences:
            transition = re.search(
                r"\bfrom\s+\d+(?:\.\d+)?\s*(?:%|percent|per\s+cent)?\s+to\s+(\d+(?:\.\d+)?)",
                sentence,
                re.I,
            )
            if transition and not _same(d.rate, float(transition.group(1))):
                self.error("decision_rate_contradiction", path,
                           "the rate is not the resulting rate stated in the decision")  # fmt: skip
        decision_text = " ".join(_FORWARD.split(sentence, maxsplit=1)[0] for sentence in sentences)
        stated = {action for action, words in _ACTIONS.items() if words.search(decision_text)}
        if not stated or len(stated) > 1 or re.search(r"\b(?:not|never|no)\b", decision_text, re.I):
            self.error("decision_action_not_supported", path,
                       "the cited decision does not unambiguously support an action")  # fmt: skip
        elif d.action not in stated:
            self.error("decision_action_contradiction", path,
                       f"action {d.action.value!r} contradicts the decision wording")  # fmt: skip
        near = " ".join(loc.near_text() for _, loc in found)
        if not _date_stated(d.decided_on, near):
            decision_sentences = " ".join(loc.sentence_text() for _, loc in found)
            if (
                d.decided_on != self.ctx.published_on
                or _date_conflicts(d.decided_on, near)
                or _explicit_date(decision_sentences)
            ):
                self.error("decision_date_not_supported", path,
                           f"decision date {d.decided_on.isoformat()} is not stated near the quote and is not"
                           " the publication date")  # fmt: skip
            elif not re.search(r"\btoday\b", near, re.IGNORECASE):
                self.warn(
                    "decision_date_assumed",
                    path,
                    "the decision date is taken from the publication date",
                )
        votes = _votes(near, d.action)
        if d.vote_for is not None:
            if (d.vote_for, d.vote_against) not in votes:
                self.error("vote_not_in_evidence", path,
                           f"vote {d.vote_for}–{d.vote_against} is not stated in the evidence")  # fmt: skip
        elif votes:
            a, b = sorted(votes)[0]
            self.error("vote_not_captured", path,
                       f"the evidence states a vote ({a}–{b}) that the decision does not record")  # fmt: skip

    def fact(self, path: str, f: ReportedFact) -> None:
        found = self.statement(path, f)
        value_at: list[tuple[_Located, int]] = []
        if f.value is not None:
            value_at = self.value_spots(f.value, found)
            if found and not value_at:
                self.error("value_not_in_evidence", path,
                           f"value {f.value:g} does not appear in its evidence")  # fmt: skip
            self.unit(path, f.value, f.unit, found)
            self.placement(path, f.value, value_at, f.period, "figure")
        if not found:
            return
        near = " ".join(loc.near_text() for _, loc in found)
        missing = _unstated_period(f.period or "", near)
        if missing:
            self.error("period_not_supported", path,
                       f"period {f.period!r} is not stated near the quote ({', '.join(missing)})")  # fmt: skip
        prose = [(loc, at) for loc, at in value_at if loc.layout.place(at)[0] == "text"]
        clauses = [loc.with_lines(*loc._clause_span(at)) for loc, at in prose] or (
            [] if value_at else [loc.sentence_text() for _, loc in found]
        )
        published = self.ctx.published_on
        if any(
            _FORWARD.search(c) and not _HISTORICAL.search(c) and not _survey_result(c, f.value)
            for c in clauses
        ) or (
            published is not None and self.fact_table_forward(f.period or "", value_at, published)
        ):
            self.error("forecast_as_fact", path,
                       "the evidence states a forecast or an estimate, not an outturn the document reports")  # fmt: skip
        self.definition(path, f, found, clauses)
        context = " ".join([near] + [loc.layout.table(line).caption for loc, at in value_at
                                     for place, line in [loc.layout.place(at)] if place == "cell"])  # fmt: skip
        key = issuers.organisation_of(f.source)
        named = (
            key in issuers.named(context)
            if key
            else bool(_content_stems(f.source) & _content_stems(context))
        )
        if not named:
            self.warn(
                "source_not_named", path, f"source {f.source!r} is not named near the evidence"
            )

    def fact_table_forward(
        self, period: str, value_at: list[tuple[_Located, int]], published: date
    ) -> bool:
        for loc, at in value_at:
            place, line = loc.layout.place(at)
            if place != "cell":
                continue
            table = loc.layout.table(line)
            if not table.years:
                continue
            years = _horizon_years(table.years[loc.layout.cell_index(line, at)])
            if not years or max(years) < published.year:
                continue
            year = max(years)
            context = f"{loc.heading} {table.context}"
            # Only an explicitly historical, completed and unambiguous period can override
            # the conservative treatment of a current-year table column.
            quarter = re.search(r"\bq([1-4])\b", period, re.I)
            month = next(
                (i for i, name in enumerate(_MONTHS, 1) if re.search(rf"\b{name}\b", period, re.I)),
                None,
            )
            if quarter:
                month = int(quarter.group(1)) * 3
            elif not (
                _QUARTER_PERIOD.search(period) or _FISCAL.search(period) or _CALENDAR.search(period)
            ):
                month = None
            elif month is None and _CALENDAR.search(period):
                month = 12
            complete = (
                month is not None
                and set(_horizon_years(period)) == {year}
                and date(year, month, monthrange(year, month)[1]) < published
            )
            historical = _HISTORICAL.search(context) or re.search(
                r"\bhistorical\b|\boutturns\b", context, re.I
            )
            if not complete or not historical or _FORWARD.search(context):
                return True
        return False

    def definition(
        self,
        path: str,
        f: ReportedFact,
        found: list[tuple[EvidenceRef, _Located]],
        clauses: list[str],
    ) -> None:
        """The adjustment basis and measure a fact claims must be stated; one never stated is reported."""
        text = " ".join(f"{loc.heading} {loc.sentence_text()}" for _, loc in found)
        stated = {a for a, words in _ADJUSTMENT.items() if words.search(text)}
        claimed = f.definition.adjustment
        if claimed is not Adjustment.NOT_STATED and claimed not in stated:
            self.error("definition_not_in_evidence", path,
                       f"adjustment {claimed.value!r} is not stated in the evidence")  # fmt: skip
        measure = f.definition.measure
        if measure:
            if re.search(r"\baverage\b", measure, re.I) and not re.search(
                r"\baverage\b", text, re.I
            ):
                self.error("definition_not_in_evidence", path,
                           f"measure {measure!r} is not stated in the evidence")  # fmt: skip
            basis, evidence_basis = _basis(measure), {_basis(c) for c in clauses} - {None}
            if basis and len(evidence_basis) == 1 and basis not in evidence_basis:
                self.error("period_basis_mismatch", path,
                           f"evidence describes a {evidence_basis.pop()} change; measure {measure!r} does not")  # fmt: skip
        if f.value is None:
            return
        if len(stated) > 1:
            self.warn("definition_ambiguous", path,
                      f"the evidence states more than one adjustment basis near {f.value:g}")  # fmt: skip
        elif not stated and claimed is Adjustment.NOT_STATED:
            self.warn("definition_not_stated", path,
                      f"the evidence does not state the adjustment basis of {f.value:g} (seasonally adjusted"
                      " or not): show it as the institution's figure and do not compare it with an official"
                      " series")  # fmt: skip
        elif stated and claimed is Adjustment.NOT_STATED:
            self.warn("definition_omitted", path,
                      f"the evidence states the adjustment basis ({stated.pop().value}) but the fact omits it")  # fmt: skip

    def guidance(self, path: str, g: Guidance) -> None:
        found = self.statement(path, g)
        if found and not any(
            _FORWARD.search(loc.sentence_text()) or _CONDITIONAL.search(loc.sentence_text())
            for _, loc in found
        ):
            self.error("guidance_not_forward", path,
                       "guidance must say what may happen; the cited sentences do not look forward")  # fmt: skip
        key, author = issuers.organisation_of(g.issuer), self.ctx.institution
        context = " ".join(loc.near_text() for _, loc in found)
        if found and key is not None and key != author and key not in issuers.named(context):
            self.error(
                "issuer_not_in_evidence",
                path,
                f"issuer {g.issuer!r} is not named in or near the evidence",
            )

    def assumption(self, path: str, a: Assumption) -> None:
        found = self.statement(path, a)
        if a.scenario is None or not found:
            return
        words = _content_stems(a.scenario)
        section_words = set().union(
            *(_content_stems(f"{loc.heading} {loc.text}") for _, loc in found)
        )
        if not words or not words & section_words:
            self.error("scenario_not_in_text", path,
                       f"scenario {a.scenario!r} is not named in the cited section")  # fmt: skip


def verify(
    summary: OutlookSummary,
    sections: Mapping[int, SectionText | str],
    context: VerificationContext | None = None,
) -> VerificationReport:
    ctx = context or VerificationContext()
    resolved = {k: v if isinstance(v, SectionText) else SectionText(v) for k, v in sections.items()}
    c = _RecordChecker(summary, resolved, ctx)
    c.statement("outlook", summary.outlook)
    for name in ("drivers", "risks"):
        for i, statement in enumerate(getattr(summary, name)):
            c.statement(f"{name}[{i}]", statement)
    if summary.uncertainty is not None:
        c.statement("uncertainty", summary.uncertainty)
    for i, claim in enumerate(summary.forecasts):
        c.forecast(f"forecasts[{i}]", claim)
        if claim.indicator not in summary.indicators:
            c.warn("indicator_not_listed", f"forecasts[{i}]",
                   f"indicator {claim.indicator.value} is not in the summary's indicator list")  # fmt: skip
    for name, check in (
        ("facts", c.fact),
        ("decisions", c.decision),
        ("guidance", c.guidance),
        ("assumptions", c.assumption),
    ):
        for i, item in enumerate(getattr(summary, name)):
            check(f"{name}[{i}]", item)
    for ordinal in ctx.injection_ordinals:
        c.warn("injection_suspected_section", f"section[{ordinal}]",
               "section text resembles instructions to a model")  # fmt: skip
    return VerificationReport(tuple(c.errors), tuple(c.warnings))
