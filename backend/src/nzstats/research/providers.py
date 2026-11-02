"""LLM provider adapters and their configuration. Disabled unless the environment says otherwise.

Configuration comes from the environment only (`load_llm_settings`). With nothing set, the provider
is `DisabledProvider`: no network, no cost. A real provider needs an explicit provider name, model and
prices; the per-source permission (`Institution.llm_refusal`) is checked by the pipeline as well.

Adapters speak plain HTTP through httpx: no vendor SDK is imported (a test enforces this), so the
dependency set and the Docker image are unchanged. Every failure becomes a `ProviderError` with a
fixed error class; upstream messages and the API key never reach logs, the database or output.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import httpx

from nzstats.research.contract import (
    DisabledProvider,
    LlmLimits,
    Provider,
    ProviderError,
    ProviderResponse,
    SummaryRequest,
)
from nzstats.research.prompt import render

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = (
    "2026-10-21"  # on this version temperature/top_p/top_k are rejected, so none is sent
)
MAX_RESPONSE_BYTES = 2_000_000
PROVIDERS = ("disabled", "anthropic", "openai_compatible", "openrouter")
OPENROUTER_URL = "https://openrouter.ai/api/v1"
_LOOPBACK = frozenset({"localhost", "127.0.0.1", "::1"})
_RETRYABLE = {408: "timeout", 409: "conflict", 429: "rate_limited", 529: "overloaded"}


class LlmConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Pricing:
    input_usd_per_mtok: float = 0.0
    output_usd_per_mtok: float = 0.0

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens * self.input_usd_per_mtok + output_tokens * self.output_usd_per_mtok
        ) / 1e6


@dataclass(frozen=True)
class LlmSettings:
    provider: str = "disabled"
    model: str = "none"
    api_key: str | None = field(default=None, repr=False)
    base_url: str | None = None
    pricing: Pricing = Pricing()
    limits: LlmLimits = LlmLimits()
    openrouter_provider: str | None = None
    openrouter_reasoning_effort: str | None = None
    # A separately authorised ledger scope. The bounded pilot runner sets it; no environment does.
    openrouter_experiment: str | None = None

    def __str__(self) -> str:
        return repr(self)


def is_hosted(settings: LlmSettings) -> bool:
    """True when text sent to this provider leaves the machine; only a loopback base URL counts as local."""
    if settings.provider == "anthropic":
        return True
    return urlsplit(settings.base_url or "").hostname not in _LOOPBACK


def estimate_tokens(chars: int) -> int:
    """A deliberately high token estimate (3 characters per token) for budget checks."""
    return max(1, math.ceil(chars / 3))


def request_chars(request: SummaryRequest) -> int:
    """Characters sent for this request: rules, schema, framing and section text."""
    rendered = render(request, published_on=request.published_on)
    return len(rendered.system) + len(rendered.user)


def _number(
    env: Mapping[str, str], name: str, default: float | None, low: float, high: float
) -> float:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        if default is None:
            raise LlmConfigError(f"{name} is required for a real provider")
        return default
    try:
        value = float(raw)
    except ValueError:
        raise LlmConfigError(f"{name} must be a number") from None
    if not math.isfinite(value) or not low <= value <= high:
        raise LlmConfigError(f"{name} must be a finite number from {low:g} to {high:g}")
    return value


def _whole(env: Mapping[str, str], name: str, default: int, low: int, high: int) -> int:
    value = _number(env, name, default, low, high)
    if value != int(value):
        raise LlmConfigError(f"{name} must be a whole number")
    return int(value)


def _base_url(url: str) -> str:
    parts = urlsplit(url)
    try:
        host = parts.hostname
        parts.port  # noqa: B018 - validates the port
    except ValueError:
        raise LlmConfigError("NZSTATS_LLM_BASE_URL is not a valid URL") from None
    if parts.username or parts.password or not host:
        raise LlmConfigError("NZSTATS_LLM_BASE_URL must have a host and no credentials")
    if parts.scheme == "https" or (parts.scheme == "http" and host in _LOOPBACK):
        return url.rstrip("/")
    raise LlmConfigError("NZSTATS_LLM_BASE_URL must be https, or http on a loopback address")


def _openrouter_host(url: str | None) -> bool:
    """Match the hostname httpx actually sends, including IDNA dot aliases and DNS root dots."""
    try:
        host = httpx.URL(url or "").host.rstrip(".").lower()
    except httpx.InvalidURL:
        raise LlmConfigError("NZSTATS_LLM_BASE_URL is not a valid URL") from None
    return host == "openrouter.ai" or host.endswith(".openrouter.ai")


def load_llm_settings(env: Mapping[str, str]) -> LlmSettings:
    provider = (env.get("NZSTATS_LLM_PROVIDER") or "disabled").strip()
    if provider not in PROVIDERS:
        raise LlmConfigError(f"unknown provider {provider!r}; one of {', '.join(PROVIDERS)}")
    if provider == "disabled":
        return LlmSettings()
    model = (env.get("NZSTATS_LLM_MODEL") or "").strip()
    if not model or len(model) > 100 or any(c.isspace() for c in model):
        raise LlmConfigError("NZSTATS_LLM_MODEL is required (one model id, no spaces)")
    key = env.get("NZSTATS_LLM_API_KEY") or None
    base = env.get("NZSTATS_LLM_BASE_URL") or None
    if provider == "anthropic":
        if key is None:
            raise LlmConfigError("NZSTATS_LLM_API_KEY is required for anthropic")
        if base is not None:
            raise LlmConfigError("NZSTATS_LLM_BASE_URL is not used with anthropic (fixed endpoint)")
    elif provider == "openrouter":
        if base is not None and base != OPENROUTER_URL:
            raise LlmConfigError("OpenRouter requires its fixed HTTPS endpoint")
        base = OPENROUTER_URL
    else:
        if base is None:
            raise LlmConfigError("NZSTATS_LLM_BASE_URL is required for openai_compatible")
        base = _base_url(base)
        if _openrouter_host(base):
            raise LlmConfigError("OpenRouter requires NZSTATS_LLM_PROVIDER=openrouter")
    pricing = Pricing(
        _number(env, "NZSTATS_LLM_INPUT_USD_PER_MTOK", None, 0, 10_000),
        _number(env, "NZSTATS_LLM_OUTPUT_USD_PER_MTOK", None, 0, 10_000),
    )
    defaults = LlmLimits()
    limits = LlmLimits(
        max_input_chars=_whole(env, "NZSTATS_LLM_MAX_INPUT_CHARS", defaults.max_input_chars, 1_000, 2_000_000),
        max_output_tokens=_whole(env, "NZSTATS_LLM_MAX_OUTPUT_TOKENS", defaults.max_output_tokens, 1, 128_000),
        max_documents_per_run=_whole(env, "NZSTATS_LLM_MAX_DOCUMENTS", defaults.max_documents_per_run, 1, 100),
        timeout_seconds=_number(env, "NZSTATS_LLM_TIMEOUT_SECONDS", defaults.timeout_seconds, 1, 1_800),
        max_retries=_whole(env, "NZSTATS_LLM_MAX_RETRIES", defaults.max_retries, 0, 5),
        max_run_usd=_number(env, "NZSTATS_LLM_MAX_RUN_USD", defaults.max_run_usd, 0.0001, 1_000),
        max_period_usd=_number(env, "NZSTATS_LLM_MAX_PERIOD_USD", defaults.max_period_usd, 0.0001, 10_000),
    )  # fmt: skip
    settings = LlmSettings(
        provider,
        model,
        key,
        base,
        pricing,
        limits,
        env.get("NZSTATS_OPENROUTER_PROVIDER"),
        env.get("NZSTATS_OPENROUTER_REASONING_EFFORT"),
    )
    if provider == "openrouter":
        from nzstats.research.openrouter import validate_settings

        validate_settings(settings)
    return settings


def build_provider(settings: LlmSettings, *, client: httpx.Client | None = None) -> Provider:
    if settings.provider == "disabled":
        return DisabledProvider()
    if settings.provider == "openrouter":
        from nzstats.research.openrouter import OpenRouterProvider, validate_settings

        validate_settings(settings)
    elif _openrouter_host(settings.base_url):
        raise LlmConfigError("OpenRouter requires NZSTATS_LLM_PROVIDER=openrouter")
    http = client or httpx.Client(
        timeout=settings.limits.timeout_seconds, follow_redirects=False, trust_env=False
    )
    if settings.provider == "anthropic":
        return AnthropicProvider(settings, http)
    if settings.provider == "openrouter":
        return OpenRouterProvider(settings, http)
    return OpenAICompatibleProvider(settings, http)


class _HttpProvider:
    name = "http"
    hosted = True

    def __init__(
        self,
        settings: LlmSettings,
        client: httpx.Client,
        *,
        capture: Callable[[str, bytes], None] | None = None,
    ) -> None:
        self.model = settings.model
        self._settings = settings
        self._client = client
        self._capture = capture

    def parameters(self) -> dict[str, str | int | float | bool]:
        raise NotImplementedError

    def _post(self, url: str, headers: Mapping[str, str], body: Mapping[str, Any]) -> Any:
        request_bytes = json.dumps(dict(body), ensure_ascii=False, separators=(",", ":")).encode()
        credential = (self._settings.api_key or "").encode()
        if credential and credential in request_bytes:
            raise ProviderError("credential_in_request", retryable=False)
        if self._capture is not None:
            self._capture("request.json", request_bytes)
        status, data, received = None, bytearray(), 0
        failure = None
        try:
            with self._client.stream(
                "POST", url, headers=dict(headers), json=dict(body),
                timeout=self._settings.limits.timeout_seconds,
                follow_redirects=False,
            ) as response:  # fmt: skip
                status = response.status_code
                for chunk in response.iter_bytes():
                    received += len(chunk)
                    data.extend(chunk[: MAX_RESPONSE_BYTES - len(data)])
                    if received > MAX_RESPONSE_BYTES:
                        raise ProviderError("response_too_large", retryable=False)
        except httpx.TimeoutException:
            failure = ProviderError("timeout", retryable=True)
        except httpx.TransportError:
            failure = ProviderError("network_error", retryable=True)
        except ProviderError as exc:
            failure = exc
        raw = bytes(data)
        redacted = bool(credential and credential in raw)
        retained = raw.replace(credential, b"[REDACTED_API_KEY]") if credential else raw
        if self._capture is not None:
            self._capture("response.bin", retained)
            self._capture(
                "response-status.json",
                json.dumps(
                    {
                        "http_status": status,
                        "complete": failure is None,
                        "truncated": received > MAX_RESPONSE_BYTES,
                        "received_bytes": received,
                        "retained_bytes": len(retained),
                        "received_prefix_sha256": hashlib.sha256(raw).hexdigest(),
                        "credential_redacted": redacted,
                        "error_class": "credential_echo"
                        if redacted
                        else failure.error_class
                        if failure
                        else None,
                    }
                ).encode(),
            )
        if failure is not None:
            raise failure
        if redacted and status == 200:
            raise ProviderError("credential_echo", retryable=False)
        try:
            parsed = json.loads(bytes(data))
        except ValueError:
            if status != 200:
                raise self.response_error(status, None) from None
            raise ProviderError("invalid_response", retryable=False) from None
        if status != 200:
            raise self.response_error(status, parsed)
        return parsed

    def response_error(self, status: int, data: Any) -> ProviderError:
        return _status_error(status)


def _status_error(status: int) -> ProviderError:
    if status in _RETRYABLE:
        return ProviderError(_RETRYABLE[status], retryable=True)
    if status >= 500:
        return ProviderError("server_error", retryable=True)
    if status in (401, 403):
        return ProviderError("auth_error", retryable=False)
    if 400 <= status < 500:
        return ProviderError("bad_request", retryable=False)
    return ProviderError("http_error", retryable=False)  # redirects and anything unexpected


def _count(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


class AnthropicProvider(_HttpProvider):
    """The Claude Messages API over HTTPS. Hosted: the text is processed by a third party."""

    name = "anthropic"
    hosted = True

    def parameters(self) -> dict[str, str | int | float | bool]:
        return {
            "anthropic_version": ANTHROPIC_VERSION,
            "max_tokens": self._settings.limits.max_output_tokens,
        }

    def summarise(self, request: SummaryRequest) -> ProviderResponse:
        prompt = render(request, published_on=request.published_on)
        body = {
            "model": self.model,
            "max_tokens": self._settings.limits.max_output_tokens,
            "system": prompt.system,
            "messages": [{"role": "user", "content": prompt.user}],
        }
        headers = {"x-api-key": self._settings.api_key or "", "anthropic-version": ANTHROPIC_VERSION,
                   "content-type": "application/json"}  # fmt: skip
        data = self._post(ANTHROPIC_URL, headers, body)
        try:
            blocks = data["content"]
            text = "".join(b["text"] for b in blocks if b.get("type") == "text")
            stop, usage = data.get("stop_reason"), data.get("usage") or {}
        except (KeyError, TypeError, AttributeError):
            raise ProviderError("invalid_response", retryable=False) from None
        tokens = _count(usage.get("input_tokens")), _count(usage.get("output_tokens"))
        if stop in ("max_tokens", "refusal"):
            raise ProviderError("output_truncated" if stop == "max_tokens" else "refused",
                                retryable=False, input_tokens=tokens[0], output_tokens=tokens[1])  # fmt: skip
        return ProviderResponse(text, str(data.get("model") or self.model), *tokens, stop)


class OpenAICompatibleProvider(_HttpProvider):
    """A `/chat/completions` endpoint: OpenAI, or a local server (llama.cpp, vLLM, Ollama) on loopback."""

    name = "openai_compatible"

    def __init__(
        self,
        settings: LlmSettings,
        client: httpx.Client,
        *,
        capture: Callable[[str, bytes], None] | None = None,
    ) -> None:
        super().__init__(settings, client, capture=capture)
        self.hosted = is_hosted(settings)

    def parameters(self) -> dict[str, str | int | float | bool]:
        return {"max_tokens": self._settings.limits.max_output_tokens, "temperature": 0}

    def request_body(self, request: SummaryRequest) -> dict[str, Any]:
        prompt = render(request, published_on=request.published_on)
        return {
            "model": self.model,
            "max_tokens": self._settings.limits.max_output_tokens,
            "temperature": 0,
            "messages": [{"role": "system", "content": prompt.system},
                         {"role": "user", "content": prompt.user}],
        }  # fmt: skip

    def summarise(self, request: SummaryRequest) -> ProviderResponse:
        headers = {"content-type": "application/json"}
        if self._settings.api_key:
            headers["authorization"] = f"Bearer {self._settings.api_key}"
        data = self._post(
            f"{self._settings.base_url}/chat/completions", headers, self.request_body(request)
        )
        return self.parse_response(data, request)

    def parse_response(self, data: Any, request: SummaryRequest) -> ProviderResponse:
        try:
            choice = data["choices"][0]
            text, finish = choice["message"]["content"], choice.get("finish_reason")
            usage = data.get("usage") or {}
            if not isinstance(text, str):
                raise TypeError
        except (KeyError, IndexError, TypeError, AttributeError):
            raise ProviderError("invalid_response", retryable=False) from None
        tokens = _count(usage.get("prompt_tokens")), _count(usage.get("completion_tokens"))
        if finish in ("length", "content_filter"):
            raise ProviderError("output_truncated" if finish == "length" else "refused",
                                retryable=False, input_tokens=tokens[0], output_tokens=tokens[1])  # fmt: skip
        return ProviderResponse(text, str(data.get("model") or self.model), *tokens, finish)


class FakeProvider:
    """Deterministic canned output for tests and offline evaluation. Never selectable by configuration."""

    name = "fake"

    def __init__(
        self,
        responses: Callable[[SummaryRequest], str] | Mapping[int, str] | str,
        *,
        model: str = "fake-1",
        hosted: bool = False,
        usage: tuple[int, int] | None = (1_000, 200),
        fail_first: Sequence[ProviderError] = (),
        latency_seconds: float = 0.0,
    ) -> None:
        self.model, self.hosted, self._usage = model, hosted, usage
        self._responses, self._failures = responses, list(fail_first)
        self._latency = latency_seconds
        self.calls: list[SummaryRequest] = []

    def parameters(self) -> dict[str, str | int | float | bool]:
        return {"fake": True}

    def summarise(self, request: SummaryRequest) -> ProviderResponse:
        self.calls.append(request)
        if self._latency:
            time.sleep(self._latency)
        if self._failures:
            raise self._failures.pop(0)
        if callable(self._responses):
            text = self._responses(request)
        elif isinstance(self._responses, str):
            text = self._responses
        else:
            text = self._responses[request.version_id]
        usage = self._usage or (None, None)
        return ProviderResponse(text, self.model, usage[0], usage[1], "end_turn")
