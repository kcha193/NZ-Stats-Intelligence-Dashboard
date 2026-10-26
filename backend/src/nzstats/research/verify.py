"""Deterministic verification of a model's summary against the stored document text.

Every rule is a fixed, explainable test on the cited text: verbatim quotes, numbers, units, horizons,
period basis, versions, pages, forward-looking language and scenario wording. An *error* blocks
approval; a *warning* is shown to the reviewer. The checks are lexical. Passing them means nothing
contradicted the evidence that these rules can see; it is not a judgement of economic accuracy,
completeness or interpretation, which stays with the human reviewer (`SCOPE` says so wherever a
result is shown).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from nzstats.research.contract import (
    EvidenceRef,
    ForecastClaim,
    Indicator,
    OutlookSummary,
    SectionText,
    Statement,
)
from nzstats.research.prompt import INJECTION_PATTERN

VERIFIER_VERSION = "verify-2"
SCOPE = (
    "Deterministic evidence checks only: quotes, numbers, units, horizons, versions and pages were"
    " matched against the stored text. This is not a check of economic accuracy, completeness or"
    " interpretation; a reviewer must read the cited evidence."
)
UNITS = frozenset({"percent", "percentage_points", "basis_points", "percent_of_gdp", "nzd",
                   "nzd_million", "nzd_billion", "index", "persons", "ratio"})  # fmt: skip

_NUM = re.compile(r"(?<![\w.])(?P<sign>[-−])?(?P<int>\d+(?:,\d{3})*(?:\.\d+)?)?(?P<frac>[½¼¾])?")
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
_SCENARIO = re.compile(
    r"scenario|alternative (?:path|projection|forecast)|sensitivity|illustrative|stress test",
    re.IGNORECASE,
)
_FISCAL = re.compile(
    r"fiscal|financial year|june\s+(?:20\d{2}\s+)?year|year\s+(?:to|ending|ended)\s+june"
    r"|\b(?:19|20)\d{2}\s*[/–-]\s*\d{2}\b|\bfy\s*\d",
    re.IGNORECASE,
)
_CALENDAR = re.compile(
    r"calendar|december\s+(?:20\d{2}\s+)?year|year\s+(?:to|ending|ended)\s+december", re.IGNORECASE
)
_ANNUAL = re.compile(
    r"annual|year[- ]on[- ]year|\by/y\b|\byoy\b|\byear\s+(?:to|ending|ended)\b|\bper year\b"
    r"|\b(?:march|june|september|december)\s+(?:20\d{2}\s+)?year\b|calendar|\b(?:19|20)\d{2}\s*[/–-]\s*\d{2}\b",
    re.IGNORECASE,
)
_QUARTERLY = re.compile(r"\bquarter(?:ly)?\b|\bq/q\b|\bqoq\b|\bq[1-4]\b", re.IGNORECASE)
_UP = re.compile(
    r"\b(?:ris|rose|increas|grow|grew|higher|climb|accelerat|lift|strengthen|pick(?:s|ed)? up|hike"
    r"|peak|improv|recover)", re.IGNORECASE)  # fmt: skip
_DOWN = re.compile(
    r"\b(?:fall|fell|declin|decreas|lower|eas(?:e|es|ed|ing)\b|cut|contract|weaken|slow|drop|reduc"
    r"|deteriorat)", re.IGNORECASE)  # fmt: skip
_FLAT = re.compile(r"\b(?:steady|unchanged|flat|stable|hold|remain)", re.IGNORECASE)
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
_DOLLAR_PREFIX = re.compile(r"(?:\$|nzd\s?|nz\$)\s?$", re.IGNORECASE)
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
class _Located:
    """A quote found in its section: the sentences around it, for checks that need context."""

    text: str  # the normalised section text
    start: int  # quote offset in `text`
    end: int
    sentences: tuple[tuple[int, int], ...]
    first: int  # indices into `sentences` covering the quote
    last: int
    heading: str

    def sentence_text(self) -> str:
        a, b = self.sentences[self.first][0], self.sentences[self.last][1]
        return self.text[a:b]

    def near_text(self) -> str:
        lo, hi = max(self.first - 1, 0), min(self.last + 1, len(self.sentences) - 1)
        return f"{self.heading} {self.text[self.sentences[lo][0] : self.sentences[hi][1]]}"

    def clause_at(self, offset: int) -> str:
        """The clause of the quote's sentence that contains `offset` (section coordinates)."""
        a, b = self.sentences[self.first][0], self.sentences[self.last][1]
        sentence, cut = self.text[a:b], a
        for part in _CLAUSE.split(sentence):
            if cut <= offset < cut + len(part) + 1:
                return part
            cut += len(part) + 1
        return sentence


def _norm(text: str) -> str:
    return " ".join(text.split())


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


def _numbers(text: str) -> set[float]:
    return {v for v, _, _ in _number_spans(text)}


def _same(a: float, b: float) -> bool:
    return abs(a - b) < 1e-9


def _value_spans(value: float, quote: str) -> list[tuple[int, int]]:
    """Where `value` is stated in the quote; a negative value may be an unsigned number + decline word."""
    spans = [(s, e) for v, s, e in _number_spans(quote) if _same(v, value)]
    if not spans and value < 0 and _DOWN.search(quote):
        spans = [(s, e) for v, s, e in _number_spans(quote) if _same(v, -value)]
    return spans


def _sentences(text: str) -> tuple[tuple[int, int], ...]:
    spans, start = [], 0
    for m in _SENTENCE_END.finditer(text):
        spans.append((start, m.start()))
        start = m.end()
    spans.append((start, len(text)))
    return tuple(spans)


def _locate(quote: str, section: SectionText) -> tuple[_Located | None, str | None]:
    """The best clean occurrence of the quote, or a truncation problem with the first occurrence."""
    text, q = _norm(section.text), _norm(quote)
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
        elif after.isalnum() and q[-1].isalnum():
            issue = "quote ends mid-word"
        elif q[-1] in ".," and len(q) > 1 and q[-2].isdigit() and after.isdigit():
            issue = "quote ends mid-number"
        first = next(i for i, (a, b) in enumerate(sentences) if a <= start <= b)
        last = next(i for i, (a, b) in enumerate(sentences) if a <= end <= b)
        located = _Located(text, start, end, sentences, first, last, _norm(section.heading or ""))
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
    pair = rf"\b{year - 1}\s*[/–-]\s*{year % 100:02d}\b"
    return bool(re.search(rf"\b{year}\b", text) or re.search(pair, text))


def _basis(text: str) -> str | None:
    if _ANNUAL.search(text):
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
            located, truncation = _locate(ref.quote, section)
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

    # -- statements -----------------------------------------------------------------------------
    def statement(self, path: str, statement: Statement) -> None:
        found = self.evidence(path, statement.evidence)
        pool = " ".join(
            [r.quote for r in statement.evidence] + [loc.sentence_text() for _, loc in found]
        )
        self.numbers_in(path, "text", statement.text, pool)
        context = " ".join(loc.near_text() for _, loc in found)
        stems = _content_stems(statement.text)
        if found and stems and len(stems & _content_stems(context)) / len(stems) < 0.5:
            self.warn("weak_lexical_support", path,
                      "under half of the text's content words appear around its quotes")  # fmt: skip
        if _CERTAIN.search(statement.text) and not _CERTAIN.search(pool):
            self.warn("certainty_escalation", path, "states more certainty than its evidence")

    # -- forecasts ------------------------------------------------------------------------------
    def forecast(self, path: str, claim: ForecastClaim) -> None:
        found = self.evidence(path, claim.evidence)
        quotes = " ".join(r.quote for r in claim.evidence)
        sentences = " ".join(loc.sentence_text() for _, loc in found)
        self.numbers_in(path, "indicator label", claim.indicator_label, f"{quotes} {sentences}")
        self.numbers_in(path, "qualification", claim.qualification, f"{quotes} {sentences}")
        value_at: list[tuple[_Located, int]] = []  # where the value sits, in section coordinates
        if claim.value is not None:
            for ref, loc in found:
                value_at += [
                    (loc, loc.start + s) for s, _ in _value_spans(claim.value, _norm(ref.quote))
                ]
            if not any(_value_spans(claim.value, r.quote) for r in claim.evidence):
                self.error("value_not_in_evidence", path,
                           f"value {claim.value:g} does not appear in its evidence")  # fmt: skip
            self.unit(path, claim, found)
        if not found:
            return
        self.horizon(path, claim, found, value_at)
        self.history_and_scenario(path, claim, found)
        self.direction(path, claim, quotes)
        self.indicator(path, claim)

    def unit(
        self, path: str, claim: ForecastClaim, found: list[tuple[EvidenceRef, _Located]]
    ) -> None:
        if claim.unit is None:
            self.error("missing_unit", path, f"value {claim.value:g} has no unit")
            return
        if claim.unit not in UNITS:
            self.error("unknown_unit", path, f"unit {claim.unit!r} is not a recognised unit")
            return
        assert claim.value is not None
        checked = []
        for ref, loc in found:
            quote = _norm(ref.quote)
            for s, e in _value_spans(claim.value, quote):
                checked.append(
                    self._unit_matches(claim.unit, quote[:s], quote[e:], loc.sentence_text())
                )
        if checked and not any(checked):
            self.error("unit_mismatch", path,
                       f"unit {claim.unit!r} is not what the evidence states next to {claim.value:g}")  # fmt: skip

    @staticmethod
    def _unit_matches(unit: str, before: str, after: str, sentence: str) -> bool:
        def stated(name: str) -> bool:
            return bool(_UNIT_SUFFIX[name].match(after))

        other_percentish = stated("percentage_points") or stated("basis_points")
        if unit == "percent":
            return stated("percent") and not other_percentish
        if unit == "percent_of_gdp":
            return stated("percent") and not other_percentish and "gdp" in sentence.lower()
        if unit in ("percentage_points", "basis_points"):
            return stated(unit)
        if unit in ("nzd_billion", "nzd_million"):
            return bool(_DOLLAR_PREFIX.search(before)) and stated(unit)
        if unit == "nzd":
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
        years, months = _horizon_years(horizon), {m.lower()[:3] for m in _MONTH.findall(horizon)}
        quarters = set(_QUARTER_LABEL.findall(horizon))
        if not (years or months or quarters):
            self.warn("horizon_without_period", path, f"horizon {horizon!r} names no period")
        near = " ".join(loc.near_text() for _, loc in found)
        near_months = {m.lower()[:3] for m in _MONTH.findall(near)}
        missing = [str(y) for y in dict.fromkeys(years) if not _year_stated(y, near)]
        missing += [m for m in sorted(months) if m not in near_months]
        missing += [f"Q{q}" for q in sorted(quarters) if f"q{q}" not in near.lower()]
        if missing:
            self.error("horizon_not_supported", path,
                       f"horizon {horizon!r} is not stated near the quote ({', '.join(missing)})")  # fmt: skip
        clauses = [loc.clause_at(at) for loc, at in value_at] or [
            loc.sentence_text() for _, loc in found
        ]
        horizon_fiscal = bool(_FISCAL.search(horizon))
        if (
            any(_FISCAL.search(c) for c in clauses)
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
        evidence_basis = {_basis(c) for c in clauses} - {None}
        claim_basis = _basis(horizon) or _basis(
            f"{claim.indicator_label} {claim.qualification or ''}"
        )
        if len(evidence_basis) == 1:
            (stated,) = evidence_basis
            if claim_basis is not None and claim_basis != stated:
                self.error("period_basis_mismatch", path,
                           f"evidence describes a {stated} change; horizon {horizon!r} does not")  # fmt: skip

    def history_and_scenario(
        self, path: str, claim: ForecastClaim, found: list[tuple[EvidenceRef, _Located]]
    ) -> None:
        sentences = " ".join(loc.sentence_text() for _, loc in found)
        if not _FORWARD.search(sentences):
            self.error("historical_not_forecast", path,
                       "no forward-looking language in the cited sentence (a historical observation?)")  # fmt: skip
        else:
            years = _horizon_years(claim.horizon)
            published = self.ctx.published_on
            if years and published is not None and max(years) < published.year:
                self.error("historical_not_forecast", path,
                           f"horizon {claim.horizon!r} ends before publication ({published.isoformat()})")  # fmt: skip
        scenario_context = " ".join(f"{loc.heading} {loc.sentence_text()}" for _, loc in found)
        if claim.scenario is None and _SCENARIO.search(scenario_context):
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


def verify(
    summary: OutlookSummary,
    sections: Mapping[int, SectionText | str],
    context: VerificationContext | None = None,
) -> VerificationReport:
    ctx = context or VerificationContext()
    resolved = {k: v if isinstance(v, SectionText) else SectionText(v) for k, v in sections.items()}
    c = _Checker(summary, resolved, ctx)
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
    for ordinal in ctx.injection_ordinals:
        c.warn("injection_suspected_section", f"section[{ordinal}]",
               "section text resembles instructions to a model")  # fmt: skip
    return VerificationReport(tuple(c.errors), tuple(c.warnings))
