"""Human-reviewed gold for one document version, and scoring with honest denominators (Phase 4Q). Calls no model.

Phase 4O's gold could not show a good result: its five forecasts were all expected rejections, and it left out third-party
forecasts. An extension sorts each item into one of four groups, so each is scored for what it is: accepted-eligible claims
and third-party forecasts form the recall denominator, expected rejections and ambiguous items sit outside it.

Gold must never be fitted to a model's output. `write_worksheet` builds the reviewer's worksheet from the document alone, and
an extension is refused unless a named person reviewed it and states it was written without seeing model output. That
statement is an attestation, not something this code can prove.

Three views are scored. "accepted" follows the live rule: one failed claim rejects the whole summary, so the view is empty.
"raw" is every fact, forecast and decision emitted; statements and guidance are not scored. "clean claims" is a labelled hypothetical for the per-claim design: it changes no status and
makes nothing displayable. Precision counts a claim once per gold item, and an emitted expected rejection or a claim outside
the gold counts against it. An empty denominator is unmeasured, never a pass. Reports hold numbers only, no text.
"""

from __future__ import annotations

import html
import os
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from nzstats.research import issuers
from nzstats.research.contract import IssuerRole, OutlookSummary
from nzstats.research.summarise import load_sections
from nzstats.research.verify import _YEAR, VerificationContext, verify

Category = Literal["accepted_eligible", "expected_rejection", "ambiguous", "third_party_forecast"]
CATEGORIES: tuple[str, ...] = (
    "accepted_eligible",
    "third_party_forecast",
    "expected_rejection",
    "ambiguous",
)
_IN_RECALL = {"accepted_eligible", "third_party_forecast"}
_CANDIDATE = re.compile(r"\d|forecast|expect|project|\bwill\b|\bdecision\b|voted", re.IGNORECASE)
VIEW_LABELS = {
    "accepted": "Accepted: follows the live rule, so one failed claim empties it",
    "raw": "Raw: all facts, forecasts and decisions emitted, passed or not. Statements and guidance are not scored",
    "clean_claims_hypothetical": "Clean claims, hypothetical: changes no status and makes nothing displayable",
}


class GoldExtensionError(ValueError):
    """Fixed, content-free refusal: the file's content is never repeated."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


_AI_REVIEWER = re.compile(
    r"\b(?:claude|codex|gpt|chatgpt|openai|anthropic|gemini|llm|ai)\b", re.IGNORECASE
)


class ExtensionItem(_Strict):
    id: str = Field(min_length=1)
    category: Category
    kind: Literal["fact", "forecast", "decision"]
    terms: tuple[str, ...] = Field(min_length=1)  # words a claim about this item must use
    value: float | None = None
    unit: str | None = None
    period_as_stated: str | None = None
    issuer_role: IssuerRole | None = None
    issuer: str | None = None
    expected_reason: str | None = None

    @model_validator(mode="after")
    def _well_formed(self) -> ExtensionItem:
        if self.category == "expected_rejection" and not self.expected_reason:
            raise ValueError("an expected rejection must say why")
        if not all(term.strip() for term in self.terms):
            raise ValueError("a term may not be blank")
        if self.category == "third_party_forecast" and not (self.issuer and self.issuer.strip()):
            raise ValueError("a third-party forecast must name its issuer")
        if (
            self.category == "third_party_forecast"
            and self.issuer_role is not IssuerRole.THIRD_PARTY
        ):
            raise ValueError("a third-party forecast must have the third-party role")
        if self.category == "third_party_forecast" and self.kind != "forecast":
            raise ValueError("a third-party forecast must be a forecast")
        return self


class GoldExtension(_Strict):
    annotator: str = Field(min_length=1)
    reviewed_by: str = Field(min_length=1)
    reviewed_on: date
    written_without_model_output: Literal[True]
    version_id: int = Field(ge=1)
    text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    items: tuple[ExtensionItem, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _reviewed_by_a_person(self) -> GoldExtension:
        if not self.annotator.strip() or not self.reviewed_by.strip():
            raise ValueError("the annotator and reviewer must be named")
        if _AI_REVIEWER.search(self.reviewed_by):
            raise ValueError("the reviewer must be a person")
        if self.reviewed_on > datetime.now(UTC).date() + timedelta(
            days=1
        ):  # Auckland is ahead of UTC
            raise ValueError("the review date is in the future")
        if len({item.id for item in self.items}) != len(self.items):
            raise ValueError("item ids must be unique")
        return self


def load_extension(path: Path) -> GoldExtension:
    try:
        return GoldExtension.model_validate_json(Path(path).read_bytes())
    except (OSError, ValueError, ValidationError) as exc:
        raise GoldExtensionError(f"the gold extension is not valid: {type(exc).__name__}") from None


@dataclass(frozen=True)
class Ratio:
    numerator: int
    denominator: int

    @property
    def text(self) -> str:
        if not self.denominator:
            return "unmeasured (0/0)"
        return f"{self.numerator}/{self.denominator}"

    def to_json(self) -> dict[str, object]:
        return {"numerator": self.numerator, "denominator": self.denominator, "text": self.text}


@dataclass(frozen=True)
class ViewScore:
    claims: int
    precision: Ratio
    recall: Ratio
    numerical_accuracy: Ratio
    period_exact: Ratio
    issuer_accuracy: Ratio
    unmatched: int
    ambiguous: int
    expected_rejections: int
    duplicates: int

    def to_json(self, label: str) -> dict[str, object]:
        return {"label": label, "claims": self.claims, "unmatched": self.unmatched, "ambiguous": self.ambiguous,
                "expected_rejections": self.expected_rejections, "duplicates": self.duplicates, "precision": self.precision.to_json(),
                "recall": self.recall.to_json(), "numerical_accuracy": self.numerical_accuracy.to_json(),
                "period_exact": self.period_exact.to_json(), "issuer_accuracy": self.issuer_accuracy.to_json()}  # fmt: skip


@dataclass(frozen=True)
class ExtensionReport:
    version_id: int
    passed: bool
    gold_counts: dict[str, int]
    views: dict[str, ViewScore] = field(default_factory=dict)

    @property
    def expected_rejections_emitted(self) -> int:
        return self.views["raw"].expected_rejections

    def to_json(self) -> dict[str, object]:
        return {"version_id": self.version_id, "passed": self.passed, "gold_counts": self.gold_counts,
                "views": {name: view.to_json(VIEW_LABELS[name]) for name, view in self.views.items()}}  # fmt: skip


@dataclass(frozen=True)
class _Emitted:
    kind: str
    text: str
    value: float | None
    unit: str | None
    period: str | None
    issuer: str | None
    role: IssuerRole | None
    failed: bool


def _flat(text: str | None) -> str:
    return " ".join((text or "").lower().split())


def _without_year(period: str | None) -> str:
    return _flat(_YEAR.sub("", period or ""))


def _same_value(a: float | None, b: float | None) -> bool:
    return a is not None and b is not None and abs(a - b) < 1e-9


def _emitted(summary: OutlookSummary, failed_paths: set[str]) -> list[_Emitted]:
    out = []
    for i, f in enumerate(summary.facts):
        out.append(
            _Emitted(
                "fact",
                f.text,
                f.value,
                f.unit,
                f.period,
                f.source,
                None,
                f"facts[{i}]" in failed_paths,
            )
        )
    for i, c in enumerate(summary.forecasts):
        text = f"{c.indicator_label} {c.indicator.value} {c.qualification or ''}"
        out.append(_Emitted("forecast", text, c.value, c.unit, c.horizon, c.issuer, c.issuer_role,
                            f"forecasts[{i}]" in failed_paths))  # fmt: skip
    for i, d in enumerate(summary.decisions):
        out.append(_Emitted("decision", f"{d.decision_maker} {d.instrument} {d.action.value}", d.rate, None, None,
                            d.decision_maker, None, f"decisions[{i}]" in failed_paths))  # fmt: skip
    return out


def _years(period: str | None) -> set[str]:
    return {m.group() for m in _YEAR.finditer(period or "")}


def _same_period(claim: str | None, item: str | None) -> bool:
    """The same period. A year the gold omits does not matter here (period exactness reports it); one it states must match."""
    wanted = _years(item)
    if wanted and _years(claim) != wanted:
        return False
    return _without_year(claim) == _without_year(item)


def _is_about(claim: _Emitted, item: ExtensionItem) -> bool:
    """The same subject and period, whatever number it states."""
    if claim.kind != item.kind or not all(_flat(t) in _flat(claim.text) for t in item.terms):
        return False
    return item.period_as_stated is None or _same_period(claim.period, item.period_as_stated)


def _match(claim: _Emitted, items: tuple[ExtensionItem, ...]) -> ExtensionItem | None:
    """The least favourable item this claim fits, whatever the gold's order. A broad ambiguous item must not hide an error."""

    def rank(item: ExtensionItem) -> tuple[int, str]:
        right = _value_right(claim, item)
        if item.category == "expected_rejection":
            return (0 if right else 3, item.id)
        return (1 if right else 2, item.id) if item.category in _IN_RECALL else (4, item.id)

    about = [
        item
        for item in items
        if _is_about(claim, item) and (item.category != "ambiguous" or _value_right(claim, item))
    ]
    return min(about, key=rank, default=None)


def _value_right(claim: _Emitted, item: ExtensionItem) -> bool:
    if item.value is None:
        return claim.value is None
    # A decision has a rate but no unit field, so its unit cannot be compared.
    if item.unit is not None and claim.kind != "decision" and item.unit != claim.unit:
        return False
    return _same_value(claim.value, item.value)


def _issuer_right(claim: _Emitted, item: ExtensionItem) -> bool:
    if claim.role is not item.issuer_role:
        return False
    if not claim.issuer or not item.issuer:
        return not item.issuer
    want, got = issuers.organisation_of(item.issuer), issuers.organisation_of(claim.issuer)
    return want == got if want or got else _flat(item.issuer) in _flat(claim.issuer)


def _score(claims: list[_Emitted], items: tuple[ExtensionItem, ...]) -> ViewScore:
    in_recall = [i for i in items if i.category in _IN_RECALL]
    found: set[str] = set()
    valued: set[str] = set()
    right = matched = unmatched = ambiguous = rejected = numbers = numbers_right = duplicates = 0
    periods = periods_right = issued = issued_right = 0
    for claim in claims:
        item = _match(claim, items)
        if item is None:
            unmatched += 1
        elif item.category == "ambiguous":
            ambiguous += 1
        elif item.category == "expected_rejection":
            rejected += 1
        else:
            matched += 1
            good = _value_right(claim, item)
            issuer_checked = item.kind == "forecast" and item.issuer_role is not None
            correct = good and (not issuer_checked or _issuer_right(claim, item))
            if correct and item.id in found:
                duplicates += 1  # stated again: it is not a further correct claim
            elif correct:
                right += 1
                found.add(item.id)
            if not (good and item.id in valued) and (
                item.value is not None or claim.value is not None
            ):
                numbers += 1
                numbers_right += good
            if good:
                valued.add(item.id)
            if item.period_as_stated is not None:
                periods += 1
                periods_right += _flat(claim.period) == _flat(item.period_as_stated)
            if issuer_checked:
                issued += 1
                issued_right += _issuer_right(claim, item)
    return ViewScore(
        len(claims), Ratio(right, matched + unmatched + rejected), Ratio(len(found), len(in_recall)),
        Ratio(numbers_right, numbers), Ratio(periods_right, periods), Ratio(issued_right, issued),
        unmatched, ambiguous, rejected, duplicates,
    )  # fmt: skip


def score_extension(
    conn: sqlite3.Connection,
    summary: OutlookSummary,
    extension: GoldExtension,
    context: VerificationContext,
) -> ExtensionReport:
    """One summary against one reviewed extension, rerunning the verifier. Reads and changes no stored status."""
    row = conn.execute(
        "SELECT text_sha256 FROM research_document_version WHERE id = ?", (extension.version_id,)
    ).fetchone()
    if (
        row is None
        or row["text_sha256"] != extension.text_sha256
        or summary.version_id != extension.version_id
    ):
        raise GoldExtensionError("the gold extension was not written for this document version")
    report = verify(summary, load_sections(conn, extension.version_id), context)
    failed = {p.path.split(".")[0] for p in report.errors}
    claims = _emitted(summary, failed)
    counts = {c: sum(i.category == c for i in extension.items) for c in CATEGORIES}
    views = {
        "accepted": _score(claims if report.passed else [], extension.items),
        "raw": _score(claims, extension.items),
        "clean_claims_hypothetical": _score([c for c in claims if not c.failed], extension.items),
    }
    return ExtensionReport(extension.version_id, report.passed, counts, views)


def write_worksheet(conn: sqlite3.Connection, version_id: int, out: Path) -> int:
    """A private review sheet of the sentences that could hold a claim, from the document alone. Returns how many."""
    row = conn.execute(
        "SELECT superseded_at, purged_at FROM research_document_version WHERE id = ?", (version_id,)
    ).fetchone()
    if row is None or row["superseded_at"] or row["purged_at"]:
        raise GoldExtensionError("no current document version to review")
    rows = []
    for ordinal, section in load_sections(conn, version_id).items():
        for sentence in re.split(r"(?<=[.!?])\s+", " ".join(section.text.split())):
            if _CANDIDATE.search(sentence):
                rows.append((section.page_start, ordinal, sentence))
    boxes = " ".join(f"[ ] {c}" for c in CATEGORIES)
    body = "\n".join(
        f"<tr><td>{page or ''}</td><td>{ordinal}</td><td>{html.escape(text)}</td><td>{boxes}<br>Issuer: ____ Period as written: ____</td></tr>"
        for page, ordinal, text in rows
    )
    page = (
        "<!doctype html><meta charset=utf-8><title>Gold review worksheet</title>"
        "<style>body{font:15px system-ui;margin:2em}td,th{border:1px solid #bbb;padding:6px;vertical-align:top;text-align:left}"
        "table{border-collapse:collapse;width:100%}</style>"
        f"<h1>Gold review worksheet: version {version_id}</h1>"
        "<p>Private and local. Built from the document alone. Read the original PDF, and do not open any model output first."
        " Copy periods exactly as written. An item may be left out.</p>"
        "<p>[ ] Written without seeing model output. Reviewer: ____________ Date: ____________</p>"
        f"<table><tr><th>Page</th><th>Section</th><th>Sentence</th><th>Your reading</th></tr>{body}</table>"
    )
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)  # an existing file keeps its old mode otherwise
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(page)
    return len(rows)
