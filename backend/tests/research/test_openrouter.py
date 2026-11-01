"""SYNTHETIC FIXTURE. No inference endpoint is contacted."""

import json
from dataclasses import replace

import httpx
import pytest

from nzstats.research import providers as pv
from nzstats.research.contract import ProviderError

from .test_providers import REQUEST

ENV = {
    "NZSTATS_LLM_PROVIDER": "openrouter",
    "NZSTATS_LLM_MODEL": "anthropic/claude-opus-5.5",
    "NZSTATS_OPENROUTER_PROVIDER": "google-vertex/europe",
    "NZSTATS_LLM_API_KEY": "synthetic-credential",
    "NZSTATS_LLM_INPUT_USD_PER_MTOK": "4.4",
    "NZSTATS_LLM_OUTPUT_USD_PER_MTOK": "22",
    "NZSTATS_LLM_MAX_RETRIES": "0",
    "NZSTATS_LLM_MAX_DOCUMENTS": "2",
    "NZSTATS_LLM_MAX_INPUT_CHARS": "45000",
    "NZSTATS_LLM_MAX_OUTPUT_TOKENS": "6000",
    "NZSTATS_LLM_MAX_RUN_USD": "5",
    "NZSTATS_LLM_MAX_PERIOD_USD": "5",
    "NZSTATS_OPENROUTER_REASONING_EFFORT": "low",
}


def envelope(**changes):
    return {
        "id": "gen-synthetic-1",
        "provider": "Google",
        "model": "anthropic/claude-opus-5.5",
        "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20, "cost": 0.00088},
        **changes,
    }


def provider(handler, env=None, **client_options):
    return pv.build_provider(
        pv.load_llm_settings(ENV if env is None else env),
        client=httpx.Client(transport=httpx.MockTransport(handler), **client_options),
    )


def test_request_pins_privacy_route_and_disables_tools_and_fallbacks():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=envelope())

    p = provider(handler)
    response = p.summarise(REQUEST)
    sent = seen[0]
    assert str(sent.url) == "https://openrouter.ai/api/v1/chat/completions"
    body = json.loads(sent.content)
    assert body["provider"] == {
        "only": ["google-vertex/europe"],
        "zdr": True,
        "data_collection": "deny",
        "allow_fallbacks": False,
        "require_parameters": True,
    }
    assert body["response_format"] == {"type": "json_object"}
    assert body["reasoning"] == {"effort": "low"}
    assert body["max_tokens"] == 6000
    assert not {"temperature", "tools", "plugins", "models", "route", "transforms"} & body.keys()
    assert (response.serving_provider, response.cost_usd, response.response_id) == (
        "Google",
        0.00088,
        "gen-synthetic-1",
    )
    assert p.parameters()["provider_only"] == "google-vertex/europe"


@pytest.mark.parametrize(
    "change",
    [
        {"NZSTATS_LLM_API_KEY": ""},
        {"NZSTATS_OPENROUTER_PROVIDER": "anthropic"},
        {"NZSTATS_OPENROUTER_PROVIDER": "google-vertex"},
        {"NZSTATS_LLM_BASE_URL": "http://openrouter.ai/api/v1"},
        {"NZSTATS_LLM_BASE_URL": "https://evil.example/v1"},
        {"NZSTATS_LLM_BASE_URL": "https://openrouter.ai/api/v1?x=y"},
        {"NZSTATS_LLM_MAX_RETRIES": "1"},
        {"NZSTATS_LLM_MAX_DOCUMENTS": "3"},
        {"NZSTATS_LLM_MAX_RUN_USD": "6"},
        {"NZSTATS_LLM_MAX_PERIOD_USD": "6"},
        {"NZSTATS_LLM_MAX_INPUT_CHARS": "45001"},
        {"NZSTATS_LLM_MAX_OUTPUT_TOKENS": "12001"},
        {"NZSTATS_LLM_INPUT_USD_PER_MTOK": "0"},
        {"NZSTATS_LLM_OUTPUT_USD_PER_MTOK": "0"},
        {"NZSTATS_LLM_MODEL": "openrouter/auto"},
    ],
)
def test_unsafe_configuration_is_rejected(change):
    with pytest.raises(pv.LlmConfigError):
        pv.load_llm_settings({**ENV, **change})


def test_generic_adapter_cannot_bypass_openrouter_controls():
    with pytest.raises(pv.LlmConfigError):
        pv.load_llm_settings(
            {
                **ENV,
                "NZSTATS_LLM_PROVIDER": "openai_compatible",
                "NZSTATS_LLM_BASE_URL": "https://openrouter.ai/api/v1",
            }
        )


@pytest.mark.parametrize(
    "host", ["openrouter.ai.", "openrouter。ai", "openrouter．ai", "openrouter｡ai"]
)
def test_transport_normalised_host_aliases_cannot_bypass_privacy_controls(host):
    from .test_providers import LOCAL

    env = {**LOCAL, "NZSTATS_LLM_BASE_URL": f"https://{host}/api/v1"}
    with pytest.raises(pv.LlmConfigError):
        pv.load_llm_settings(env)
    with pytest.raises(pv.LlmConfigError):
        pv.build_provider(
            replace(pv.load_llm_settings(LOCAL), base_url=env["NZSTATS_LLM_BASE_URL"])
        )


def test_direct_settings_construction_cannot_bypass_validation():
    s = pv.load_llm_settings(ENV)
    with pytest.raises(pv.LlmConfigError):
        pv.build_provider(replace(s, api_key=None))


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (400, "bad_request"),
        (401, "auth_error"),
        (403, "auth_error"),
        (404, "bad_request"),
        (429, "rate_limited"),
        (500, "server_error"),
        (307, "http_error"),
    ],
)
def test_http_failures_are_sanitised_single_attempts_and_redirects_never_followed(status, error):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status,
            headers={"location": "https://evil.example"},
            text="synthetic-credential full document",
        )

    p = provider(handler, follow_redirects=True)
    with pytest.raises(ProviderError) as exc:
        p.summarise(REQUEST)
    assert exc.value.error_class == error
    assert not exc.value.retryable
    assert "synthetic-credential" not in str(exc.value)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"model": "different-model"},
        {"provider": "Anthropic"},
        {"provider": None},
        {"model": None},
        {"usage": {}},
        {"usage": {"prompt_tokens": True, "completion_tokens": 20, "cost": 0.001}},
        {"usage": {"prompt_tokens": 100, "completion_tokens": -1, "cost": 0.001}},
        {"usage": {"prompt_tokens": 100, "completion_tokens": 6001, "cost": 0.14}},
        {"usage": {"prompt_tokens": 1000000, "completion_tokens": 20, "cost": 4.5}},
        {"usage": {"prompt_tokens": 100, "completion_tokens": 20, "cost": 9}},
        {"usage": {"prompt_tokens": 100, "completion_tokens": 20, "cost": float("nan")}},
        {"usage": {"prompt_tokens": 100, "completion_tokens": 20, "cost": -1}},
        {"choices": [{"message": {"content": "not JSON"}, "finish_reason": "stop"}]},
        {"choices": [{"message": {"content": "{}"}, "finish_reason": "length"}]},
        {
            "choices": [
                {"message": {"content": "{}", "tool_calls": [{"id": "x"}]}, "finish_reason": "stop"}
            ]
        },
    ],
)
def test_unverifiable_response_is_rejected_without_retry(changes):
    p = provider(lambda r: httpx.Response(200, text=json.dumps(envelope(**changes))))
    with pytest.raises(ProviderError) as exc:
        p.summarise(REQUEST)
    assert not exc.value.retryable


def test_timeout_and_malformed_envelope_do_not_leak_or_retry():
    def timeout(request):
        raise httpx.ReadTimeout("synthetic-credential")

    for handler in [timeout, lambda r: httpx.Response(200, text="not JSON")]:
        with pytest.raises(ProviderError) as exc:
            provider(handler).summarise(REQUEST)
        assert not exc.value.retryable
        assert "synthetic-credential" not in str(exc.value)


def test_comparison_model_requires_its_own_exact_provider():
    def handler(request):
        body = json.loads(request.content)
        assert body["max_completion_tokens"] == 6000
        assert "max_tokens" not in body
        return httpx.Response(200, json=envelope(model="openai/gpt-5.6-sol", provider="Azure"))

    p = provider(
        handler,
        {
            **ENV,
            "NZSTATS_LLM_MODEL": "openai/gpt-5.6-sol",
            "NZSTATS_OPENROUTER_PROVIDER": "azure/eu",
        },
    )
    assert p.summarise(REQUEST).serving_provider == "Azure"
