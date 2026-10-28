"""Summarise stored research document versions with a configured provider. Never scheduled.

For each eligible version: build the framed request, refuse documents over the input cap (never
truncate), skip work already done for the same key, check the run budget against the worst-case
cost of the next call, call the provider with bounded retries, parse strictly, verify every claim
deterministically, and store the result, its usage and its claims in one transaction. Provider and
parsing failures are stored statuses, never exceptions that end the run. Each run is audited in
`research_llm_run`.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta

from pydantic import ValidationError

from nzstats.clock import utc_now
from nzstats.research import summary_store as ss
from nzstats.research.contract import (
    PERIOD_DAYS,
    DisabledProvider,
    LlmLimits,
    ModelProvenance,
    Provider,
    ProviderDisabled,
    ProviderError,
    SectionText,
    SummaryRequest,
    assemble,
    build_request,
    parse_draft,
)
from nzstats.research.prompt import PROMPT_VERSION, injection_findings, input_sha256
from nzstats.research.providers import Pricing, estimate_tokens, request_chars
from nzstats.research.registry import ContentPolicy, Institution
from nzstats.research.verify import VERIFIER_VERSION, VerificationContext, verify
from nzstats.store.db import transaction

log = logging.getLogger(__name__)

PROCESSING_VERSION = "3b-1"
BACKOFF_SECONDS = 2.0
# Failures the provider reports before generating anything, so nothing is billed. Every other failure
# is charged with the usage the provider reported, or at the worst case when it reported none.
NOT_BILLED = frozenset(
    {"auth_error", "bad_request", "rate_limited", "overloaded", "conflict", "http_error"}
)
MAX_BACKOFF_SECONDS = 30.0


@dataclass(frozen=True)
class Candidate:
    version_id: int
    institution: str
    title: str
    published_on: str | None


@dataclass
class ItemResult:
    version_id: int
    institution: str
    outcome: str
    summary_id: int | None = None
    error_class: str | None = None
    cost_usd: float = 0.0
    estimated_usd: float = 0.0
    errors: int = 0
    warnings: int = 0


@dataclass
class SummariseResult:
    run_id: int | None = None
    outcome: str = "ok"
    items: list[ItemResult] = field(default_factory=list)
    refusals: list[tuple[str, str]] = field(default_factory=list)
    spent_usd: float = 0.0
    period_remaining_usd: float = 0.0  # what the rolling cap allowed when the run started

    @property
    def counts(self) -> dict[str, int]:
        return dict(Counter(i.outcome for i in self.items))


@dataclass
class _Call:
    call_no: int
    input_tokens: int | None
    output_tokens: int | None
    estimated: bool
    latency_ms: int
    cost_usd: float
    outcome: str
    error_class: str | None


def eligible_versions(
    conn: sqlite3.Connection,
    registry: Mapping[str, Institution],
    *,
    hosted: bool,
    institution: str | None = None,
    version_ids: Sequence[int] = (),
) -> tuple[list[Candidate], list[tuple[str, str]]]:
    """Versions this provider may process, and (institution, reason) for every refusal."""
    sql = (
        "SELECT v.id, v.title, v.licence_snapshot, v.acquisition, p.published_on, i.key"
        " FROM research_document_version v"
        " JOIN research_publication p ON p.id = v.publication_id"
        " JOIN research_institution i ON i.id = p.institution_id"
    )
    params: list[object] = []
    if version_ids:
        sql += f" WHERE v.id IN ({','.join('?' * len(version_ids))})"
        params += list(version_ids)
    else:
        sql += " WHERE p.current_version_id = v.id"
    if institution:
        sql += " AND i.key = ?"
        params.append(institution)
    sql += " ORDER BY p.published_on DESC, v.id"
    candidates, refusals = [], {}
    for row in conn.execute(sql, params):
        key = row["key"]
        inst = registry.get(key)
        reason = (
            "not in the research registry"
            if inst is None
            else inst.llm_refusal(hosted=hosted, acquisition=row["acquisition"])
        )
        if reason is None and _stored_policy(row["licence_snapshot"]) not in (
            None,
            ContentPolicy.FULL_TEXT,
        ):
            reason = "stored under a policy other than full_text"
        if reason is not None:
            refusals.setdefault(key, reason)
            continue
        candidates.append(Candidate(int(row["id"]), key, row["title"], row["published_on"]))
    return candidates, sorted(refusals.items())


def _stored_policy(snapshot: str) -> str | None:
    try:
        value = json.loads(snapshot or "{}")
    except ValueError:
        return "unreadable"
    return value.get("content_policy") if isinstance(value, dict) else "unreadable"


def load_sections(conn: sqlite3.Connection, version_id: int) -> dict[int, SectionText]:
    return {
        int(r["ordinal"]): SectionText(r["text"], r["page_start"], r["page_end"], r["heading"])
        for r in conn.execute(
            "SELECT ordinal, heading, text, page_start, page_end FROM research_section"
            " WHERE version_id=? ORDER BY ordinal",
            (version_id,),
        )
    }


def summarise_versions(
    conn: sqlite3.Connection,
    registry: Mapping[str, Institution],
    provider: Provider,
    *,
    pricing: Pricing,
    limits: LlmLimits,
    institution: str | None = None,
    version_ids: Sequence[int] = (),
    limit: int | None = None,
    dry_run: bool = False,
    now_fn: Callable[[], datetime] = utc_now,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> SummariseResult:
    if isinstance(provider, DisabledProvider) or provider.name == "disabled":
        raise ProviderDisabled("no LLM provider is configured")
    candidates, refusals = eligible_versions(
        conn, registry, hosted=provider.hosted, institution=institution, version_ids=version_ids
    )
    cap = min(limit or limits.max_documents_per_run, limits.max_documents_per_run)
    result = SummariseResult(refusals=refusals)
    # The rolling cap: this run may spend no more than the period has left, so repeated runs stay bounded.
    started = now_fn()
    remaining = max(
        0.0, limits.max_period_usd - ss.spent_since(conn, started - timedelta(days=PERIOD_DAYS))
    )
    result.period_remaining_usd = remaining
    run_limits = limits
    limits = replace(limits, max_run_usd=min(limits.max_run_usd, remaining))
    parameters = dict(provider.parameters())
    if not dry_run:
        result.run_id = ss.start_run(
            conn, provider=provider.name, model=provider.model, hosted=provider.hosted,
            prompt_version=PROMPT_VERSION, processing_version=PROCESSING_VERSION,
            limits={"max_input_chars": limits.max_input_chars, "max_output_tokens": limits.max_output_tokens,
                    "max_retries": limits.max_retries, "max_run_usd": run_limits.max_run_usd,
                    "max_period_usd": limits.max_period_usd, "period_days": PERIOD_DAYS,
                    "period_remaining_usd": round(remaining, 6), "timeout_seconds": limits.timeout_seconds},
            dry_run=False, now=started,
        )  # fmt: skip
    stopped = False
    slots = 0  # the cap bounds work still to do; finished and oversize versions never use a slot
    try:
        for candidate in candidates:
            sections = load_sections(conn, candidate.version_id)
            request = build_request(candidate.version_id, sections, prompt_version=PROMPT_VERSION,
                                    limits=limits, published_on=candidate.published_on)  # fmt: skip
            item = ItemResult(candidate.version_id, candidate.institution, "pending")
            if request.truncated:
                item.outcome = "input_too_long"
                result.items.append(item)
                continue
            key = ss.SummaryKey(
                candidate.version_id, provider.name, provider.model, PROMPT_VERSION, PROCESSING_VERSION,
                input_sha256(request, provider=provider.name, model=provider.model, parameters=parameters),
            )  # fmt: skip
            worst = pricing.cost(estimate_tokens(request_chars(request)), limits.max_output_tokens)
            item.estimated_usd = worst
            existing = ss.completed_summary(conn, key)
            if existing is not None:
                item.outcome, item.summary_id = "exists", int(existing["id"])
                result.items.append(item)
                continue
            if slots >= cap:
                break
            slots += 1
            result.items.append(item)
            if stopped:
                item.outcome = "budget_exhausted"
            elif dry_run:
                item.outcome = "would_summarise"
            else:
                stopped = _process(conn, provider, request, sections, key, parameters, item, result,
                                   pricing=pricing, limits=limits, worst=worst, now_fn=now_fn,
                                   sleep=sleep, clock=clock)  # fmt: skip
    except BaseException:
        if result.run_id is not None:
            ss.finish_run(conn, result.run_id, outcome="aborted", counts=result.counts,
                          spent_usd=result.spent_usd, now=now_fn())  # fmt: skip
        raise
    if stopped:
        result.outcome = "budget_exhausted"
    elif any(i.outcome == "provider_error" for i in result.items):
        result.outcome = "partial"
    if result.run_id is not None:
        ss.finish_run(conn, result.run_id, outcome=result.outcome, counts=result.counts,
                      spent_usd=result.spent_usd, now=now_fn())  # fmt: skip
    return result


def _process(
    conn: sqlite3.Connection,
    provider: Provider,
    request: SummaryRequest,
    sections: Mapping[int, SectionText],
    key: ss.SummaryKey,
    parameters: Mapping[str, str | int | float | bool],
    item: ItemResult,
    result: SummariseResult,
    *,
    pricing: Pricing,
    limits: LlmLimits,
    worst: float,
    now_fn: Callable[[], datetime],
    sleep: Callable[[float], None],
    clock: Callable[[], float],
) -> bool:
    """Call, parse, verify and store one document. True when the run budget stops the run."""
    calls: list[_Call] = []
    response, error, budget_stop = None, None, False
    estimated_in = estimate_tokens(request_chars(request))
    for call_no in range(1, limits.max_retries + 2):
        if result.spent_usd + worst > limits.max_run_usd:
            budget_stop = True
            break
        started = clock()
        try:
            response = provider.summarise(request)
            error = None
        except ProviderDisabled:
            raise
        except ProviderError as exc:
            error = exc
        except Exception:  # an adapter bug must not end the run; the message is logged, not stored
            log.exception("provider %s raised unexpectedly", provider.name)
            error = ProviderError("provider_exception", retryable=False)
        latency = int((clock() - started) * 1000)
        if error is None and response is not None:
            in_tok, out_tok = response.input_tokens, response.output_tokens
            estimated = in_tok is None or out_tok is None
            in_tok = in_tok if in_tok is not None else estimated_in
            out_tok = out_tok if out_tok is not None else estimate_tokens(len(response.text))
            cost = pricing.cost(in_tok, out_tok)
            calls.append(_Call(call_no, in_tok, out_tok, estimated, latency, cost, "ok", None))
            result.spent_usd += cost
            break
        assert error is not None
        reported = error.input_tokens is not None and error.output_tokens is not None
        if reported:
            cost = pricing.cost(error.input_tokens or 0, error.output_tokens or 0)
        else:
            cost = 0.0 if error.error_class in NOT_BILLED else worst
        calls.append(_Call(call_no, error.input_tokens, error.output_tokens, not reported, latency,
                           cost, "provider_error", error.error_class))  # fmt: skip
        result.spent_usd += cost
        if not error.retryable or call_no > limits.max_retries:
            break
        sleep(min(BACKOFF_SECONDS * 2 ** (call_no - 1), MAX_BACKOFF_SECONDS))
    item.cost_usd = sum(c.cost_usd for c in calls)
    if not calls:  # the budget refused the first call: nothing happened, nothing to store
        item.outcome = "budget_exhausted"
        return True
    attempt = ss.next_attempt(conn, key)
    raw, output_json, verification, claims = None, None, None, ()
    if response is None or error is not None:
        status, error_class = "provider_error", error.error_class if error else "budget_exhausted"
    else:
        raw = response.text
        status, error_class, output_json, verification, claims = _interpret(
            response.text, response.model, request, sections, key, parameters, now_fn()
        )
    with transaction(conn):
        summary_id = ss.insert_summary(
            conn, key, run_id=result.run_id or 0, attempt=attempt, hosted=provider.hosted,
            verifier_version=VERIFIER_VERSION, parameters=parameters, raw_output=raw,
            output_json=output_json, status=status, error_class=error_class,
            verification=verification, now=now_fn(),
        )  # fmt: skip
        for c in calls:
            ss.record_usage(
                conn, run_id=result.run_id or 0, version_id=key.version_id, summary_id=summary_id,
                call_no=c.call_no, provider=provider.name, model=provider.model,
                input_tokens=c.input_tokens, output_tokens=c.output_tokens, usage_estimated=c.estimated,
                latency_ms=c.latency_ms, cost_usd=c.cost_usd, outcome=c.outcome,
                error_class=c.error_class, now=now_fn(),
            )  # fmt: skip
        if status == "verified":
            ss.insert_claims(conn, summary_id, claims)
    item.outcome, item.summary_id, item.error_class = status, summary_id, error_class
    if verification is not None:
        item.errors, item.warnings = len(verification["errors"]), len(verification["warnings"])
    return budget_stop


def _interpret(
    text: str,
    model: str,
    request: SummaryRequest,
    sections: Mapping[int, SectionText],
    key: ss.SummaryKey,
    parameters: Mapping[str, str | int | float | bool],
    now: datetime,
) -> tuple[str, str | None, str | None, dict | None, tuple]:
    """(status, error_class, output_json, verification, claims) for one model output."""
    try:
        draft = parse_draft(text)
    except ValidationError:
        return "invalid_output", "schema_mismatch", None, None, ()
    except ValueError:
        return "invalid_output", "invalid_json", None, None, ()
    provenance = ModelProvenance(
        provider=key.provider, model=model, prompt_version=key.prompt_version,
        processing_version=key.processing_version, parameters=dict(parameters),
        input_text_sha256=key.input_sha256, created_at=now,
    )  # fmt: skip
    try:
        summary = assemble(draft, version_id=key.version_id, provenance=provenance)
    except ValidationError:
        return "invalid_output", "schema_mismatch", None, None, ()
    published = date.fromisoformat(request.published_on) if request.published_on else None
    report = verify(summary, sections, VerificationContext(
        published_on=published, injection_ordinals=tuple(injection_findings(sections))))  # fmt: skip
    status = "verified" if report.passed else "failed_verification"
    return status, None, summary.model_dump_json(), report.to_json(), summary.forecasts
