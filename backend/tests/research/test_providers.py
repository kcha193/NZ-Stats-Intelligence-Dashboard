"""Provider adapters and their configuration. Every HTTP call goes to an `httpx.MockTransport`."""

import json

import httpx
import pytest

from nzstats.research import providers as pv
from nzstats.research.contract import (
    DisabledProvider,
    LlmLimits,
    ProviderError,
    SectionText,
    build_request,
)

SECRET = "sk-test-SECRET-never-printed"
REAL = {
    "NZSTATS_LLM_PROVIDER": "anthropic",
    "NZSTATS_LLM_MODEL": "claude-opus-5-5",
    "NZSTATS_LLM_API_KEY": SECRET,
    "NZSTATS_LLM_INPUT_USD_PER_MTOK": "4",
    "NZSTATS_LLM_OUTPUT_USD_PER_MTOK": "20",
}
LOCAL = {
    "NZSTATS_LLM_PROVIDER": "openai_compatible",
    "NZSTATS_LLM_MODEL": "local-model",
    "NZSTATS_LLM_BASE_URL": "http://127.0.0.1:8080/v1",
    "NZSTATS_LLM_INPUT_USD_PER_MTOK": "0",
    "NZSTATS_LLM_OUTPUT_USD_PER_MTOK": "0",
}
REQUEST = build_request(
    7, {0: SectionText("SYNTHETIC FIXTURE. Growth is expected to be 2.5% in 2027.", 1, 1)},
    prompt_version="outlook-v1", published_on="2026-08-13",
)  # fmt: skip


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _anthropic_ok(text='{"ok": 1}', stop="end_turn", usage=(120, 40)):
    def handler(request: httpx.Request) -> httpx.Response:
        handler.seen.append(request)
        return httpx.Response(200, json={
            "model": "claude-opus-5-5", "stop_reason": stop,
            "content": [{"type": "thinking", "thinking": ""}, {"type": "text", "text": text}],
            "usage": {"input_tokens": usage[0], "output_tokens": usage[1]}})  # fmt: skip

    handler.seen = []
    return handler


# --- configuration ---------------------------------------------------------------------------
def test_no_configuration_means_the_disabled_provider():
    settings = pv.load_llm_settings({})
    assert settings.provider == "disabled"
    assert isinstance(pv.build_provider(settings), DisabledProvider)


def test_the_fake_provider_cannot_be_selected_from_the_environment():
    with pytest.raises(pv.LlmConfigError, match="provider"):
        pv.load_llm_settings({"NZSTATS_LLM_PROVIDER": "fake"})


@pytest.mark.parametrize(
    "missing",
    ["NZSTATS_LLM_MODEL", "NZSTATS_LLM_API_KEY", "NZSTATS_LLM_INPUT_USD_PER_MTOK",
     "NZSTATS_LLM_OUTPUT_USD_PER_MTOK"],
)  # fmt: skip
def test_a_real_provider_needs_model_key_and_prices(missing):
    env = {k: v for k, v in REAL.items() if k != missing}
    with pytest.raises(pv.LlmConfigError, match=missing):
        pv.load_llm_settings(env)


@pytest.mark.parametrize(
    ("name", "value"),
    [("NZSTATS_LLM_INPUT_USD_PER_MTOK", "nan"), ("NZSTATS_LLM_OUTPUT_USD_PER_MTOK", "-1"),
     ("NZSTATS_LLM_MAX_RUN_USD", "0"), ("NZSTATS_LLM_MAX_RUN_USD", "inf"),
     ("NZSTATS_LLM_MAX_OUTPUT_TOKENS", "0"), ("NZSTATS_LLM_MAX_RETRIES", "9"),
     ("NZSTATS_LLM_TIMEOUT_SECONDS", "x"), ("NZSTATS_LLM_MAX_DOCUMENTS", "0")],
)  # fmt: skip
def test_limits_and_prices_must_be_finite_and_in_range(name, value):
    with pytest.raises(pv.LlmConfigError, match=name):
        pv.load_llm_settings({**REAL, name: value})


def test_limits_come_from_the_environment():
    s = pv.load_llm_settings({**REAL, "NZSTATS_LLM_MAX_OUTPUT_TOKENS": "16000",
                              "NZSTATS_LLM_MAX_RUN_USD": "0.5", "NZSTATS_LLM_MAX_RETRIES": "1"})  # fmt: skip
    assert (s.limits.max_output_tokens, s.limits.max_run_usd, s.limits.max_retries) == (
        16000,
        0.5,
        1,
    )
    assert s.pricing.cost(1_000_000, 1_000_000) == pytest.approx(24.0)


def test_the_api_key_never_appears_in_repr_or_errors():
    s = pv.load_llm_settings(REAL)
    assert SECRET not in repr(s) and SECRET not in str(s)
    provider = pv.build_provider(s, client=_client(lambda r: httpx.Response(401, text=SECRET)))
    with pytest.raises(ProviderError) as exc:
        provider.summarise(REQUEST)
    assert SECRET not in str(exc.value) and exc.value.error_class == "auth_error"


def test_a_base_url_is_refused_for_anthropic_so_the_key_cannot_be_redirected():
    with pytest.raises(pv.LlmConfigError, match="NZSTATS_LLM_BASE_URL"):
        pv.load_llm_settings({**REAL, "NZSTATS_LLM_BASE_URL": "https://evil.example/v1"})


@pytest.mark.parametrize(
    ("url", "ok", "hosted"),
    [("http://127.0.0.1:8080/v1", True, False), ("http://localhost:11434/v1", True, False),
     ("http://[::1]:8000/v1", True, False), ("https://api.openai.com/v1", True, True),
     ("http://192.168.1.5:8080/v1", False, None), ("ftp://127.0.0.1/v1", False, None),
     ("https://user:pw@api.example.com/v1", False, None)],
)  # fmt: skip
def test_openai_compatible_base_urls_and_locality(url, ok, hosted):
    env = {**LOCAL, "NZSTATS_LLM_BASE_URL": url}
    if not ok:
        with pytest.raises(pv.LlmConfigError, match="NZSTATS_LLM_BASE_URL"):
            pv.load_llm_settings(env)
        return
    assert pv.build_provider(pv.load_llm_settings(env)).hosted is hosted


# --- Anthropic adapter -------------------------------------------------------------------------
def test_anthropic_request_shape_and_usage():
    handler = _anthropic_ok()
    s = pv.load_llm_settings({**REAL, "NZSTATS_LLM_MAX_OUTPUT_TOKENS": "16000"})
    provider = pv.build_provider(s, client=_client(handler))
    assert provider.hosted is True and provider.name == "anthropic"
    response = provider.summarise(REQUEST)
    sent = handler.seen[0]
    assert str(sent.url) == "https://api.anthropic.com/v1/messages"
    assert sent.headers["x-api-key"] == SECRET
    assert sent.headers["anthropic-version"] == pv.ANTHROPIC_VERSION
    body = json.loads(sent.content)
    assert body["model"] == "claude-opus-5-5" and body["max_tokens"] == 16000
    assert "temperature" not in body and "top_p" not in body  # a 400 on API version 2026-10-21
    assert "untrusted" in body["system"].lower()
    assert body["messages"][0]["role"] == "user" and "<<<SECTION" in body["messages"][0]["content"]
    assert (response.text, response.input_tokens, response.output_tokens) == ('{"ok": 1}', 120, 40)
    assert provider.parameters() == {"anthropic_version": pv.ANTHROPIC_VERSION, "max_tokens": 16000}


@pytest.mark.parametrize(
    ("stop", "error_class"), [("max_tokens", "output_truncated"), ("refusal", "refused")]
)
def test_anthropic_truncated_or_refused_output_is_a_non_retryable_error(stop, error_class):
    provider = pv.build_provider(
        pv.load_llm_settings(REAL), client=_client(_anthropic_ok(stop=stop))
    )
    with pytest.raises(ProviderError) as exc:
        provider.summarise(REQUEST)
    assert (exc.value.error_class, exc.value.retryable) == (error_class, False)


@pytest.mark.parametrize(
    ("status", "error_class", "retryable"),
    [(408, "timeout", True), (409, "conflict", True), (429, "rate_limited", True),
     (500, "server_error", True), (529, "overloaded", True), (400, "bad_request", False),
     (401, "auth_error", False), (403, "auth_error", False), (404, "bad_request", False),
     (302, "http_error", False)],
)  # fmt: skip
def test_http_statuses_map_to_fixed_error_classes(status, error_class, retryable):
    provider = pv.build_provider(
        pv.load_llm_settings(REAL),
        client=_client(lambda r: httpx.Response(status, headers={"location": "https://x"}, text="boom")),
    )  # fmt: skip
    with pytest.raises(ProviderError) as exc:
        provider.summarise(REQUEST)
    assert (exc.value.error_class, exc.value.retryable) == (error_class, retryable)


def test_timeouts_network_errors_bad_json_and_oversized_bodies():
    def raiser(exc):
        def handler(request):
            raise exc

        return handler

    cases = [
        (raiser(httpx.ReadTimeout("slow")), "timeout", True),
        (raiser(httpx.ConnectError("down")), "network_error", True),
        (lambda r: httpx.Response(200, text="not json"), "invalid_response", False),
        (lambda r: httpx.Response(200, json={"content": "wrong shape"}), "invalid_response", False),
        (lambda r: httpx.Response(200, content=b"x" * (pv.MAX_RESPONSE_BYTES + 1)),
         "response_too_large", False),
    ]  # fmt: skip
    for handler, error_class, retryable in cases:
        provider = pv.build_provider(pv.load_llm_settings(REAL), client=_client(handler))
        with pytest.raises(ProviderError) as exc:
            provider.summarise(REQUEST)
        assert (exc.value.error_class, exc.value.retryable) == (error_class, retryable)


# --- OpenAI-compatible adapter -----------------------------------------------------------------
def test_openai_compatible_request_shape_without_a_key():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={
            "model": "local-model", "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5}})  # fmt: skip

    provider = pv.build_provider(pv.load_llm_settings(LOCAL), client=_client(handler))
    response = provider.summarise(REQUEST)
    assert str(seen[0].url) == "http://127.0.0.1:8080/v1/chat/completions"
    assert "authorization" not in seen[0].headers
    body = json.loads(seen[0].content)
    assert [m["role"] for m in body["messages"]] == ["system", "user"] and body["temperature"] == 0
    assert (response.input_tokens, response.output_tokens) == (10, 5)


def test_openai_compatible_length_finish_is_truncation_and_a_key_is_a_bearer_token():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "{"},
                                                      "finish_reason": "length"}]})  # fmt: skip

    env = {**LOCAL, "NZSTATS_LLM_API_KEY": SECRET}
    provider = pv.build_provider(pv.load_llm_settings(env), client=_client(handler))
    with pytest.raises(ProviderError) as exc:
        provider.summarise(REQUEST)
    assert exc.value.error_class == "output_truncated"
    assert seen[0].headers["authorization"] == f"Bearer {SECRET}"


# --- the fake provider -------------------------------------------------------------------------
def test_fake_provider_is_deterministic_and_can_fail_first():
    fake = pv.FakeProvider({7: '{"a": 1}'}, usage=(100, 20),
                           fail_first=[ProviderError("rate_limited", retryable=True)])  # fmt: skip
    with pytest.raises(ProviderError):
        fake.summarise(REQUEST)
    assert fake.summarise(REQUEST).text == '{"a": 1}'
    assert len(fake.calls) == 2 and fake.hosted is False
    estimated = pv.FakeProvider(lambda req: "{}", usage=None).summarise(REQUEST)
    assert estimated.input_tokens is None


def test_token_estimate_is_conservative():
    assert pv.estimate_tokens(3000) == 1000 and pv.estimate_tokens(1) == 1
    assert pv.request_chars(REQUEST) > len(REQUEST.sections[0].text)


def test_default_limits_are_unchanged_by_default_settings():
    assert pv.load_llm_settings({}).limits == LlmLimits()


def test_a_truncated_or_refused_response_carries_its_billed_usage():
    provider = pv.build_provider(pv.load_llm_settings(REAL),
                                 client=_client(_anthropic_ok(stop="max_tokens", usage=(900, 4000))))  # fmt: skip
    with pytest.raises(ProviderError) as exc:
        provider.summarise(REQUEST)
    assert (exc.value.input_tokens, exc.value.output_tokens) == (900, 4000)
