"""Real-model evaluation (Phase 3D-A): stored summaries of real documents scored against a human annotation.

The synthetic replay (`evaluate.run_eval`) measures the deterministic layers on hand-written outputs. This module
measures what a real model actually produced for real documents, from what `research summarise` stored: no model is
called and nothing is written. Each summary is re-verified with the current verifier on the stored sections, then
scored with the same functions as the replay, so the metric definitions are identical. Cost and latency are the
recorded `research_llm_usage` rows (retries included), not price-point estimates.

The annotation file is derived from third-party documents, so keep it under `data/` (not in git). Its results are
never merged with `RECORDED_BASELINE`: the documents, the model and the annotator all differ.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from nzstats.research.contract import Indicator, IssuerRole, OutlookSummary, PolicyAction
from nzstats.research.evaluate import (
    PRICE_POINTS,
    EvalReport,
    GoldClaim,
    GoldDecision,
    GoldVersion,
    aggregate,
    score,
)
from nzstats.research.prompt import injection_findings
from nzstats.research.summarise import load_sections
from nzstats.research.verify import UNITS, VerificationContext, resolve_verifier, verify


class AnnotationError(ValueError):
    pass


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GoldForecast(_Strict):
    indicator: Indicator
    horizon: str = Field(min_length=1, max_length=200)
    value: float | None = None
    unit: str | None = None
    scenario: str | None = None
    issuer_role: IssuerRole | None = None  # Phase 4I: whose forecast it is

    @field_validator("unit")
    @classmethod
    def _known_unit(cls, unit: str | None) -> str | None:
        # A unit the contract does not have can never match a model's claim, so numerical fidelity would be
        # wrong without anyone noticing (the Phase 4H file used "people" for "persons").
        if unit is not None and unit not in UNITS:
            raise ValueError(f"unit {unit!r} is not one of the contract's units")
        return unit


class GoldPolicyDecision(_Strict):
    rate: float
    decided_on: date
    action: PolicyAction
    vote_for: int | None = Field(default=None, ge=0)
    vote_against: int | None = Field(default=None, ge=0)


class DocumentAnnotation(_Strict):
    version_id: int = Field(ge=1)
    indicators: tuple[Indicator, ...] = ()
    forecasts: tuple[GoldForecast, ...] = ()
    decisions: tuple[GoldPolicyDecision, ...] = ()
    key_points: tuple[tuple[str, ...], ...] = ()
    note: str | None = None


class AnnotationFile(_Strict):
    annotator: str = Field(min_length=1)
    annotated_on: date
    documents: tuple[DocumentAnnotation, ...] = Field(min_length=1)


def load_annotations(path: Path) -> AnnotationFile:
    try:
        return AnnotationFile.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, ValueError, ValidationError) as exc:
        raise AnnotationError(f"annotation file is not valid: {type(exc).__name__}") from exc


def _gold(doc: DocumentAnnotation) -> GoldVersion:
    return GoldVersion(
        frozenset(i.value for i in doc.indicators),
        tuple(
            GoldClaim(f.indicator.value, f.horizon, f.value, f.unit, f.scenario,
                      f.issuer_role.value if f.issuer_role else None)
            for f in doc.forecasts
        ),
        doc.key_points,
        tuple(
            GoldDecision(d.rate, d.decided_on.isoformat(), d.action.value, d.vote_for, d.vote_against)
            for d in doc.decisions
        ),
    )  # fmt: skip


@dataclass(frozen=True)
class ModelGroup:
    provider: str
    model: str
    prompt_version: str
    documents: int
    provider_errors: int
    recorded_cost_usd: float
    report: EvalReport


@dataclass(frozen=True)
class RealEvalReport:
    annotator: str
    annotated_on: date
    groups: tuple[ModelGroup, ...]
    unsummarised: tuple[int, ...]  # annotated versions with no stored summary

    def to_markdown(self) -> str:
        lines = [
            "Real documents, real model outputs, scored against a human annotation by"
            f" {self.annotator} ({self.annotated_on.isoformat()}). These results are not comparable with the"
            " synthetic replay baseline: the documents, the model and the annotation differ.",
        ]
        if self.unsummarised:
            lines.append(
                f"Annotated but never summarised: versions {', '.join(map(str, self.unsummarised))}."
            )
        for g in self.groups:
            mean = g.recorded_cost_usd / g.documents if g.documents else 0.0
            lines += [
                "",
                f"## {g.provider}/{g.model}, prompt {g.prompt_version}",
                f"{g.documents} documents; {g.provider_errors} provider errors (not scored); recorded cost"
                f" ${g.recorded_cost_usd:.4f} (${mean:.4f} per scored document).",
                "",
                *g.report.to_markdown().splitlines()[
                    1:
                ],  # the replay/live mode line does not apply
            ]
        return "\n".join(lines) + "\n"


def _usage(conn: sqlite3.Connection, summary_id: int) -> tuple[int, int, bool, float, float]:
    row = conn.execute(
        "SELECT COALESCE(SUM(input_tokens), 0), COALESCE(SUM(output_tokens), 0), COALESCE(MAX(usage_estimated), 0),"
        " COALESCE(SUM(latency_ms), 0), COALESCE(SUM(cost_usd), 0) FROM research_llm_usage WHERE summary_id = ?",
        (summary_id,),
    ).fetchone()
    return int(row[0]), int(row[1]), bool(row[2]), float(row[3]), float(row[4])


def evaluate_stored(
    conn: sqlite3.Connection, annotations: AnnotationFile, *, model: str | None = None
) -> RealEvalReport:
    """Score the newest stored summary per (version, provider, model, prompt) for every annotated version.

    Provider errors are counted, not scored; recorded cost covers every attempt, failed ones included.
    """
    gold = {d.version_id: d for d in annotations.documents}
    marks = ",".join("?" * len(gold))
    rows = conn.execute(
        "SELECT s.*, p.published_on, v.purged_at, i.key AS institution FROM research_summary s"
        " JOIN research_document_version v ON v.id = s.version_id"
        " JOIN research_publication p ON p.id = v.publication_id"
        " JOIN research_institution i ON i.id = p.institution_id"
        f" WHERE s.version_id IN ({marks}) ORDER BY s.id DESC",
        tuple(gold),
    ).fetchall()
    # The model filter applies before grouping and before coverage, so one model never inherits another's.
    rows = [r for r in rows if model is None or r["model"] == model]
    grouped: dict[tuple[str, str, str], list[sqlite3.Row]] = defaultdict(list)
    for r in rows:
        grouped[(r["provider"], r["model"], r["prompt_version"])].append(r)
    summarised = {r["version_id"] for r in rows if r["status"] != "provider_error"}

    groups = []
    for (provider, model_name, prompt), members in sorted(grouped.items()):
        report = EvalReport("real")
        errors, cost = 0, 0.0
        scored: set[int] = set()
        for r in members:  # newest first
            in_tok, out_tok, estimated, latency, spent = _usage(conn, r["id"])
            cost += spent
            if r["status"] == "provider_error":
                errors += 1
                continue
            if r["purged_at"] is not None:  # purged: there is nothing left to score
                continue
            if r["version_id"] in scored:  # an older attempt at the same work
                continue
            scored.add(r["version_id"])
            summary = result = None
            if r["output_json"]:
                summary = OutlookSummary.model_validate_json(r["output_json"])
                sections = load_sections(conn, r["version_id"])
                published = date.fromisoformat(r["published_on"]) if r["published_on"] else None
                ctx = VerificationContext(
                    published_on=published,
                    injection_ordinals=tuple(injection_findings(sections)),
                    institution=r["institution"],
                )
                result = verify(
                    summary, sections, ctx, version=resolve_verifier(r["verifier_version"])
                )
            report.models.append(score(str(r["id"]), str(r["version_id"]), summary, result,
                                       _gold(gold[r["version_id"]]), in_tok, out_tok, estimated, latency))  # fmt: skip
        aggregate(report, PRICE_POINTS)
        groups.append(
            ModelGroup(provider, model_name, prompt, len(report.models), errors, cost, report)
        )
    missing = tuple(sorted(v for v in gold if v not in summarised))
    return RealEvalReport(annotations.annotator, annotations.annotated_on, tuple(groups), missing)
