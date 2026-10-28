import json
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


def test_sources_shows_the_llm_processing_permission(env, capsys):
    assert main(["research", "sources"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert "llm" in lines[0]
    assert all("denied" in line for line in lines[1:] if line.strip())


# --- Phase 3B: summarise, inspect, approve, reject ----------------------------------------------
LLM_REGISTRY = REGISTRY.replace(
    "min_text_chars = 200\n",
    'min_text_chars = 200\nllm_processing = "local_only"\nllm_processing_note = "synthetic"\n',
)


@pytest.fixture()
def llm_env(tmp_path, monkeypatch):
    from nzstats.research.providers import FakeProvider
    from nzstats.store.db import connect, migrate

    from .llm_support import draft_json, seed_version

    path = tmp_path / "research.toml"
    path.write_text(textwrap.dedent(LLM_REGISTRY), encoding="utf-8")
    monkeypatch.setenv("NZSTATS_RESEARCH_SOURCES_FILE", str(path))
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("NZSTATS_LLM_API_KEY", raising=False)
    for name, value in (("NZSTATS_LLM_PROVIDER", "openai_compatible"), ("NZSTATS_LLM_MODEL", "local"),
                        ("NZSTATS_LLM_BASE_URL", "http://127.0.0.1:9/v1"),
                        ("NZSTATS_LLM_INPUT_USD_PER_MTOK", "4"),
                        ("NZSTATS_LLM_OUTPUT_USD_PER_MTOK", "20")):  # fmt: skip
        monkeypatch.setenv(name, value)
    conn = connect(tmp_path / "data" / "nzstats.db")
    migrate(conn)
    version = seed_version(conn)
    state = {"text": lambda req: draft_json(req.version_id)}
    fake = FakeProvider(lambda req: state["text"](req))
    monkeypatch.setattr("nzstats.research.cli.build_llm_provider", lambda settings: fake)
    return conn, version, fake, state


def test_summarise_without_a_configured_provider_refuses(tmp_path, monkeypatch, capsys):
    path = tmp_path / "research.toml"
    path.write_text(textwrap.dedent(LLM_REGISTRY), encoding="utf-8")
    monkeypatch.setenv("NZSTATS_RESEARCH_SOURCES_FILE", str(path))
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("NZSTATS_LLM_PROVIDER", raising=False)
    assert main(["research", "summarise"]) == 1
    assert "no LLM provider is configured" in capsys.readouterr().out


def test_a_bad_llm_configuration_is_a_clear_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("NZSTATS_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("NZSTATS_LLM_API_KEY", "sk-secret-value")
    assert main(["research", "summarise"]) == 2
    out = capsys.readouterr().out
    assert "NZSTATS_LLM_MODEL" in out and "sk-secret-value" not in out


def test_summarise_then_list_inspect_and_approve(llm_env, capsys):
    conn, version, fake, _ = llm_env
    assert main(["research", "summarise", "example"]) == 0
    out = capsys.readouterr().out
    assert f"version {version}" in out and "verified" in out and "spent" in out
    assert main(["research", "summaries"]) == 0
    listing = capsys.readouterr().out
    assert "verified" in listing and "unreviewed" in listing
    sid = conn.execute("SELECT id FROM research_summary").fetchone()[0]
    assert main(["research", "summary", str(sid)]) == 0
    shown = capsys.readouterr().out
    assert "not a check of economic accuracy" in shown
    assert "expected to grow 2.5% in the year to March 2027" in shown and "page 1" in shown
    assert "Not an official statistic" in shown
    assert main(["research", "approve", str(sid), "--reviewer", "Kevin"]) == 0
    assert main(["research", "summaries", "--review", "approved"]) == 0
    assert "approved" in capsys.readouterr().out


def test_dry_run_estimates_without_calling(llm_env, capsys):
    _, _, fake, _ = llm_env
    assert main(["research", "summarise", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "would_summarise" in out and "estimated" in out and fake.calls == []


def test_a_failed_summary_cannot_be_approved_and_rejection_needs_a_note(llm_env, capsys):
    conn, _, _, state = llm_env
    state["text"] = lambda req: "not json"
    assert main(["research", "summarise"]) == 0  # the run worked; the output was invalid
    sid = conn.execute("SELECT id FROM research_summary").fetchone()[0]
    assert main(["research", "approve", str(sid), "--reviewer", "Kevin"]) == 1
    assert "only verified" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main(["research", "reject", str(sid), "--reviewer", "Kevin"])
    assert (
        main(["research", "reject", str(sid), "--reviewer", "Kevin", "--note", "bad output"]) == 0
    )
    assert main(["research", "summary", "999"]) == 1


def test_model_text_is_printed_without_control_characters(llm_env, capsys):
    conn, version, _, state = llm_env
    from .llm_support import draft_json

    state["text"] = lambda req: draft_json(req.version_id, outlook={
        "text": "Growth \x1b[2J\x1b]0;pwned\x07 is expected to pick up.",
        "evidence": [{"version_id": req.version_id, "section_ordinal": 0, "page": 1,
                      "quote": "expected to grow 2.5% in the year to March 2027"}]})  # fmt: skip
    assert main(["research", "summarise"]) == 0
    sid = conn.execute("SELECT id FROM research_summary").fetchone()[0]
    capsys.readouterr()
    assert main(["research", "summary", str(sid)]) == 0
    out = capsys.readouterr().out
    assert "\x1b" not in out and "\x07" not in out and "\\x1b[2J" in out


def test_every_stored_field_from_the_model_is_escaped_including_units(llm_env, capsys):
    conn, _, _, state = llm_env
    from .llm_support import draft

    def output(req):
        data = draft(req.version_id)
        data["forecasts"][0]["unit"] = "\x1b[31mpct"
        return __import__("json").dumps(data)

    state["text"] = output
    assert main(["research", "summarise"]) == 0
    sid = conn.execute("SELECT id FROM research_summary").fetchone()[0]
    capsys.readouterr()
    assert main(["research", "summary", str(sid)]) == 0
    out = capsys.readouterr().out
    assert "\x1b" not in out and "\\x1b[31mpct" in out


# --- Phase 3C: publication decisions ----------------------------------------------------------
DISPLAY_REGISTRY = LLM_REGISTRY.replace(
    'llm_processing_note = "synthetic"\n',
    'llm_processing_note = "synthetic"\npublic_display = "summary"\npublic_display_approved_by = "T"\n'
    'public_display_approved_on = "2026-10-26"\npublic_display_note = "synthetic"\n',
)


def test_publish_needs_approval_then_shows_why_and_withdraw_works(llm_env, tmp_path, capsys):
    conn, *_ = llm_env
    (tmp_path / "research.toml").write_text(textwrap.dedent(DISPLAY_REGISTRY), encoding="utf-8")
    assert main(["research", "summarise", "example"]) == 0
    sid = conn.execute("SELECT id FROM research_summary").fetchone()[0]
    capsys.readouterr()
    assert main(["research", "publish", str(sid), "--approver", "Kevin", "--note", "terms ok"]) == 1
    assert "only an approved, verified summary" in capsys.readouterr().out
    with pytest.raises(SystemExit):  # a note is required
        main(["research", "publish", str(sid), "--approver", "Kevin"])
    assert main(["research", "approve", str(sid), "--reviewer", "Kevin"]) == 0
    assert main(["research", "publish", str(sid), "--approver", "Kevin", "--note", "terms ok"]) == 0
    assert main(["research", "summaries"]) == 0
    assert "publish" in capsys.readouterr().out
    assert main(["research", "summary", str(sid)]) == 0
    shown = capsys.readouterr().out
    assert "publication publish by Kevin" in shown and "public: yes (summary)" in shown
    assert main(["research", "withdraw", str(sid), "--approver", "Kevin", "--note", "query"]) == 0
    assert main(["research", "summary", str(sid)]) == 0
    assert "public: no (not publication-approved (withdrawn))" in capsys.readouterr().out


def test_sources_shows_the_public_display_permission(env, capsys):
    assert main(["research", "sources"]) == 0
    out = capsys.readouterr().out
    assert "display" in out.splitlines()[0] and "none" in out


def test_readiness_reports_each_gate_without_any_request(env, capsys, monkeypatch):
    web, built = env
    monkeypatch.delenv("NZSTATS_LLM_PROVIDER", raising=False)
    assert main(["research", "readiness", "example"]) == 0
    out = capsys.readouterr().out
    assert "1. Automated discovery and fetching: granted" in out
    assert "2. Extraction and local storage: granted" in out
    assert "3. LLM processing: not granted" in out and "llm_processing is denied" in out
    assert "4. Public display: not granted" in out
    assert "first blocker:" in out
    assert built == [] and web.requests == []


def test_readiness_of_the_shipped_registry_lists_every_source_as_not_ready(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.delenv("NZSTATS_RESEARCH_SOURCES_FILE", raising=False)
    monkeypatch.delenv("NZSTATS_LLM_PROVIDER", raising=False)
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(tmp_path / "data"))
    assert main(["research", "readiness"]) == 0
    out = capsys.readouterr().out
    assert "treasury" in out and "rbnz" in out
    assert "granted 0 of 4" in out


def test_readiness_of_an_unknown_institution_is_an_error(env, capsys):
    assert main(["research", "readiness", "nope"]) == 2


def test_quality_grades_stored_versions(env, capsys, tmp_path):
    from nzstats.store.db import connect, migrate

    from .llm_support import seed_version

    conn = connect(tmp_path / "data" / "nzstats.db")
    migrate(conn)
    version = seed_version(conn, (PARA * 3, "�" * 50 + PARA))
    conn.close()
    assert main(["research", "quality"]) == 0
    out = capsys.readouterr().out
    assert f"version {version}" in out and "poor" in out and "undecodable_characters" in out
    assert main(["research", "quality", "424242"]) == 1
    assert "no version 424242" in capsys.readouterr().out


def test_evaluate_scores_stored_summaries_without_calling_a_model(
    env, capsys, tmp_path, monkeypatch
):
    import json

    from nzstats.store.db import connect, migrate

    from .llm_support import seed_version
    from .public_support import store_summary

    monkeypatch.setattr("nzstats.research.cli.build_llm_provider", pytest.fail)
    conn = connect(tmp_path / "data" / "nzstats.db")
    migrate(conn)
    version = seed_version(conn)
    store_summary(conn, version, review=None, publish=False)
    conn.close()
    path = tmp_path / "ann.json"
    path.write_text(json.dumps({"annotator": "A", "annotated_on": "2026-10-28", "documents": [
        {"version_id": version, "indicators": ["gdp"], "forecasts": [
            {"indicator": "gdp", "horizon": "year to March 2027", "value": 2.5, "unit": "percent"}]}]}))  # fmt: skip
    assert main(["research", "evaluate", "--annotations", str(path)]) == 0
    out = capsys.readouterr().out
    assert "Real documents" in out and "fake/fake-1" in out
    path.write_text("{}")
    assert main(["research", "evaluate", "--annotations", str(path)]) == 2


MANUAL_REGISTRY = """
[institutions.manualonly]
name = "Manual Only"
kind = "government"
allowed_hosts = ["docs.example.org"]
categories = ["economic_outlook"]
review_status = "needs_review"
content_policy = "full_text"
terms_evidence = "direct"
licence = "Synthetic test licence"
min_text_chars = 200
manual_import = "approved"
manual_import_approved_by = "Test Owner"
manual_import_approved_on = "2026-10-28"
manual_import_note = "synthetic: copies obtained by a person may be stored"
"""


def _doc(tmp_path, name="outlook.html"):
    path = tmp_path / name
    path.write_text(f"<html><body><main><h1>Outlook</h1><p>{PARA * 6}</p></main></body></html>",
                    encoding="utf-8")  # fmt: skip
    return path


def test_import_stores_an_owner_supplied_copy_without_any_request(
    env, tmp_path, monkeypatch, capsys
):
    web, built = env
    registry = tmp_path / "research.toml"
    registry.write_text(registry.read_text() + textwrap.dedent(MANUAL_REGISTRY), encoding="utf-8")
    doc = _doc(tmp_path)
    args = ["research", "import", "manualonly", str(doc), "--url", "https://docs.example.org/outlook",
            "--importer", "Test Owner", "--note", "saved from a browser", "--published-on", "2026-10-01"]  # fmt: skip
    assert main(args) == 0
    out = capsys.readouterr().out
    assert "manualonly: new" in out and "version" in out
    assert str(tmp_path) not in out  # no local path is echoed back
    assert web.requests == [] and built == []
    assert main(args) == 0
    assert "manualonly: unchanged" in capsys.readouterr().out
    assert main(["research", "ingest", "manualonly"]) == 1  # the crawler stays refused
    assert "needs review" in capsys.readouterr().out


def test_import_is_refused_for_a_source_without_the_permission(env, tmp_path, capsys):
    doc = _doc(tmp_path)
    assert main(["research", "import", "locked", str(doc), "--url", "https://locked.example.org/x",
                 "--importer", "Owner", "--note", "n"]) == 1  # fmt: skip
    assert "refused (manual import not approved for this source)" in capsys.readouterr().out


def test_import_infers_the_format_from_the_file_suffix_and_refuses_others(env, tmp_path, capsys):
    registry = tmp_path / "research.toml"
    registry.write_text(registry.read_text() + textwrap.dedent(MANUAL_REGISTRY), encoding="utf-8")
    doc = _doc(tmp_path, "outlook.docx")
    assert main(["research", "import", "manualonly", str(doc), "--url", "https://docs.example.org/o",
                 "--importer", "Owner", "--note", "n"]) == 2  # fmt: skip
    assert "html or pdf" in capsys.readouterr().out


def test_health_reports_each_source_and_exits_1_when_attention_is_needed(env, capsys):
    assert main(["research", "health"]) == 1  # the approved example source has nothing stored yet
    out = capsys.readouterr().out
    assert "example" in out and "no_publications" in out and "locked" in out and "gated" in out
    assert main(["research", "health", "--json"]) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["needs_attention"] is True and {s["key"] for s in data["sources"]} == {
        "example",
        "locked",
    }


def test_health_exits_1_for_a_published_summary_of_an_institution_removed_from_the_registry(
    tmp_path, monkeypatch, capsys
):
    from nzstats.store.db import connect, migrate

    from .llm_support import seed_version
    from .public_support import store_summary

    path = tmp_path / "research.toml"
    locked_only = "[institutions.locked]" + REGISTRY.split("[institutions.locked]")[1]
    path.write_text(textwrap.dedent(locked_only), encoding="utf-8")
    monkeypatch.setenv("NZSTATS_RESEARCH_SOURCES_FILE", str(path))
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(tmp_path / "data"))
    conn = connect(tmp_path / "data" / "nzstats.db")
    migrate(conn)
    assert main(["research", "health"]) == 0  # only the gated `locked` source: nothing to report
    capsys.readouterr()
    sid = store_summary(
        conn, seed_version(conn)
    )  # `example` has stored, published research but no entry
    assert main(["research", "health", "--json"]) == 1
    data = json.loads(capsys.readouterr().out)
    removed = next(s for s in data["sources"] if s["key"] == "example")
    assert data["needs_attention"] is True and removed["routes"] == "unregistered"
    assert [f["code"] for f in removed["findings"]] == ["published_but_withheld"]
    assert main(["research", "health"]) == 1
    assert f"research withdraw {sid}" in capsys.readouterr().out
