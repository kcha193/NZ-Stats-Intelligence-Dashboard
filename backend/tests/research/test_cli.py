import textwrap

import pytest

from nzstats.cli import main

from .support import BASE, ROBOTS, Site, research_fetcher

PARA = "The example economy is assumed to grow slowly in this synthetic fixture text. "
REGISTRY = f"""
[institutions.example]
name = "Example Research"
kind = "bank"
allowed_hosts = ["research.example.org"]
landing_urls = ["{BASE}/research/"]
categories = ["economic_outlook"]
review_status = "approved"
content_policy = "full_text"
terms_evidence = "direct"
licence = "Synthetic test licence"
approved_by = "Test Reviewer"
approved_on = "2026-10-25"
approval_note = "synthetic test source"
min_text_chars = 200

[[institutions.example.discovery]]
mechanism = "html_links"
url = "{BASE}/research/"
link_pattern = "^https://research\\\\.example\\\\.org/research/.+"

[institutions.locked]
name = "Locked Bank"
kind = "bank"
allowed_hosts = ["locked.example.org"]
review_status = "restricted"
content_policy = "none"
"""


@pytest.fixture()
def env(tmp_path, monkeypatch):
    path = tmp_path / "research.toml"
    path.write_text(textwrap.dedent(REGISTRY), encoding="utf-8")
    monkeypatch.setenv("NZSTATS_RESEARCH_SOURCES_FILE", str(path))
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(tmp_path / "data"))
    web = Site(
        {
            ROBOTS: "",
            f"{BASE}/research/": f'<main><a href="{BASE}/research/a">A</a></main>',
            f"{BASE}/research/a": f"<main><h1>A</h1><p>{PARA * 6}</p></main>",
        }
    )
    built = []

    def factory(inst, settings):
        built.append(inst.key)
        return research_fetcher(inst, web)

    monkeypatch.setattr("nzstats.research.cli.build_fetcher", factory)
    return web, built


def test_sources_lists_every_institution_with_its_status(env, capsys):
    assert main(["research", "sources"]) == 0
    out = capsys.readouterr().out
    assert "example" in out and "approved" in out and "full_text" in out
    assert "locked" in out and "restricted" in out


def test_shipped_registry_lists_all_ten_without_network(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("NZSTATS_RESEARCH_SOURCES_FILE", raising=False)
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr("nzstats.research.cli.build_fetcher", pytest.fail)
    assert main(["research", "sources"]) == 0
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(lines) == 11  # header + ten institutions


def test_ingest_of_a_restricted_source_refuses_without_any_request(env, capsys):
    web, built = env
    assert main(["research", "ingest", "locked"]) == 1
    assert "restricted" in capsys.readouterr().out
    assert built == [] and web.requests == []


def test_unknown_institution_is_an_error(env, capsys):
    assert main(["research", "ingest", "nope"]) == 2
    assert "unknown institution" in capsys.readouterr().out


def test_ingest_an_approved_source_then_status(env, capsys):
    web, _ = env
    assert main(["research", "ingest", "example", "--limit", "1"]) == 0
    assert "new" in capsys.readouterr().out
    assert main(["research", "status"]) == 0
    out = capsys.readouterr().out
    assert "example" in out and "ok" in out


def test_discover_is_a_dry_run(env, capsys):
    web, _ = env
    assert main(["research", "discover", "example"]) == 0
    assert f"{BASE}/research/a" in capsys.readouterr().out
    assert f"{BASE}/research/a" not in web.requests


def test_failed_items_give_a_non_zero_exit(env, capsys):
    web, _ = env
    web.pages[f"{BASE}/research/a"] = "<main><p>tiny</p></main>"
    assert main(["research", "ingest", "example"]) == 1
    assert "failed" in capsys.readouterr().out


@pytest.mark.parametrize("value", ["0", "-1", "x"])
def test_limit_must_be_a_positive_integer(value, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["research", "ingest", "example", "--limit", value])
    assert exc.value.code == 2
