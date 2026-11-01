"""Bounded OpenRouter pilot: explicit routes, no privacy relaxation, retries or fallback.

Public catalogue and ZDR endpoint evidence checked 2026-11-01. These are candidate routes,
not source-processing approvals. The pipeline separately refuses missing version consent.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from nzstats.research.contract import LlmLimits, ProviderError, ProviderResponse, SummaryRequest
from nzstats.research.prompt import render
from nzstats.research.providers import (
    OPENROUTER_URL,
    LlmConfigError,
    LlmSettings,
    OpenAICompatibleProvider,
    Pricing,
    _count,
    _status_error,
)


@dataclass(frozen=True)
class Route:
    model: str
    provider_id: str
    response_provider: str
    context_tokens: int


ROUTES = (
    Route("anthropic/claude-opus-5.5", "google-vertex/europe", "Google", 1_000_000),
    Route("openai/gpt-5.6-sol", "azure/eu", "Azure", 1_050_000),
)


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
        and 0 < limits.max_output_tokens <= 6_000
    ):
        raise LlmConfigError(
            "OpenRouter pilot requires zero retries, two documents and US$5 maximum"
        )
    return route


def input_token_bound(request: SummaryRequest) -> int:
    """UTF-8 byte ceiling, including framing/schema, rather than a chars/3 heuristic.

    Byte-level model tokenizers cannot need more than one token per input byte; reserve
    another 2,048 tokens for the service's chat template. No cache discount is assumed.
    """
    prompt = render(request, published_on=request.published_on)
    return len(prompt.system.encode()) + len(prompt.user.encode()) + 2048


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

    def validate_run(self, pricing: Pricing, limits: LlmLimits) -> None:
        """The reservation must cover exactly the adapter's actual output/timeout caps."""
        validate_settings(replace(self._settings, pricing=pricing, limits=limits))
        if (
            limits.max_output_tokens != self._settings.limits.max_output_tokens
            or limits.timeout_seconds != self._settings.limits.timeout_seconds
        ):
            raise LlmConfigError("OpenRouter pipeline and adapter limits must agree")

    def parameters(self) -> dict[str, str | int | float | bool]:
        return {
            "max_tokens": self._settings.limits.max_output_tokens,
            "provider_only": self.route.provider_id,
            "zdr": True,
            "data_collection": "deny",
            "allow_fallbacks": False,
            "require_parameters": True,
            "response_format": "json_object",
            "reasoning_effort": "high",
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
                "reasoning": {"effort": "high"},
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

        def refuse(code: str) -> None:
            raise ProviderError(
                code,
                retryable=False,
                input_tokens=in_tok,
                output_tokens=out_tok,
                cost_usd=cost,
                **metadata,
            )

        if (
            not isinstance(data, dict)
            or data.get("model") != self.model
            or data.get("provider") != self.route.response_provider
        ):
            refuse("route_unverified")
        if in_tok is None or out_tok is None or cost is None:
            refuse("usage_unverified")
        assert in_tok is not None and out_tok is not None and cost is not None
        calculated = self._settings.pricing.cost(in_tok, out_tok)
        if (
            in_tok > input_token_bound(request)
            or out_tok > self._settings.limits.max_output_tokens
            or cost > calculated + 0.000001
        ):
            refuse("usage_exceeded")
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
        return ProviderResponse(
            response.text,
            response.model,
            in_tok,
            out_tok,
            response.stop_reason,
            self.route.response_provider,
            cost,
            metadata["response_id"],
        )

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

    def response_metadata(self, data: Any) -> dict[str, str | None]:
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
