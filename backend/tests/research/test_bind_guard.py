"""Phase 3F: published research is served without authentication, so the server refuses to expose it beyond loopback.

The research routes have no login. `nzstats serve` therefore refuses to start with `NZSTATS_PUBLIC_RESEARCH=1` on a
non-loopback address unless the operator states, with `NZSTATS_RESEARCH_ALLOW_NONLOOPBACK=1`, that something else
(a loopback-only published port, a private network, an authenticating proxy) limits who can connect.
"""

import json

import pytest

from nzstats.cli import main
from nzstats.research.api import ALLOW_NONLOOPBACK_ENV, bind_refusal

ON = {"NZSTATS_PUBLIC_RESEARCH": "1"}


@pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.2", "::1", "localhost", "LOCALHOST"])
def test_loopback_hosts_are_allowed_with_research_on(host):
    assert bind_refusal(host, ON) is None


@pytest.mark.parametrize(
    "host",
    ["0.0.0.0", "::", "", "192.168.1.20", "10.0.0.5", "nas.local", "example.org", "::ffff:0.0.0.0"],
)
def test_any_other_host_is_refused_with_research_on(host):
    reason = bind_refusal(host, ON)
    assert reason and "without authentication" in reason and ALLOW_NONLOOPBACK_ENV in reason


def test_research_off_never_restricts_the_bind_address():
    for env in ({}, {"NZSTATS_PUBLIC_RESEARCH": "0"}, {"NZSTATS_PUBLIC_RESEARCH": "true"}):
        assert bind_refusal("0.0.0.0", env) is None


def test_an_explicit_acknowledgement_allows_a_non_loopback_bind():
    assert bind_refusal("0.0.0.0", {**ON, ALLOW_NONLOOPBACK_ENV: "1"}) is None
    assert (
        bind_refusal("0.0.0.0", {**ON, ALLOW_NONLOOPBACK_ENV: "yes"}) is not None
    )  # only the exact value counts


@pytest.fixture()
def uvicorn_calls(monkeypatch, tmp_path):
    import uvicorn

    calls = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: calls.append(kw))
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv(ALLOW_NONLOOPBACK_ENV, raising=False)
    return calls


def test_serve_refuses_to_start_when_research_would_be_exposed(uvicorn_calls, monkeypatch, capsys):
    monkeypatch.setenv("NZSTATS_PUBLIC_RESEARCH", "1")
    assert main(["serve", "--no-scheduler", "--host", "0.0.0.0"]) == 2
    assert uvicorn_calls == [] and "without authentication" in capsys.readouterr().err


def test_serve_starts_on_loopback_or_with_research_off_or_acknowledged(uvicorn_calls, monkeypatch):
    monkeypatch.setenv("NZSTATS_PUBLIC_RESEARCH", "1")
    assert main(["serve", "--no-scheduler", "--host", "127.0.0.1"]) == 0
    monkeypatch.setenv(ALLOW_NONLOOPBACK_ENV, "1")
    assert main(["serve", "--no-scheduler", "--host", "0.0.0.0"]) == 0
    monkeypatch.delenv(ALLOW_NONLOOPBACK_ENV)
    monkeypatch.delenv("NZSTATS_PUBLIC_RESEARCH")
    assert main(["serve", "--no-scheduler", "--host", "0.0.0.0"]) == 0
    assert [c["host"] for c in uvicorn_calls] == ["127.0.0.1", "0.0.0.0", "0.0.0.0"]


# --- the private research preview (Phase 4I): loopback only, no override --------------------------------
@pytest.fixture()
def served(monkeypatch, tmp_path):
    import uvicorn

    apps = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: apps.append((app, kw)))
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv(ALLOW_NONLOOPBACK_ENV, raising=False)
    monkeypatch.delenv("NZSTATS_PUBLIC_RESEARCH", raising=False)
    return apps


def _paths(app) -> set[str]:
    return set(app.openapi()["paths"])


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.20", "nas.local"])
def test_the_private_preview_refuses_any_non_loopback_bind_even_when_acknowledged(
    served, monkeypatch, capsys, host
):
    monkeypatch.setenv(
        ALLOW_NONLOOPBACK_ENV, "1"
    )  # the public-research override does not apply here
    assert main(["serve", "--no-scheduler", "--private-research", "--host", host]) == 2
    assert served == [] and "private research preview" in capsys.readouterr().err


def test_the_private_preview_is_mounted_only_when_asked_for(served):
    assert main(["serve", "--no-scheduler", "--host", "127.0.0.1"]) == 0
    assert main(["serve", "--no-scheduler", "--private-research", "--host", "127.0.0.1"]) == 0
    (off, _), (on, _) = served
    assert "/api/private/research/items" not in _paths(off)
    assert "/api/private/research/items" in _paths(on)


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.20", "nas.local"])
def test_internal_drafts_refuse_any_non_loopback_bind_even_when_acknowledged(
    served, monkeypatch, capsys, host
):
    monkeypatch.setenv(
        ALLOW_NONLOOPBACK_ENV, "1"
    )  # the public-research override does not apply here
    assert main(["serve", "--no-scheduler", "--internal-drafts", "--host", host]) == 2
    assert served == [] and "internal drafts" in capsys.readouterr().err


def test_internal_drafts_are_mounted_and_advertised_only_when_asked_for(served):
    assert main(["serve", "--no-scheduler", "--host", "127.0.0.1"]) == 0
    assert main(["serve", "--no-scheduler", "--internal-drafts", "--host", "127.0.0.1"]) == 0
    (off, _), (on, _) = served
    assert "/api/internal/drafts" not in _paths(off) and "/api/internal/drafts" in _paths(on)
    assert off.state.capabilities.get("internal_drafts") is False
    assert on.state.capabilities.get("internal_drafts") is True
    assert "/api/private/research/items" not in _paths(on)  # it grants nothing else


# --- Phase 4AA: the owner's auto_display opt-in turns internal drafts on for a normal loopback start ------------
OPT_IN = {
    "auto_display": {
        "enabled": True,
        "enabled_by": "Test Owner",
        "enabled_on": "2026-11-08",
        "note": "synthetic",
    }
}


def _owner_file(tmp_path, content) -> None:
    data = tmp_path / "data"
    data.mkdir(parents=True, exist_ok=True)
    text = content if isinstance(content, str) else json.dumps(content)
    (data / "internal-drafts.json").write_text(text)


def _drafts_on(app) -> bool:
    on = app.state.capabilities.get("internal_drafts")
    assert on is ("/api/internal/drafts" in _paths(app))  # advertised exactly when mounted
    return on


def test_a_normal_loopback_start_shows_drafts_when_the_owner_opted_in(served, tmp_path):
    _owner_file(tmp_path, OPT_IN)
    assert main(["serve", "--no-scheduler", "--host", "127.0.0.1"]) == 0
    ((app, _),) = served
    assert _drafts_on(app) is True
    assert "/api/private/research/items" not in _paths(app)  # it grants nothing else


@pytest.mark.parametrize(
    "content",
    [
        None,  # no file: no opt-in
        {"drafts": []},  # the named list without auto_display
        {
            "auto_display": {**OPT_IN["auto_display"], "enabled": False}
        },  # only an explicit true counts
        "{not json",
    ],
)
def test_without_an_explicit_owner_opt_in_a_normal_start_shows_no_drafts(served, tmp_path, content):
    if content is not None:
        _owner_file(tmp_path, content)
    assert main(["serve", "--no-scheduler", "--host", "127.0.0.1"]) == 0
    ((app, _),) = served
    assert _drafts_on(app) is False


def test_the_owner_can_switch_drafts_off_for_one_start(served, tmp_path):
    _owner_file(tmp_path, OPT_IN)
    assert main(["serve", "--no-scheduler", "--no-internal-drafts", "--host", "127.0.0.1"]) == 0
    ((app, _),) = served
    assert _drafts_on(app) is False


def test_on_and_off_together_is_a_usage_error(served):
    with pytest.raises(SystemExit) as exc:
        main(["serve", "--internal-drafts", "--no-internal-drafts"])
    assert exc.value.code == 2 and served == []


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.20"])
def test_the_opt_in_never_turns_drafts_on_for_a_non_loopback_bind(served, tmp_path, host):
    """The container binds 0.0.0.0: it starts as before, with no drafts, rather than refusing."""
    _owner_file(tmp_path, OPT_IN)
    assert main(["serve", "--refresh", "scheduler", "--host", host]) == 0
    ((app, kw),) = served
    assert kw["host"] == host and _drafts_on(app) is False
