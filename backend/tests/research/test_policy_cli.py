"""Phase 4W: the `nzstats research` policy commands. SYNTHETIC FIXTURE; the provider is a mock transport."""

import json
import os
import stat
from types import SimpleNamespace

import httpx
import pytest

from nzstats.cli import main
from nzstats.research import policy as pol
from nzstats.research import policy_cli

from .policy_support import policy_dict, registry, write_policy
from .test_policy_run import KEY, Env, good_output


@pytest.fixture()
def cli(tmp_path, monkeypatch):
    env = Env(tmp_path, content=json.dumps(good_output(1)))
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(env.data))
    monkeypatch.setattr("nzstats.research.cli.load_registry", lambda: env.reg)
    monkeypatch.setattr("nzstats.research.cli.build_llm_provider", pytest.fail)
    monkeypatch.setattr("nzstats.research.cli.build_fetcher", pytest.fail)
    monkeypatch.delenv("NZSTATS_LLM_API_KEY", raising=False)
    return env


def run(*argv):
    return main(["research", *argv])


def no_network(monkeypatch):
    def refuse(self, *a, **k):
        pytest.fail("a network request was attempted")

    monkeypatch.setattr(httpx.Client, "send", refuse)


def test_a_dry_run_prints_the_report_and_the_code_and_touches_nothing(cli, capsys, monkeypatch):
    no_network(monkeypatch)
    db_before = (cli.data / "nzstats.db").read_bytes()
    assert run("run-policy", str(cli.path), "--version", str(cli.version), "--dry-run") == 0
    out = capsys.readouterr().out
    assert "ELIGIBLE" in out and "Confirmation code:" in out and "Activity is expected" not in out
    assert (cli.data / "nzstats.db").read_bytes() == db_before  # read-only: not one byte changed


def test_a_refused_dry_run_exits_nonzero_and_lists_codes(cli, capsys, monkeypatch):
    no_network(monkeypatch)
    bad = write_policy(cli.data, policy_dict(cli.reg, series="FEU"), name="x.json")
    monkeypatch.setattr(
        "nzstats.research.cli.load_registry",
        lambda: registry(llm_processing="denied", manual_import="approved"),
    )
    assert run("run-policy", str(bad), "--version", str(cli.version), "--dry-run") == 2
    assert "llm_processing_denied" in capsys.readouterr().out


def test_execution_from_a_pipe_or_automation_is_refused_and_logged(cli, capsys, monkeypatch):
    no_network(monkeypatch)
    code = None
    assert (
        run("run-policy", str(cli.path), "--version", str(cli.version), "--confirm", "abcd1234")
        == 2
    )
    out = capsys.readouterr().out
    assert "not_interactive" in out and "Nothing was requested or reserved" in out
    import sqlite3

    rows = (
        sqlite3.connect(cli.data / "nzstats.db")
        .execute("SELECT event, refusal_code FROM research_policy_event")
        .fetchall()
    )
    assert rows == [("refused", "not_interactive")] and code is None


def test_a_wrong_confirmation_in_a_terminal_is_refused(cli, capsys, monkeypatch):
    no_network(monkeypatch)
    tty = SimpleNamespace(isatty=lambda: True)
    monkeypatch.setattr(policy_cli, "sys", SimpleNamespace(stdin=tty, stdout=tty))
    monkeypatch.setenv("NZSTATS_LLM_API_KEY", KEY)
    assert (
        run("run-policy", str(cli.path), "--version", str(cli.version), "--confirm", "00000000")
        == 2
    )
    assert "confirmation_mismatch" in capsys.readouterr().out


def test_a_full_confirmed_run_through_the_cli_makes_one_request(cli, capsys, monkeypatch):
    tty = SimpleNamespace(isatty=lambda: True)
    monkeypatch.setattr(policy_cli, "sys", SimpleNamespace(stdin=tty, stdout=tty))
    monkeypatch.setenv("NZSTATS_LLM_API_KEY", KEY)
    real = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(cli.respond), **kw)
    )
    assert run("run-policy", str(cli.path), "--version", str(cli.version), "--dry-run") == 0
    code = capsys.readouterr().out.split("Confirmation code:")[1].split()[0]
    monkeypatch.setattr(policy_cli, "_ask", lambda prompt: code)
    assert run("run-policy", str(cli.path), "--version", str(cli.version), "--confirm", code) == 0
    out = capsys.readouterr().out
    assert "One request made" in out and "unreviewed internal draft" in out and KEY not in out
    assert len(cli.posts) == 1
    assert (
        run("run-policy", str(cli.path), "--version", str(cli.version), "--dry-run") == 2
    )  # now ineligible
    assert "version_attempted" in capsys.readouterr().out


def test_policy_init_writes_a_private_policy_with_correct_pins_and_authorises_nothing(
    cli, capsys, tmp_path
):
    out = cli.data / "new-policy.json"
    assert (
        run(
            "policy-init",
            str(out),
            "--issued-by",
            "Synthetic Owner",
            "--policy-id",
            "treasury-feu-nov",
        )
        == 0
    )
    assert stat.S_IMODE(os.stat(out).st_mode) == 0o600
    policy, sha = pol.load_policy(
        out, cli.data
    )  # the pins match this code, this registry's licence is pinned too
    assert policy.max_calls == 4 and policy.aggregate_usd == 2.0 and policy.per_call_usd == 0.5
    assert "authorises nothing" in capsys.readouterr().out
    assert (
        run("policy-init", str(out), "--issued-by", "x", "--policy-id", "treasury-feu-nov") == 2
    )  # no overwrite
    assert (
        run(
            "policy-init",
            str(tmp_path / "outside.json"),
            "--issued-by",
            "x",
            "--policy-id",
            "treasury-feu-nov",
        )
        == 2
    )
    assert (
        run(
            "policy-init",
            str(cli.data / "big.json"),
            "--issued-by",
            "x",
            "--policy-id",
            "abc",
            "--aggregate-usd",
            "9",
        )
        == 2
    )


def test_policy_audit_lists_the_ledger_and_events_and_revoke_is_permanent(cli, capsys):
    assert run("policy-audit") == 0
    assert "Lifetime ledger: 0 of 8" in capsys.readouterr().out
    assert run("policy-revoke", str(cli.path), "--reason", "owner withdrew it") == 0
    assert run("policy-audit") == 0
    assert "revoked" in capsys.readouterr().out
    assert run("run-policy", str(cli.path), "--version", str(cli.version), "--dry-run") == 2
    assert "policy_revoked" in capsys.readouterr().out


def test_a_database_without_the_audit_table_is_refused_with_the_migrate_hint(cli, capsys):
    import sqlite3

    conn = sqlite3.connect(cli.data / "nzstats.db")
    conn.executescript(
        "DROP TRIGGER research_policy_event_no_delete; DROP TRIGGER research_policy_event_immutable;"
        "DROP INDEX research_policy_event_content_once; DROP INDEX research_policy_event_policy;"
        "DROP TABLE research_policy_event;"
    )
    conn.close()
    assert run("run-policy", str(cli.path), "--version", str(cli.version), "--dry-run") == 2
    assert "database_not_migrated" in capsys.readouterr().out
    assert run("policy-audit") == 0 and "run `nzstats migrate`" in capsys.readouterr().out
