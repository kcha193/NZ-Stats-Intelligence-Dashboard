"""Offline evaluation of the summary pipeline against a synthetic, hand-annotated set.

Each case holds synthetic document versions, gold annotations (forecast claims, indicators, key
points) and candidate outputs: `model` candidates stand in for a model's answer (replayed through the
fake provider, or replaced by a live provider's answer with `run_eval(..., provider=...)`), and `probe`
candidates carry planted errors labelled with the verifier codes they must trigger.

Replay results measure the deterministic layers (parsing, verification, gating, metrics) on
simulated outputs. They are not a measurement of a real model; run a live provider for that.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from nzstats.research.contract import (
    ForecastClaim,
    ModelProvenance,
    OutlookSummary,
    Provider,
    SectionText,
    assemble,
    build_request,
    parse_draft,
)
from nzstats.research.prompt import PROMPT_VERSION, injection_findings
from nzstats.research.providers import FakeProvider, Pricing, estimate_tokens, request_chars
from nzstats.research.verify import VerificationContext, verify

REF_CODES = frozenset({"wrong_version", "unknown_section", "quote_not_found", "quote_truncated",
                       "page_outside_section", "page_without_pages", "instruction_like_evidence"})  # fmt: skip
# Prices per million tokens (input, output) from the Claude API model table, cached 2026-10-06. Estimates
# only: check current pricing before relying on them.
PRICE_POINTS = {
    "claude-opus-5-5": Pricing(4.0, 20.0),
    "claude-sonnet-5-5": Pricing(2.0, 10.0),
    "claude-haiku-5-5": Pricing(0.10, 0.50),
}
# The replay results recorded in docs/progress.md; the test fails if a change makes any of them worse.
RECORDED_BASELINE: dict[str, float] = {
    "raw_precision": 0.909, "raw_recall": 0.909, "accepted_precision": 0.941, "accepted_recall": 0.727,
    "numerical_fidelity": 0.950, "scenario_accuracy": 1.0, "indicator_f1": 0.941,
    "citation_correctness": 0.953, "completeness": 0.869, "verified_rate": 0.769,
    "probe_detection_rate": 1.0,
}  # fmt: skip

_MONTH = re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b")
_YEAR = re.compile(r"\b((?:19|20)\d{2})(?:\s*[/–-]\s*(\d{2}))?\b")
_YEAR_TO = re.compile(r"year\s+(?:to|ending|ended)|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(?:(?:19|20)\d{2}\s+)?year\b|fiscal")  # fmt: skip
_QUARTER = re.compile(r"\bquarter|\bq[1-4]\b")


@dataclass(frozen=True)
class GoldClaim:
    indicator: str
    horizon: str
    value: float | None
    unit: str | None
    scenario: str | None


@dataclass(frozen=True)
class GoldVersion:
    indicators: frozenset[str]
    forecasts: tuple[GoldClaim, ...]
    key_points: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class CandidateOutput:
    id: str
    version: str
    role: str  # "model" or "probe"
    output: dict[str, Any]
    expected_errors: frozenset[str] = frozenset()
    expected_warnings: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Case:
    id: str
    description: str
    published_on: str | None
    versions: dict[str, dict[int, SectionText]]
    version_ids: dict[str, int]
    gold: dict[str, GoldVersion]
    candidates: tuple[CandidateOutput, ...]


@dataclass
class ProbeResult:
    case: str
    candidate: str
    expected_errors: frozenset[str]
    expected_warnings: frozenset[str]
    errors: frozenset[str]
    warnings: frozenset[str]

    @property
    def as_expected(self) -> bool:
        if self.expected_warnings - self.warnings:
            return False
        if self.expected_errors:
            return self.expected_errors <= self.errors
        return not self.errors  # a probe with no expected error must pass verification


@dataclass
class ModelResult:
    case: str
    version: str
    verified: bool
    errors: frozenset[str]
    raw: dict[str, int]
    accepted: dict[str, int]
    indicators: tuple[int, int, int]
    refs: int
    bad_refs: int
    items: int
    unsupported_items: int
    key_points: tuple[int, int]
    input_tokens: int
    output_tokens: int
    usage_estimated: bool
    latency_ms: float


@dataclass
class EvalReport:
    mode: str
    models: list[ModelResult] = field(default_factory=list)
    probes: list[ProbeResult] = field(default_factory=list)
    metrics: dict[str, float | None] = field(default_factory=dict)
    costs: dict[str, float] = field(default_factory=dict)

    def to_markdown(self) -> str:
        lines = [
            f"Mode: {self.mode}. "
            + (
                "Replay of hand-written simulated outputs: this is not a measurement of a real model."
                if self.mode == "replay"
                else "Live provider outputs on the synthetic documents."
            ),  # fmt: skip
            "",
            "| metric | value |",
            "|---|---|",
        ]
        for name, label in _LABELS.items():
            value = self.metrics.get(name)
            lines.append(f"| {label} | {'n/a' if value is None else f'{value:.3f}'} |")
        lines += ["", "| price point | mean cost per document (USD) |", "|---|---|"]
        lines += [f"| {k} | {v:.4f} |" for k, v in self.costs.items()]
        missed = [p for p in self.probes if not p.as_expected]
        lines += [
            "",
            f"Probes behaving as labelled: {len(self.probes) - len(missed)} of {len(self.probes)}.",
        ]
        lines += [f"- missed: {p.case}/{p.candidate} expected {sorted(p.expected_errors)},"
                  f" got {sorted(p.errors)}" for p in missed]  # fmt: skip
        return "\n".join(lines) + "\n"


_LABELS = {
    "raw_precision": "forecast precision (raw model output)",
    "raw_recall": "forecast recall (raw model output)",
    "accepted_precision": "forecast precision (accepted)",
    "accepted_recall": "forecast recall (accepted)",
    "numerical_fidelity": "numerical fidelity (aligned raw claims)",
    "scenario_accuracy": "scenario versus baseline (aligned raw claims)",
    "indicator_precision": "indicator classification precision",
    "indicator_recall": "indicator classification recall",
    "indicator_f1": "indicator classification F1",
    "citation_correctness": "citation correctness (evidence refs)",
    "completeness": "summary completeness (key points)",
    "unsupported_item_rate": "items with a verifier error (raw)",
    "verified_rate": "model outputs passing verification",
    "probe_detection_rate": "planted errors detected",
    "probe_false_rejection_rate": "clean probes wrongly rejected",
    "mean_input_tokens": "mean input tokens per document",
    "mean_output_tokens": "mean output tokens per document",
    "mean_latency_ms": "mean provider latency (ms)",
}


def rate(numerator: float, denominator: float) -> float | None:
    return None if denominator == 0 else numerator / denominator


def horizon_key(text: str) -> frozenset[str]:
    """Period tokens of a horizon: years, months, fiscal pair, quarterly or year-to basis."""
    t = text.lower()
    tokens: set[str] = set()
    for m in _YEAR.finditer(t):
        tokens.add(m.group(1))
        if m.group(2):
            tokens |= {f"{int(m.group(1)) // 100 * 100 + int(m.group(2))}", "pair"}
    tokens |= {f"m:{m}" for m in _MONTH.findall(t)}
    if _QUARTER.search(t):
        tokens.add("quarter")
    elif _YEAR_TO.search(t):
        tokens.add("year_to")
    return frozenset(tokens)


def extraction_counts(
    predicted: Sequence[ForecastClaim], gold: Sequence[GoldClaim]
) -> dict[str, int]:
    """Align claims on (indicator, horizon key); prefer gold claims with the same value."""
    free = list(range(len(gold)))
    aligned = correct = scenario_ok = value_ok = 0
    for claim in predicted:
        options = [g for g in free if gold[g].indicator == claim.indicator.value
                   and horizon_key(gold[g].horizon) == horizon_key(claim.horizon)]  # fmt: skip
        if not options:
            continue
        same_value = [g for g in options if _same_value(gold[g].value, claim.value)]
        g = (same_value or options)[0]
        free.remove(g)
        aligned += 1
        scenario_match = (gold[g].scenario is None) == (claim.scenario is None)
        scenario_ok += scenario_match
        correct += scenario_match
        value_ok += _same_value(gold[g].value, claim.value) and gold[g].unit == claim.unit
    return {"predicted": len(predicted), "gold": len(gold), "aligned": aligned, "correct": correct,
            "scenario_correct": scenario_ok, "value_correct": value_ok}  # fmt: skip


def _same_value(a: float | None, b: float | None) -> bool:
    return (a is None and b is None) or (a is not None and b is not None and abs(a - b) < 1e-9)


def indicator_counts(predicted: set[str], gold: set[str]) -> tuple[int, int, int]:
    return len(predicted & gold), len(predicted), len(gold)


def completeness(text: str, key_points: Sequence[Sequence[str]]) -> tuple[int, int]:
    lowered = text.lower()
    covered = sum(all(w.lower() in lowered for w in point) for point in key_points)
    return covered, len(key_points)


# --- loading -----------------------------------------------------------------------------------
def load_eval_set(directory: Path) -> list[Case]:
    return [
        load_case(path, index) for index, path in enumerate(sorted(Path(directory).glob("*.json")))
    ]


def load_case(path: Path, index: int = 0) -> Case:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    versions = {
        key: {i: SectionText(s["text"], s.get("page"), s.get("page"), s.get("heading"))
              for i, s in enumerate(sections)}
        for key, sections in raw["versions"].items()
    }  # fmt: skip
    ids = {key: 1000 * (index + 1) + n + 1 for n, key in enumerate(sorted(versions))}
    gold = {
        key: GoldVersion(
            frozenset(g.get("indicators", ())),
            tuple(GoldClaim(f["indicator"], f["horizon"], f.get("value"), f.get("unit"), f.get("scenario"))
                  for f in g.get("forecasts", ())),
            tuple(tuple(p) for p in g.get("key_points", ())),
        )
        for key, g in raw["gold"].items()
    }  # fmt: skip
    models = {
        c["version"]: c["output"] for c in raw["candidates"] if c.get("role", "probe") == "model"
    }
    candidates = []
    for c in raw["candidates"]:
        output = dict(c["output"])
        base = models.get(c["version"], {})
        for name in ("outlook", "indicators"):
            if name not in output and name in base:
                output[name] = base[name]
        candidates.append(CandidateOutput(
            c["id"], c["version"], c.get("role", "probe"), output,
            frozenset(c.get("expected_errors", ())), frozenset(c.get("expected_warnings", ()))))  # fmt: skip
    return Case(raw["id"], raw.get("description", ""), raw.get("published_on"), versions, ids, gold,
                tuple(candidates))  # fmt: skip


def expand_output(output: Mapping[str, Any], version_ids: Mapping[str, int], version: str) -> str:
    """The shorthand candidate as the JSON text a model would return."""

    def refs(evidence: Sequence[Sequence[Any]]) -> list[dict[str, Any]]:
        out = []
        for e in evidence:
            cited = version_ids.get(e[3], 99_999) if len(e) > 3 else version_ids[version]
            out.append({"version_id": cited, "section_ordinal": e[0], "page": e[1], "quote": e[2]})
        return out

    def statement(s: Mapping[str, Any]) -> dict[str, Any]:
        return {"text": s["text"], "evidence": refs(s["evidence"])}

    data: dict[str, Any] = {"outlook": statement(output["outlook"])}
    for name in ("drivers", "risks"):
        if name in output:
            data[name] = [statement(s) for s in output[name]]
    if output.get("uncertainty"):
        data["uncertainty"] = statement(output["uncertainty"])
    data["indicators"] = list(output.get("indicators", ()))
    data["forecasts"] = [
        {"indicator": f["indicator"], "indicator_label": f.get("label", f["indicator"]),
         "horizon": f["horizon"], "value": f.get("value"), "unit": f.get("unit"),
         "direction": f.get("direction", "unclear"), "qualification": f.get("qualification"),
         "scenario": f.get("scenario"), "evidence": refs(f["evidence"])}
        for f in output.get("forecasts", ())
    ]  # fmt: skip
    return json.dumps(data)


# --- running -----------------------------------------------------------------------------------
def _summarise_one(
    case: Case, version: str, provider: Provider
) -> tuple[OutlookSummary | None, Any, float, int, int, bool]:
    sections = case.versions[version]
    request = build_request(case.version_ids[version], sections, prompt_version=PROMPT_VERSION,
                            published_on=case.published_on)  # fmt: skip
    started = time.perf_counter()
    response = provider.summarise(request)
    latency = (time.perf_counter() - started) * 1000
    estimated = response.input_tokens is None or response.output_tokens is None
    in_tok = (
        response.input_tokens
        if response.input_tokens is not None
        else estimate_tokens(request_chars(request))
    )
    out_tok = (
        response.output_tokens
        if response.output_tokens is not None
        else estimate_tokens(len(response.text))
    )
    try:
        draft = parse_draft(response.text)
    except ValueError:
        return None, None, latency, in_tok, out_tok, estimated
    provenance = ModelProvenance(
        provider=provider.name, model=response.model, prompt_version=PROMPT_VERSION,
        processing_version="eval", input_text_sha256="0" * 64, created_at=datetime.now(UTC),
    )  # fmt: skip
    summary = assemble(draft, version_id=case.version_ids[version], provenance=provenance)
    published = date.fromisoformat(case.published_on) if case.published_on else None
    report = verify(summary, sections, VerificationContext(
        published_on=published, injection_ordinals=tuple(injection_findings(sections))))  # fmt: skip
    return summary, report, latency, in_tok, out_tok, estimated


def _replay(case: Case, candidate: CandidateOutput) -> FakeProvider:
    return FakeProvider(
        expand_output(candidate.output, case.version_ids, candidate.version), usage=None
    )


def run_eval(
    cases: Sequence[Case],
    *,
    pricing: Mapping[str, Pricing] | None = None,
    provider: Provider | None = None,
) -> EvalReport:
    report = EvalReport("live" if provider is not None else "replay")
    for case in cases:
        for candidate in case.candidates:
            if candidate.role == "probe":
                _, result, *_ = _summarise_one(case, candidate.version, _replay(case, candidate))
                errors = (
                    frozenset(p.code for p in result.errors)
                    if result
                    else frozenset({"invalid_output"})
                )
                warnings = frozenset(p.code for p in result.warnings) if result else frozenset()
                report.probes.append(ProbeResult(case.id, candidate.id, candidate.expected_errors,
                                                 candidate.expected_warnings, errors, warnings))  # fmt: skip
                continue
            source = provider if provider is not None else _replay(case, candidate)
            report.models.append(_model_result(case, candidate.version, source))
    _aggregate(report, pricing or PRICE_POINTS)
    return report


def _model_result(case: Case, version: str, provider: Provider) -> ModelResult:
    summary, result, latency, in_tok, out_tok, estimated = _summarise_one(case, version, provider)
    gold = case.gold[version]
    if summary is None or result is None:
        empty = extraction_counts([], gold.forecasts)
        return ModelResult(case.id, version, False, frozenset({"invalid_output"}), empty, empty,
                           (0, 0, len(gold.indicators)), 0, 0, 0, 0, (0, len(gold.key_points)),
                           in_tok, out_tok, estimated, latency)  # fmt: skip
    errors = result.errors
    raw = extraction_counts(summary.forecasts, gold.forecasts)
    accepted = raw if result.passed else extraction_counts([], gold.forecasts)
    statements = [("outlook", summary.outlook)]
    statements += [(f"drivers[{i}]", s) for i, s in enumerate(summary.drivers)]
    statements += [(f"risks[{i}]", s) for i, s in enumerate(summary.risks)]
    if summary.uncertainty is not None:
        statements.append(("uncertainty", summary.uncertainty))
    items = [p for p, _ in statements] + [f"forecasts[{i}]" for i in range(len(summary.forecasts))]
    unsupported = sum(
        any(e.path == item or e.path.startswith(f"{item}.") for e in errors) for item in items
    )
    refs = sum(len(s.evidence) for _, s in statements) + sum(
        len(c.evidence) for c in summary.forecasts
    )
    bad_refs = len({e.path for e in errors if e.code in REF_CODES})
    text = " ".join(s.text for _, s in statements)
    return ModelResult(
        case.id, version, result.passed, frozenset(e.code for e in errors), raw, accepted,
        indicator_counts({i.value for i in summary.indicators}, set(gold.indicators)), refs, bad_refs,
        len(items), unsupported, completeness(text, gold.key_points), in_tok, out_tok, estimated, latency,
    )  # fmt: skip


def _aggregate(report: EvalReport, pricing: Mapping[str, Pricing]) -> None:
    models = report.models

    def total(name: str, key: str) -> int:
        return sum(getattr(m, name)[key] for m in models)

    m: dict[str, float | None] = {
        "raw_precision": rate(total("raw", "correct"), total("raw", "predicted")),
        "raw_recall": rate(total("raw", "correct"), total("raw", "gold")),
        "accepted_precision": rate(total("accepted", "correct"), total("accepted", "predicted")),
        "accepted_recall": rate(total("accepted", "correct"), total("accepted", "gold")),
        "numerical_fidelity": rate(total("raw", "value_correct"), total("raw", "aligned")),
        "scenario_accuracy": rate(total("raw", "scenario_correct"), total("raw", "aligned")),
    }
    tp, n_pred, n_gold = (sum(mr.indicators[i] for mr in models) for i in range(3))
    precision, recall = rate(tp, n_pred), rate(tp, n_gold)
    m["indicator_precision"], m["indicator_recall"] = precision, recall
    m["indicator_f1"] = (None if not precision or not recall
                         else 2 * precision * recall / (precision + recall))  # fmt: skip
    m["citation_correctness"] = rate(
        sum(x.refs - x.bad_refs for x in models), sum(x.refs for x in models)
    )
    m["completeness"] = rate(
        sum(x.key_points[0] for x in models), sum(x.key_points[1] for x in models)
    )
    m["unsupported_item_rate"] = rate(
        sum(x.unsupported_items for x in models), sum(x.items for x in models)
    )
    m["verified_rate"] = rate(sum(x.verified for x in models), len(models))
    planted = [p for p in report.probes if p.expected_errors]
    clean = [p for p in report.probes if not p.expected_errors]
    m["probe_detection_rate"] = rate(sum(p.as_expected for p in planted), len(planted))
    m["probe_false_rejection_rate"] = rate(sum(not p.as_expected for p in clean), len(clean))
    m["mean_input_tokens"] = rate(sum(x.input_tokens for x in models), len(models))
    m["mean_output_tokens"] = rate(sum(x.output_tokens for x in models), len(models))
    m["mean_latency_ms"] = (
        rate(sum(x.latency_ms for x in models), len(models)) if report.mode == "live" else None
    )
    report.metrics = m
    if models:
        for name, price in pricing.items():
            report.costs[name] = sum(
                price.cost(x.input_tokens, x.output_tokens) for x in models
            ) / len(models)
