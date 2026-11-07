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
from nzstats.research.hosted import HostedConsent, approved_sections, consent_refusal
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
STALE_MARGIN_SECONDS = 60.0


def stale_after(limits: LlmLimits) -> timedelta:
    """How long a call can legitimately be in flight: every attempt at its timeout, every back-off, and a margin."""
    attempts = limits.max_retries + 1
    return timedelta(
        seconds=limits.timeout_seconds * attempts
        + MAX_BACKOFF_SECONDS * limits.max_retries
        + STALE_MARGIN_SECONDS
    )


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
    version_scoped_hosted: bool = False,
) -> tuple[list[Candidate], list[tuple[str, str]]]:
    """Versions this provider may process, and (institution, reason) for every refusal."""
    sql = (
        "SELECT v.id, v.title, v.licence_snapshot, v.acquisition, v.purged_at, p.published_on, i.key"
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
            "its text was purged"
            if row["purged_at"]
            else "not in the research registry"
            if inst is None
            else (
                None
                if inst.holds(row["acquisition"]) and inst.content_policy == ContentPolicy.FULL_TEXT
                else "source acquisition or full-text storage permission refused"
            )
            if version_scoped_hosted
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
    hosted_consents: Sequence[HostedConsent] = (),
    verifier: str = VERIFIER_VERSION,
    run_started: Callable[[int], None] | None = None,
) -> SummariseResult:
    if isinstance(provider, DisabledProvider) or provider.name == "disabled":
        raise ProviderDisabled("no LLM provider is configured")
    if provider.name == "openrouter":
        from nzstats.research.openrouter import OpenRouterProvider

        if not isinstance(provider, OpenRouterProvider):
            raise ValueError("OpenRouter requires the privacy-enforcing adapter")
        provider.validate_run(pricing, limits)
    candidates, refusals = eligible_versions(
        conn,
        registry,
        hosted=provider.hosted,
        institution=institution,
        version_ids=version_ids,
        version_scoped_hosted=provider.name == "openrouter",
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
    scope = provider.pilot_scope if provider.name == "openrouter" else None
    prompt_version = provider.prompt_version if provider.name == "openrouter" else PROMPT_VERSION
    if not dry_run:
        result.run_id = ss.start_run(
            conn, provider=provider.name, model=provider.model, hosted=provider.hosted,
            prompt_version=prompt_version, processing_version=PROCESSING_VERSION,
            limits={"max_input_chars": limits.max_input_chars, "max_output_tokens": limits.max_output_tokens,
                    "max_retries": limits.max_retries, "max_run_usd": run_limits.max_run_usd,
                    "max_period_usd": limits.max_period_usd, "period_days": PERIOD_DAYS,
                    "period_remaining_usd": round(remaining, 6), "timeout_seconds": limits.timeout_seconds,
                    **({"experiment": scope.experiment} if scope else {})},
            dry_run=False, now=started,
        )  # fmt: skip
        if run_started is not None:
            run_started(result.run_id)
        # A reservation held past its own deadline belongs to a process that is gone.
        ss.abandon_stale(conn, now=started)
    stopped = False
    dry_spent, dry_attempts = 0.0, 0
    slots = 0  # the cap bounds work still to do; finished and oversize versions never use a slot
    try:
        for candidate in candidates:
            sections = load_sections(conn, candidate.version_id)
            if provider.name == "openrouter":
                grant = next(
                    (
                        g
                        for g in hosted_consents
                        if isinstance(g, HostedConsent) and g.version_id == candidate.version_id
                    ),
                    None,
                )
                try:
                    if grant is None:
                        raise ValueError("missing consent")
                    sections = approved_sections(sections, grant)
                except ValueError:
                    result.refusals.append(
                        (
                            candidate.institution,
                            f"version {candidate.version_id}: independent hosted consent missing or mismatched",
                        )
                    )
                    continue
            inst = registry.get(candidate.institution)
            request = build_request(candidate.version_id, sections, prompt_version=prompt_version,
                                    limits=limits, published_on=candidate.published_on,
                                    institution=candidate.institution,
                                    author=inst.name if inst else None)  # fmt: skip
            if provider.name == "openrouter":
                reason = consent_refusal(conn, request, provider, hosted_consents, now_fn())
                if reason:
                    result.refusals.append((candidate.institution, reason))
                    continue
            item = ItemResult(candidate.version_id, candidate.institution, "pending")
            if request.truncated or (
                provider.name == "openrouter" and not provider.input_fits(request)
            ):
                item.outcome = "input_too_long"
                result.items.append(item)
                continue
            key = ss.SummaryKey(
                candidate.version_id, provider.name, provider.model, prompt_version, PROCESSING_VERSION,
                input_sha256(request, provider=provider.name, model=provider.model, parameters=parameters),
            )  # fmt: skip
            if provider.name == "openrouter":
                from nzstats.research.openrouter import input_token_bound

                worst = pricing.cost(input_token_bound(request), limits.max_output_tokens)
            else:
                worst = pricing.cost(
                    estimate_tokens(request_chars(request)), limits.max_output_tokens
                )
            item.estimated_usd = worst
            existing = ss.completed_summary(conn, key)
            if existing is not None:
                item.outcome, item.summary_id = "exists", int(existing["id"])
                result.items.append(item)
                continue
            pilot_refusal = (
                ss.openrouter_refusal(
                    conn, candidate.version_id, worst, scope=scope,
                    pending_usd=dry_spent, pending_attempts=dry_attempts,
                )
                if provider.name == "openrouter" else None
            )  # fmt: skip
            if pilot_refusal == "attempt_consumed":
                item.outcome = "attempt_consumed"
                result.items.append(item)
                continue
            if slots >= cap:
                break
            slots += 1
            result.items.append(item)
            if stopped:
                item.outcome = "budget_exhausted"
            elif (
                dry_run
                and provider.name == "openrouter"
                and (dry_spent + worst > limits.max_run_usd or pilot_refusal is not None)
            ):
                item.outcome = "budget_exhausted"
                stopped = True
            elif dry_run:
                item.outcome = "would_summarise"
                dry_spent += worst
                dry_attempts += 1
            else:
                stopped = _process(conn, provider, request, sections, key, parameters, item, result,
                                   pricing=pricing, limits=limits, worst=worst, now_fn=now_fn,
                                   sleep=sleep, clock=clock, scope=scope, verifier=verifier,
                                   consent_check=(lambda req=request: consent_refusal(
                                       conn, req, provider, hosted_consents, now_fn()))
                                   if provider.name == "openrouter" else None)  # fmt: skip
                if item.outcome == "attempt_consumed":
                    slots -= 1  # another process consumed this version after the read-only check
    except BaseException:
        if result.run_id is not None:
            _record_abort(conn, result, now_fn())
        raise
    if stopped:
        result.outcome = "budget_exhausted"
    elif any(i.outcome == "provider_error" for i in result.items):
        result.outcome = "partial"
    if result.run_id is not None:
        ss.finish_run(conn, result.run_id, outcome=result.outcome, counts=result.counts,
                      spent_usd=result.spent_usd, now=now_fn())  # fmt: skip
    return result


def _record_abort(conn: sqlite3.Connection, result: SummariseResult, now: datetime) -> None:
    """Close an interrupted run. A call that never returned may have been billed, so its reservation stays at the
    worst case and the run records it as spent. Recording must not hide the error that interrupted the run."""
    try:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        interrupted = ss.abandon_run(conn, result.run_id or 0, now=now)
        result.spent_usd += interrupted
        ss.finish_run(conn, result.run_id or 0, outcome="aborted", counts=result.counts,
                      spent_usd=result.spent_usd, now=now)  # fmt: skip
    except Exception:
        log.exception(
            "could not record the aborted run %s; its reservations stay held", result.run_id
        )


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
    scope: ss.PilotScope | None = None,
    consent_check: Callable[[], str | None] | None = None,
    verifier: str = VERIFIER_VERSION,
) -> bool:
    """Call, parse, verify and store one document. True when the run budget stops the run."""
    calls: list[_Call] = []
    response, error, budget_stop = None, None, False
    estimated_in = estimate_tokens(request_chars(request))
    for call_no in range(1, limits.max_retries + 2):
        if result.spent_usd + worst > limits.max_run_usd:
            budget_stop = True
            break
        # Reserve before contacting the provider: under the database write lock, so another process sees it.
        try:
            held = ss.reserve(
                conn, run_id=result.run_id or 0, version_id=key.version_id, call_no=call_no,
                provider=provider.name, model=provider.model, amount_usd=worst,
                period_cap_usd=limits.max_period_usd,
                since=now_fn() - timedelta(days=PERIOD_DAYS), now=now_fn(),
                expires_at=now_fn() + stale_after(limits), scope=scope,
                consent_check=consent_check,
            )  # fmt: skip
        except ss.AttemptConsumed:
            item.outcome = "attempt_consumed"
            return False
        except ss.ConsentRefused:
            item.outcome = "consent_refused"
            return False
        if held is None:
            budget_stop = True
            break
        started = clock()
        try:
            if consent_check is not None and consent_check() is not None:
                raise ProviderError(
                    "hosted_consent_refused",
                    retryable=False,
                    input_tokens=0,
                    output_tokens=0,
                    cost_usd=0,
                )
            response = provider.summarise(request)
            error = None
        except ProviderDisabled:
            ss.settle(conn, held, actual_usd=0.0, basis="not_billed", now=now_fn())
            raise
        except ProviderError as exc:
            error = exc
        except Exception:  # never log arbitrary exception text from an adapter
            log.error("provider %s raised unexpectedly", provider.name)
            error = ProviderError("provider_exception", retryable=False)
        latency = int((clock() - started) * 1000)
        if error is None and response is not None:
            in_tok, out_tok = response.input_tokens, response.output_tokens
            estimated = in_tok is None or out_tok is None
            in_tok = in_tok if in_tok is not None else estimated_in
            out_tok = out_tok if out_tok is not None else estimate_tokens(len(response.text))
            cost = (
                response.cost_usd
                if response.cost_usd is not None
                else pricing.cost(in_tok, out_tok)
            )
            calls.append(_Call(call_no, in_tok, out_tok, estimated, latency, cost, "ok", None))
            result.spent_usd += cost
            # Settled at once, in its own transaction: the cost is durable even if storing the result fails.
            ss.settle(conn, held, actual_usd=cost, basis="estimated" if estimated else "reported",
                      now=now_fn())  # fmt: skip
            break
        assert error is not None
        reported = error.input_tokens is not None and error.output_tokens is not None
        if error.cost_usd is not None:
            cost, basis = error.cost_usd, "reported"
        elif reported:
            cost, basis = (
                pricing.cost(error.input_tokens or 0, error.output_tokens or 0),
                "reported",
            )
        elif error.error_class in NOT_BILLED and provider.name != "openrouter":
            cost, basis = 0.0, "not_billed"
        else:
            cost, basis = worst, "worst_case"
        calls.append(_Call(call_no, error.input_tokens, error.output_tokens, not reported, latency,
                           cost, "provider_error", error.error_class))  # fmt: skip
        result.spent_usd += cost
        ss.settle(conn, held, actual_usd=cost, basis=basis, now=now_fn())
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
        if error is not None:
            parameters = dict(parameters)
            for name in (
                "serving_provider",
                "response_model",
                "response_id",
                "reasoning_tokens",
                "finish_reason",
                "native_finish_reason",
            ):
                value = getattr(error, name)
                if value is not None:
                    parameters[name] = value
    else:
        raw = response.text
        parameters = dict(parameters)
        if response.serving_provider is not None:
            parameters["serving_provider"] = response.serving_provider
        if response.response_id is not None:
            parameters["response_id"] = response.response_id
        if response.reasoning_tokens is not None:
            parameters["reasoning_tokens"] = response.reasoning_tokens
        if response.stop_reason is not None:
            parameters["finish_reason"] = response.stop_reason
        status, error_class, output_json, verification, claims = _interpret(
            response.text, response.model, request, sections, key, parameters, now_fn(), verifier
        )
    try:
        with transaction(conn):
            summary_id = ss.insert_summary(
                conn, key, run_id=result.run_id or 0, attempt=attempt, hosted=provider.hosted,
                verifier_version=verifier, parameters=parameters, raw_output=raw,
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
    except sqlite3.IntegrityError:
        purged = conn.execute("SELECT purged_at FROM research_document_version WHERE id=?",
                              (key.version_id,)).fetchone()[0]  # fmt: skip
        if purged is None:
            raise
        item.outcome = "purged"  # purged while the call ran: the call was billed and settled; its output is refused
        return budget_stop
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
    verifier: str = VERIFIER_VERSION,
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
        published_on=published, injection_ordinals=tuple(injection_findings(sections)),
        institution=request.institution), version=verifier)  # fmt: skip
    status = "verified" if report.passed else "failed_verification"
    return status, None, summary.model_dump_json(), report.to_json(), summary.forecasts
