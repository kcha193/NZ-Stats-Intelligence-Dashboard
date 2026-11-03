"""Version-bound gold packs for institutional reports, and offline probes of the verifier (Phase 4Q). Calls no model.

A pack is one reading of one stored document version, for its owner to review, kept outside Git because it quotes the document. It binds to
the version's id and hashes, so gold written for one report can never score another, and a new report needs its own.

`check_pack` tests the gold against the stored text: the publication and document dates, each quote on its stated page,
its value and reference period inside the quote, its issuer named near the quote, and each relative date resolved from
the document date. The publication date is the wrong anchor: "next week" in a report dated Thursday and published the
following Monday counts from that Thursday.

`probe_pack` turns each true item into a claim, corrupts it in known ways and runs the real verifier, so what the verifier
misses is measured. A miss is a limit to report. It never justifies changing a threshold, and a probe never scores a model.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from nzstats.research.contract import (
    Direction,
    EvidenceRef,
    ForecastClaim,
    Indicator,
    IssuerRole,
    ModelProvenance,
    OutlookSummary,
    PolicyAction,
    PolicyDecision,
    ReportedFact,
    SectionText,
    Statement,
)
from nzstats.research.issuers import organisation_of
from nzstats.research.summarise import load_sections
from nzstats.research.verify import VerificationContext, verify

MAX_RELATIVE_DAYS = 14
ISSUER_BEFORE_CHARS = 1500
ISSUER_AFTER_CHARS = 200  # a figure's source line follows the sentence it supports
QUARTERS = {"march": 1, "june": 2, "september": 3, "december": 4}
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
UNSUPPORTED_YEARS = range(
    2025, 1999, -1
)  # an added year is the latest of these the document never states
MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
MINUS = "-\u2212"  # hyphen-minus and the typographic minus
WRONG_ISSUERS = (
    "International Monetary Fund",
    "Reserve Bank of Australia",
)  # third parties the verifier knows by name


class GoldPackError(ValueError):
    """Fixed, content-free refusal: the pack's content is never repeated."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class GoldItem(_Strict):
    id: str = Field(min_length=1)
    kind: Literal["fact", "forecast", "decision", "view"]
    issuer: str = Field(min_length=1)
    issuer_role: IssuerRole
    named_as: str = Field(min_length=1)  # the words in the document that name the issuer
    page: int = Field(ge=1)
    quote: str = Field(min_length=8, max_length=600)
    text: str = Field(min_length=1)
    value: float | None = None
    unit: str | None = None
    period_as_stated: str | None = None  # the words used; a missing year stays missing (Phase 4O)
    period_resolved: str | None = None  # e.g. 2026Q3: the reading, kept apart from the words
    indicator: Indicator | None = None
    direction: Direction = Direction.UNCLEAR
    action: PolicyAction | None = None
    decided_on: date | None = None
    vote_for: int | None = None
    vote_against: int | None = None
    decision_maker: str | None = None

    @model_validator(mode="after")
    def _a_decision_is_complete(self) -> GoldItem:
        if self.kind == "decision" and (
            self.action is None or self.value is None or self.decided_on is None
        ):
            raise ValueError("a decision needs its action, rate and date")
        return self

    @model_validator(mode="after")
    def _whole_vote(self) -> GoldItem:
        if (self.vote_for is None) != (self.vote_against is None):
            raise ValueError("a vote is recorded as both counts or neither")
        return self


class GoldRelativeDate(_Strict):
    id: str = Field(min_length=1)
    page: int = Field(ge=1)
    quote: str = Field(min_length=8, max_length=600)
    phrase: str = Field(min_length=1)
    resolved: date
    calendar_quote: str | None = None  # the document's own calendar line, where it has one


class AccuracyPack(_Strict):
    annotator: str = Field(min_length=1)
    annotated_on: date
    version_id: int = Field(ge=1)
    text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    document_date: date
    published_on: date
    foreign_quote: str = Field(
        min_length=8, max_length=600
    )  # from an earlier report; must not be in this one
    items: tuple[GoldItem, ...] = Field(min_length=1)
    relative_dates: tuple[GoldRelativeDate, ...] = ()


def load_pack(path: Path) -> AccuracyPack:
    try:
        return AccuracyPack.model_validate_json(Path(path).read_bytes())
    except (OSError, ValueError, ValidationError) as exc:
        raise GoldPackError(f"the gold pack is not valid: {type(exc).__name__}") from None


@dataclass(frozen=True)
class PackProblem:
    item: str
    code: str


@dataclass(frozen=True)
class PackReport:
    version_id: int
    items: int
    relative_dates: int
    problems: tuple[PackProblem, ...]

    def to_json(self) -> dict[str, object]:
        return {"version_id": self.version_id, "items": self.items, "relative_dates": self.relative_dates,
                "ok": not self.problems, "problems": [{"item": p.item, "code": p.code} for p in self.problems]}  # fmt: skip


@dataclass(frozen=True)
class ProbeResult:
    item: str
    kind: str
    mutation: str
    expected: Literal["accepted", "rejected"]
    caught: bool  # the verifier raised an error on this claim
    codes: tuple[str, ...]
    measured: bool = (
        True  # False when the true claim was already rejected, so a corruption proves nothing
    )


@dataclass(frozen=True)
class ProbeReport:
    version_id: int
    results: tuple[ProbeResult, ...]

    @property
    def caught(self) -> int:
        return sum(r.caught for r in self.results if r.expected == "rejected" and r.measured)

    @property
    def missed(self) -> int:
        return sum(not r.caught for r in self.results if r.expected == "rejected" and r.measured)

    @property
    def not_measured(self) -> int:
        return sum(not r.measured for r in self.results)

    @property
    def false_rejections(self) -> int:
        return sum(r.caught for r in self.results if r.expected == "accepted")

    def to_json(self) -> dict[str, object]:
        return {"version_id": self.version_id, "caught": self.caught, "missed": self.missed,
                "not_measured": self.not_measured, "false_rejections": self.false_rejections,
                "results": [{"item": r.item, "kind": r.kind, "mutation": r.mutation, "expected": r.expected,
                             "caught": r.caught, "measured": r.measured, "codes": list(r.codes)}
                            for r in self.results]}  # fmt: skip


def _flat(text: str) -> str:
    return " ".join(text.replace("’", "'").replace("‘", "'").split())


def _bound(conn: sqlite3.Connection, pack: AccuracyPack) -> sqlite3.Row:
    row = conn.execute(
        "SELECT v.text_sha256, v.content_sha256, v.superseded_at, v.purged_at, p.current_version_id, p.title,"
        " p.published_on, i.key AS institution, i.name AS institution_name"
        " FROM research_document_version v JOIN research_publication p ON p.id = v.publication_id"
        " JOIN research_institution i ON i.id = p.institution_id WHERE v.id = ?",
        (pack.version_id,),
    ).fetchone()
    if (
        row is None
        or row["text_sha256"] != pack.text_sha256
        or row["content_sha256"] != pack.content_sha256
    ):
        raise GoldPackError("the gold pack was not written for this stored document version")
    if row["superseded_at"] or row["purged_at"] or row["current_version_id"] != pack.version_id:
        raise GoldPackError("the gold pack's document version is no longer current")
    return row


def _find(sections: dict[int, SectionText], page: int, quote: str) -> tuple[int, str] | None:
    """The section on `page` holding `quote`, and the flattened text around the quote there."""
    wanted = _flat(quote)
    for ordinal, section in sections.items():
        last = section.page_end or section.page_start
        if section.page_start is None or last is None or not section.page_start <= page <= last:
            continue
        flat = _flat(section.text)
        at = flat.find(wanted)
        if at >= 0:
            end = at + len(wanted) + ISSUER_AFTER_CHARS
            return ordinal, flat[max(0, at - ISSUER_BEFORE_CHARS) : end]
    return None


def _has_number(value: float, quote: str) -> bool:
    """True when `quote` holds `value` as a whole signed number: 2.9 is not found in "-2.9", nor 3.5 as a sign in "3.0-3.5"."""
    wanted = Decimal(f"{value:.10f}")
    for found in re.finditer(
        rf"(?<![\d.])(?P<sign>(?<![\w.])[{MINUS}])?(?P<number>\d+(?:\.\d+)?)(?!\.?\d)",
        quote.replace(",", ""),
    ):
        number = Decimal(found["number"])
        if (-number if found["sign"] else number) == wanted:
            return True
    return False


def _period_conflict(stated: str | None, resolved: str | None) -> bool:
    """A stated quarter, and any stated year, must agree with the resolved quarter. A year the words omit is not invented."""
    words = (stated or "").lower()
    parsed = re.fullmatch(r"(\d{4})Q([1-4])", resolved or "")
    if parsed is None:
        return False
    year, quarter = int(parsed.group(1)), int(parsed.group(2))
    direct = re.search(r"\b(\d{4})\s*q([1-4])\b", words)
    named = re.search(
        r"(march|june|september|december)\b(?:\s+(\d{4}))?(?:\s+quarter)?(?:\s+(\d{4}))?", words
    )
    if direct:
        return (int(direct.group(1)), int(direct.group(2))) != (year, quarter)
    if not (named and "quarter" in words):
        return False
    years = {int(y) for y in (named.group(2), named.group(3)) if y}
    return QUARTERS[named.group(1)] != quarter or bool(years and year not in years)


def _check_item(sections: dict[int, SectionText], item: GoldItem) -> list[str]:
    found = _find(sections, item.page, item.quote)
    if found is None:
        return ["quote_not_found"]
    codes = []
    if item.value is not None and not _has_number(item.value, item.quote):
        codes.append("value_not_in_quote")
    if (
        item.period_as_stated
        and _flat(item.period_as_stated).lower() not in _flat(item.quote).lower()
    ):
        codes.append("period_not_in_quote")
    if _period_conflict(item.period_as_stated, item.period_resolved):
        codes.append("period_resolved_mismatch")
    if _flat(item.named_as).lower() not in found[1].lower():
        codes.append("issuer_not_near_quote")
    return codes


def _relative_candidates(phrase: str, document: date) -> set[date] | None:
    """The dates a phrase naming a weekday can mean from the document date, or None when it names no weekday.

    The weekday is the first one after the document date, never the document day itself. For "next <weekday>" that first one
    may fall in the document's own week, and some writers mean the same weekday of the following week, so both are allowed.
    """
    words = re.findall(r"[a-z]+", phrase.lower())
    named = next((day for day in WEEKDAYS if day in words), None)
    if named is None:
        return None
    ahead = (WEEKDAYS.index(named) - document.weekday() - 1) % 7 + 1
    first = document + timedelta(days=ahead)
    if "next" in words and first.isocalendar()[:2] == document.isocalendar()[:2]:
        return {first, first + timedelta(days=7)}
    return {first}


def _calendar_dates(line: str) -> set[tuple[int, int]]:
    """The (month, day) pairs a calendar line states, as "4 Nov", "4 November" or "Nov 4". The line carries no year."""
    month = rf"(?P<m>{'|'.join(MONTHS)})[a-z]*\.?"
    found = [
        (m["m"], m["d"]) for m in re.finditer(rf"\b(?P<d>\d{{1,2}})\s+{month}\b", line.lower())
    ]
    found += [
        (m["m"], m["d"]) for m in re.finditer(rf"\b{month}\s+(?P<d>\d{{1,2}})\b", line.lower())
    ]
    return {(MONTHS.index(m) + 1, int(d)) for m, d in found}


def _check_relative(
    sections: dict[int, SectionText], pack: AccuracyPack, item: GoldRelativeDate
) -> list[str]:
    if _find(sections, item.page, item.quote) is None:
        return ["quote_not_found"]
    codes = []
    phrase = _flat(item.phrase).lower()
    if phrase not in _flat(item.quote).lower():
        codes.append("phrase_not_in_quote")
    named = next((day for day in WEEKDAYS if day in phrase), None)
    if named and item.resolved.strftime("%A").lower() != named:
        codes.append("weekday_mismatch")
    candidates = _relative_candidates(phrase, pack.document_date)
    if named and candidates is not None and item.resolved not in candidates:
        codes.append("relative_date_mismatch")
    gap = (item.resolved - pack.document_date).days
    if gap <= 0:
        codes.append("relative_date_not_after_document")
    elif gap > MAX_RELATIVE_DAYS:
        codes.append("relative_date_too_far")
    if item.calendar_quote:
        whole = " ".join(_flat(s.text) for s in sections.values())
        stated = _calendar_dates(item.calendar_quote)
        if _flat(item.calendar_quote) not in whole:
            codes.append("calendar_quote_not_found")
        elif not stated:
            codes.append("calendar_quote_has_no_date")
        elif (item.resolved.month, item.resolved.day) not in stated:
            codes.append("calendar_date_mismatch")
    return codes


def check_pack(conn: sqlite3.Connection, pack: AccuracyPack) -> PackReport:
    """Test the gold against the stored text; raises `GoldPackError` when it is bound to another document."""
    row = _bound(conn, pack)
    sections = load_sections(conn, pack.version_id)
    problems = []
    day = pack.document_date
    if f"{day.day} {day:%B} {day.year}" not in row["title"]:
        problems.append(PackProblem("document", "document_date_not_in_title"))
    if row["published_on"] != pack.published_on.isoformat():
        problems.append(PackProblem("document", "published_on_mismatch"))
    if pack.document_date > pack.published_on:
        problems.append(PackProblem("document", "document_date_after_publication"))
    if _flat(pack.foreign_quote) in " ".join(_flat(s.text) for s in sections.values()):
        problems.append(PackProblem("document", "foreign_quote_present"))
    for item in pack.items:
        problems += [PackProblem(item.id, code) for code in _check_item(sections, item)]
    for relative in pack.relative_dates:
        problems += [
            PackProblem(relative.id, code) for code in _check_relative(sections, pack, relative)
        ]
    return PackReport(pack.version_id, len(pack.items), len(pack.relative_dates), tuple(problems))


def _evidence(version: int, ordinal: int, page: int, quote: str) -> tuple[EvidenceRef, ...]:
    return (EvidenceRef(version_id=version, section_ordinal=ordinal, page=page, quote=quote),)


def _claim(
    item: GoldItem, evidence: tuple[EvidenceRef, ...], **over: object
) -> ForecastClaim | ReportedFact | PolicyDecision | Statement:
    if item.kind == "view":
        return Statement(text=item.text, evidence=evidence)
    if item.kind == "fact":
        fields: dict[str, object] = {"text": item.text, "source": item.issuer, "value": item.value, "unit": item.unit,
                                     "period": item.period_as_stated, "evidence": evidence}  # fmt: skip
        return ReportedFact(**{**fields, **over})
    if item.kind == "forecast":
        fields = {"indicator": item.indicator or Indicator.OTHER, "indicator_label": item.text,
                  "horizon": item.period_as_stated or "", "value": item.value, "unit": item.unit,
                  "direction": item.direction, "issuer": item.issuer, "issuer_role": item.issuer_role,
                  "evidence": evidence}  # fmt: skip
        return ForecastClaim(**{**fields, **over})
    fields = {"action": item.action, "rate": item.value, "decided_on": item.decided_on, "vote_for": item.vote_for,
              "vote_against": item.vote_against, "decision_maker": item.decision_maker or item.issuer,
              "evidence": evidence}  # fmt: skip
    return PolicyDecision(**{**fields, **over})


def _wrong_issuer(item: GoldItem, institution: str, institution_name: str) -> dict[str, object]:
    """Swap an author forecast for a third party, or a third-party one for the document's own author, as the verifier knows them.

    Both sides must be organisations the verifier recognises, and not the author when a third party is wanted: otherwise the
    claim is rejected for being internally impossible and the probe measures nothing about attribution. Empty when no valid swap exists.
    """
    if item.issuer_role is IssuerRole.AUTHOR:
        other = next(
            (n for n in WRONG_ISSUERS if organisation_of(n) not in (None, institution)), None
        )
        return {"issuer": other, "issuer_role": IssuerRole.THIRD_PARTY} if other else {}
    if organisation_of(institution_name) == institution:
        return {"issuer": institution_name, "issuer_role": IssuerRole.AUTHOR}
    return {}


def _unsupported_year(document_text: str) -> str | None:
    """The latest year in `UNSUPPORTED_YEARS` that the document never states, or None when it states them all."""
    stated = set(re.findall(r"\b\d{4}\b", document_text))
    return next((str(year) for year in UNSUPPORTED_YEARS if str(year) not in stated), None)


def _mutations(
    item: GoldItem, document_text: str, institution: str, institution_name: str
) -> dict[str, dict[str, object]]:
    if item.kind == "view":
        return {}
    value = (item.value or 0) + 1.0
    if item.kind == "decision":
        changes: dict[str, dict[str, object]] = {
            "wrong_rate": {"rate": value},
            "wrong_date": {"decided_on": date(2031, 3, 3)},
        }
        if item.vote_for is not None and item.vote_against is not None:
            changes["wrong_vote"] = {"vote_for": item.vote_for + 1}
        return changes
    changes = {}
    if item.period_as_stated:
        period = "period" if item.kind == "fact" else "horizon"
        changes["wrong_period"] = {period: "March 2031"}
        year = _unsupported_year(document_text)
        # Adding a year already stated, by the period or by the document, corrupts nothing: skip rather than score it as a miss
        if year and not re.search(r"\b\d{4}\b", item.period_as_stated):
            changes["added_year"] = {period: f"{item.period_as_stated} {year}"}
    if item.value is not None:
        changes["wrong_value"] = {"value": value}
    wrong = _wrong_issuer(item, institution, institution_name)
    if item.kind == "forecast" and wrong:
        changes["wrong_issuer"] = wrong
    return changes


def _errors_on(
    pack: AccuracyPack, sections: dict[int, SectionText], institution: str, item: GoldItem,
    ordinal: int, claim: ForecastClaim | ReportedFact | PolicyDecision | Statement,
) -> tuple[str, ...]:  # fmt: skip
    name = {"fact": "facts", "forecast": "forecasts", "decision": "decisions", "view": "drivers"}[
        item.kind
    ]
    summary = OutlookSummary(
        version_id=pack.version_id, contract_version=2,
        outlook=Statement(text="Probe statement.", evidence=_evidence(pack.version_id, ordinal, item.page, item.quote)),
        indicators=(claim.indicator,) if isinstance(claim, ForecastClaim) else (),
        provenance=ModelProvenance(provider="none", model="none", prompt_version="none", processing_version="none",
                                   input_text_sha256=pack.text_sha256, created_at=datetime.now(UTC)),
        **{name: (claim,)},
    )  # fmt: skip
    report = verify(
        summary,
        sections,
        VerificationContext(published_on=pack.published_on, institution=institution),
    )
    return tuple(sorted({p.code for p in report.errors if p.path.startswith(f"{name}[0]")}))


def _probes(
    pack: AccuracyPack,
    item: GoldItem,
    ordinal: int,
    document_text: str,
    institution: tuple[str, str],
) -> list[tuple[str, ForecastClaim | ReportedFact | PolicyDecision | Statement]]:
    good = _evidence(pack.version_id, ordinal, item.page, item.quote)
    claims = [("baseline", _claim(item, good))]
    claims += [
        (name, _claim(item, good, **over))
        for name, over in _mutations(item, document_text, *institution).items()
    ]
    claims.append(
        ("wrong_page", _claim(item, _evidence(pack.version_id, ordinal, item.page + 1, item.quote)))
    )
    claims.append(
        (
            "foreign_evidence",
            _claim(item, _evidence(pack.version_id, ordinal, item.page, pack.foreign_quote)),
        )
    )
    return claims


def probe_pack(conn: sqlite3.Connection, pack: AccuracyPack) -> ProbeReport:
    """True claims and corrupted copies through the real verifier. A quote that is not found is skipped: `check_pack` reports it."""
    row = _bound(conn, pack)
    sections = load_sections(conn, pack.version_id)
    results = []
    document_text = " ".join(_flat(s.text) for s in sections.values())
    for item in pack.items:
        found = _find(sections, item.page, item.quote)
        if found is None:
            continue
        clean = True
        for mutation, claim in _probes(
            pack, item, found[0], document_text, (row["institution"], row["institution_name"])
        ):
            codes = _errors_on(pack, sections, row["institution"], item, found[0], claim)
            if mutation == "baseline":
                clean = not codes
                results.append(
                    ProbeResult(item.id, item.kind, mutation, "accepted", bool(codes), codes)
                )
            else:
                results.append(
                    ProbeResult(item.id, item.kind, mutation, "rejected", bool(codes), codes, clean)
                )
    return ProbeReport(pack.version_id, tuple(results))
