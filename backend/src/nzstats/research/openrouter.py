"""Bounded OpenRouter pilot: explicit routes, no privacy relaxation, retries or fallback.

Public catalogue and ZDR endpoint evidence checked 2026-11-01 and 2026-11-02. These are candidate
routes, not source-processing approvals. The pipeline separately refuses missing version consent.

`max_tokens` is a hard limit on reasoning plus final text. Claude Opus 5.5 cannot switch reasoning
off or take a separate reasoning budget, so `reasoning.effort` is its only control and is not a
ceiling: Phase 4M spent all 6,000 tokens on reasoning at `high`. Failure classes name a specific
cause only when the response metadata supports it.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from nzstats.research.contract import LlmLimits, ProviderError, ProviderResponse, SummaryRequest
from nzstats.research.prompt import PROMPT_VERSION, render
from nzstats.research.providers import (
    OPENROUTER_URL,
    LlmConfigError,
    LlmSettings,
    OpenAICompatibleProvider,
    Pricing,
    _count,
    _status_error,
)
from nzstats.research.summary_store import PilotScope

log = logging.getLogger(__name__)

MAX_OUTPUT_TOKENS = 12_000
# A timeout must not cost a billed attempt. Phase 4M observed 107 and 136 output tokens/s.
MIN_OUTPUT_TOKENS_PER_SECOND = 60
_FINISH_REASONS = frozenset({"stop", "length", "content_filter", "tool_calls", "error"})
_NATIVE_FINISH_REASONS = frozenset(
    {"end_turn", "max_tokens", "stop_sequence", "tool_use", "refusal"}
)


@dataclass(frozen=True)
class Route:
    model: str
    provider_id: str
    response_provider: str
    context_tokens: int
    reasoning_efforts: tuple[str, ...] = ("low", "medium")  # high exhausted the Phase 4M budget


ROUTES = (
    Route("anthropic/claude-opus-5.5", "google-vertex/europe", "Google", 1_000_000),
    Route("openai/gpt-5.6-sol", "azure/eu", "Azure", 1_050_000),
)


@dataclass(frozen=True)
class Experiment:
    """A reviewed, separately consented request configuration and its own ledger scope."""

    scope: PilotScope
    prompt_version: str
    reasoning_effort: str
    max_output_tokens: int
    timeout_seconds: float


SECOND_PILOT = Experiment(
    PilotScope("phase-4n-second-pilot", max_attempts=2, max_usd=1.0),
    "outlook-v4",
    "low",
    MAX_OUTPUT_TOKENS,
    300.0,
)
EXPERIMENTS = {SECOND_PILOT.scope.experiment: SECOND_PILOT}


def validate_settings(settings: LlmSettings) -> Route:
    route = next(
        (
            r
            for r in ROUTES
            if (r.model, r.provider_id) == (settings.model, settings.openrouter_provider)
        ),
        None,
    )
    limits = settings.limits
    if route is None:
        raise LlmConfigError(
            "OpenRouter model/provider pair is not an eligible reviewed pilot route"
        )
    if not settings.api_key or not settings.api_key.strip():
        raise LlmConfigError("NZSTATS_LLM_API_KEY is required for OpenRouter")
    if settings.base_url != OPENROUTER_URL:
        raise LlmConfigError("OpenRouter requires its fixed HTTPS endpoint")
    if (settings.pricing.input_usd_per_mtok, settings.pricing.output_usd_per_mtok) != (4.4, 22.0):
        raise LlmConfigError(
            "OpenRouter prices must match the reviewed route (4.4 input, 22 output)"
        )
    if not (
        limits.max_retries == 0
        and 1 <= limits.max_documents_per_run <= 2
        and 0 < limits.max_run_usd <= 5
        and 0 < limits.max_period_usd <= 5
        and 0 < limits.max_input_chars <= 45_000
        and 0 < limits.max_output_tokens <= MAX_OUTPUT_TOKENS
        and limits.timeout_seconds * MIN_OUTPUT_TOKENS_PER_SECOND >= limits.max_output_tokens
    ):
        raise LlmConfigError(
            "OpenRouter pilot requires zero retries, two documents and US$5 maximum,"
            " with at most 12,000 output tokens and a timeout long enough to receive them"
        )
    if settings.openrouter_reasoning_effort not in route.reasoning_efforts:
        raise LlmConfigError(
            "NZSTATS_OPENROUTER_REASONING_EFFORT must be an explicit reviewed effort (low or medium)"
        )
    if settings.openrouter_experiment is not None:
        experiment = EXPERIMENTS.get(settings.openrouter_experiment)
        if (
            experiment is None
            or (
                experiment.prompt_version,
                experiment.reasoning_effort,
                experiment.max_output_tokens,
                experiment.timeout_seconds,
            )
            != (
                PROMPT_VERSION,
                settings.openrouter_reasoning_effort,
                limits.max_output_tokens,
                limits.timeout_seconds,
            )
            or limits.max_run_usd > experiment.scope.max_usd
        ):
            raise LlmConfigError("OpenRouter settings do not match the authorised experiment")
    return route


def input_token_bound(request: SummaryRequest) -> int:
    """UTF-8 byte ceiling, including framing/schema, rather than a chars/3 heuristic.

    Byte-level model tokenizers cannot need more than one token per input byte; reserve
    another 2,048 tokens for the service's chat template. No cache discount is assumed.
    """
    prompt = render(request, published_on=request.published_on)
    return len(prompt.system.encode()) + len(prompt.user.encode()) + 2048


def _first_choice(data: Any) -> dict[str, Any]:
    choices = data.get("choices") if isinstance(data, dict) else None
    first = choices[0] if isinstance(choices, list) and choices else None
    return first if isinstance(first, dict) else {}


def _json_cut_off(text: str) -> bool:
    """True only when the parser ran out of text, so the JSON stops mid-document."""
    try:
        json.loads(text)
    except json.JSONDecodeError as exc:
        return exc.msg.startswith("Unterminated string") or exc.pos >= len(text.rstrip())
    return False


def _usage_details(data: Any) -> dict[str, Any]:
    usage = data.get("usage") if isinstance(data, dict) else None
    details = usage.get("completion_tokens_details") if isinstance(usage, dict) else None
    return details if isinstance(details, dict) else {}


def _usage_consistent(data: Any, in_tok: int, out_tok: int, reasoning: int | None) -> bool:
    """Optional fields may be absent, but anything reported must agree with the billed counts."""
    usage = data["usage"]
    details = usage.get("completion_tokens_details")
    if details is not None and not isinstance(details, dict):
        return False
    raw = _usage_details(data).get("reasoning_tokens")
    if raw is not None and (reasoning is None or reasoning > out_tok):
        return False
    total = usage.get("total_tokens")
    return total is None or (_count(total) is not None and total == in_tok + out_tok)


class OpenRouterProvider(OpenAICompatibleProvider):
    name = "openrouter"
    hosted = True

    def __init__(
        self,
        settings: LlmSettings,
        client: Any,
        *,
        capture: Callable[[str, bytes], None] | None = None,
    ) -> None:
        self.route = validate_settings(settings)
        super().__init__(settings, client, capture=capture)

    @property
    def pilot_scope(self) -> PilotScope:
        experiment = self._settings.openrouter_experiment
        return EXPERIMENTS[experiment].scope if experiment else PilotScope()

    def validate_run(self, pricing: Pricing, limits: LlmLimits) -> None:
        """The reservation must cover exactly the adapter's actual output/timeout caps."""
        validate_settings(replace(self._settings, pricing=pricing, limits=limits))
        if (
            limits.max_output_tokens != self._settings.limits.max_output_tokens
            or limits.timeout_seconds != self._settings.limits.timeout_seconds
        ):
            raise LlmConfigError("OpenRouter pipeline and adapter limits must agree")

    def parameters(self) -> dict[str, str | int | float | bool]:
        experiment = self._settings.openrouter_experiment
        return {
            **({"experiment": experiment} if experiment else {}),
            "max_tokens": self._settings.limits.max_output_tokens,
            "timeout_seconds": self._settings.limits.timeout_seconds,
            "provider_only": self.route.provider_id,
            "zdr": True,
            "data_collection": "deny",
            "allow_fallbacks": False,
            "require_parameters": True,
            "response_format": "json_object",
            "reasoning_effort": self._settings.openrouter_reasoning_effort or "",
            "input_usd_per_mtok": 4.4,
            "output_usd_per_mtok": 22.0,
        }

    def input_fits(self, request: SummaryRequest) -> bool:
        return not request.truncated and input_token_bound(
            request
        ) + self._settings.limits.max_output_tokens <= min(self.route.context_tokens, 272_000)

    def request_body(self, request: SummaryRequest) -> dict[str, Any]:
        if not self.input_fits(request):
            raise ProviderError("input_too_long", retryable=False)
        body = super().request_body(request)
        del body["temperature"]  # neither selected endpoint advertises support
        if self.route.provider_id == "azure/eu":
            # Azure advertises max_completion_tokens, not max_tokens. With
            # require_parameters=True, sending the latter would make it ineligible.
            body["max_completion_tokens"] = body.pop("max_tokens")
        body.update(
            {
                "provider": {
                    "only": [self.route.provider_id],
                    "zdr": True,
                    "data_collection": "deny",
                    "allow_fallbacks": False,
                    "require_parameters": True,
                },
                "response_format": {"type": "json_object"},
                "reasoning": {"effort": self._settings.openrouter_reasoning_effort},
            }
        )
        return body

    def summarise(self, request: SummaryRequest) -> ProviderResponse:
        try:
            return super().summarise(request)
        except ProviderError as exc:
            # Even rate limits and transport failures consume the pilot's single attempt.
            exc.retryable = False
            raise

    def parse_response(self, data: Any, request: SummaryRequest) -> ProviderResponse:
        in_tok, out_tok, cost = self.reported_usage(data)
        metadata = self.response_metadata(data)
        reasoning = metadata["reasoning_tokens"]
        choice = _first_choice(data)
        message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
        content = message.get("content")
        has_content = isinstance(content, str) and bool(content.strip())

        def refuse(code: str) -> None:
            self._record_diagnostics(data, code, in_tok, out_tok, metadata)
            raise ProviderError(
                code,
                retryable=False,
                input_tokens=in_tok,
                output_tokens=out_tok,
                cost_usd=cost,
                **metadata,
            )

        # OpenRouter can report an upstream failure inside an HTTP 200 body.
        choices = data.get("choices") if isinstance(data, dict) else None
        choices = choices if isinstance(choices, list) else []
        if (
            (isinstance(data, dict) and data.get("error") is not None)
            or any(isinstance(c, dict) and c.get("error") is not None for c in choices)
            or choice.get("finish_reason") == "error"
        ):
            refuse("upstream_error")
        if len(choices) > 1:  # the request asks for one completion
            refuse("invalid_response")
        if (
            not isinstance(data, dict)
            or data.get("model") != self.model
            or data.get("provider") != self.route.response_provider
        ):
            refuse("route_unverified")
        if (
            in_tok is None
            or out_tok is None
            or cost is None
            or not _usage_consistent(data, in_tok, out_tok, reasoning)
        ):
            refuse("usage_unverified")
        assert in_tok is not None and out_tok is not None and cost is not None
        calculated = self._settings.pricing.cost(in_tok, out_tok)
        if (
            in_tok > input_token_bound(request)
            or out_tok > self._settings.limits.max_output_tokens
            or cost > calculated + 0.000001
        ):
            refuse("usage_exceeded")
        if (
            choice.get("finish_reason") == "content_filter"
            or choice.get("native_finish_reason") == "refusal"
            or message.get("refusal") is not None
        ):
            refuse("refused")
        if choice.get("finish_reason") == "length" or (
            choice.get("native_finish_reason") == "max_tokens"
        ):
            cap = self._settings.limits.max_output_tokens
            if has_content:
                refuse("final_json_truncated" if _json_cut_off(content) else "output_truncated")
            if reasoning == out_tok and out_tok >= cap:
                refuse("reasoning_budget_exhausted")
            refuse("output_truncated")
        if (
            choice.get("finish_reason") == "stop"
            and not has_content
            and not message.get("tool_calls")
        ):
            refuse("missing_final_content")
        try:
            response = super().parse_response(data, request)
        except ProviderError as exc:
            refuse(exc.error_class)
        if response.stop_reason != "stop" or data["choices"][0]["message"].get("tool_calls"):
            refuse("unexpected_completion")
        try:
            parsed = json.loads(response.text)
        except ValueError:
            refuse("invalid_json")
        if not isinstance(parsed, dict):
            refuse("invalid_json")
        if metadata["response_id"] is None:
            refuse("response_id_unverified")
        self._record_diagnostics(data, None, in_tok, out_tok, metadata)
        return ProviderResponse(
            response.text,
            response.model,
            in_tok,
            out_tok,
            response.stop_reason,
            self.route.response_provider,
            cost,
            metadata["response_id"],
            reasoning,
        )

    def _record_diagnostics(
        self,
        data: Any,
        failure_class: str | None,
        in_tok: int | None,
        out_tok: int | None,
        metadata: dict[str, Any],
    ) -> None:
        """Metadata beside the raw capture: never content, reasoning or upstream messages."""
        if self._capture is None:
            return
        message = _first_choice(data).get("message")
        content = message.get("content") if isinstance(message, dict) else None
        text = content if isinstance(content, str) else ""
        reasoning = metadata["reasoning_tokens"]
        body = {
            "failure_class": failure_class,
            "finish_reason": metadata["finish_reason"],
            "native_finish_reason": metadata["native_finish_reason"],
            "prompt_tokens": in_tok,
            "completion_tokens": out_tok,
            "reasoning_tokens": reasoning,
            "final_output_tokens": out_tok - reasoning
            if out_tok is not None and reasoning is not None
            else None,
            "max_output_tokens": self._settings.limits.max_output_tokens,
            "reasoning_effort": self._settings.openrouter_reasoning_effort,
            "final_content_chars": len(text),
            "final_content_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "response_id": metadata["response_id"],
            "serving_provider": metadata["serving_provider"],
            "response_model": metadata["response_model"],
        }
        try:
            self._capture("diagnostics.json", json.dumps(body, sort_keys=True).encode())
        except OSError:  # derived data; the raw capture and the billed result must still stand
            log.warning("could not record OpenRouter response diagnostics")

    @staticmethod
    def reported_usage(data: Any) -> tuple[int | None, int | None, float | None]:
        usage = data.get("usage") if isinstance(data, dict) else None
        usage = usage if isinstance(usage, dict) else {}
        in_tok, out_tok = _count(usage.get("prompt_tokens")), _count(usage.get("completion_tokens"))
        cost = usage.get("cost")
        cost = (
            float(cost)
            if isinstance(cost, (float, int))
            and not isinstance(cost, bool)
            and math.isfinite(cost)
            and cost >= 0
            else None
        )

        return in_tok, out_tok, cost

    def response_metadata(self, data: Any) -> dict[str, Any]:
        choice = _first_choice(data)
        finish, native = choice.get("finish_reason"), choice.get("native_finish_reason")
        data = data if isinstance(data, dict) else {}
        model, provider, rid = data.get("model"), data.get("provider"), data.get("id")
        # Do not persist arbitrary upstream strings: an error may echo credentials or text.
        return {
            "response_model": model
            if isinstance(model, str) and model in {r.model for r in ROUTES}
            else None,
            "serving_provider": provider
            if provider in ("Google", "Azure", "Anthropic", "OpenAI", "Amazon Bedrock")
            else None,
            "response_id": rid
            if isinstance(rid, str)
            and re.fullmatch(r"gen-[A-Za-z0-9_-]{1,180}", rid)
            and self._settings.api_key not in rid
            else None,
            "reasoning_tokens": _count(_usage_details(data).get("reasoning_tokens")),
            "finish_reason": finish if finish in _FINISH_REASONS else None,
            "native_finish_reason": native if native in _NATIVE_FINISH_REASONS else None,
        }

    def response_error(self, status: int, data: Any) -> ProviderError:
        in_tok, out_tok, cost = self.reported_usage(data)
        return ProviderError(
            _status_error(status).error_class,
            retryable=False,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=cost,
            **self.response_metadata(data),
        )
