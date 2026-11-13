"""The Phase 4AF documents must describe what the code and the registry actually do."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from nzstats.cli import main
from nzstats.research.registry import load_registry

REPO = Path(__file__).resolve().parents[2]
DOCS = REPO / "docs"
NAMES = ("source-readiness", "pdf-tables", "verification", "runbook", "first-bank-pilot")
TEXT = {n: (DOCS / f"phase-4af-{n}.md").read_text(encoding="utf-8") for n in NAMES}
BANKS = {
    "ANZ New Zealand": "anz",
    "ASB": "asb",
    "BNZ": "bnz",
    "Westpac New Zealand": "westpac",
    "Kiwibank": "kiwibank",
}


def test_every_document_says_there_is_no_live_ingestion_and_no_permission_changed() -> None:
    for name, text in TEXT.items():
        assert re.search(r"no live ingestion", text, re.IGNORECASE), name
        assert re.search(r"no permission (?:field )?(?:was )?changed", text, re.IGNORECASE), name


@pytest.mark.parametrize(("name", "key"), BANKS.items())
def test_the_readiness_row_matches_the_registry(name: str, key: str) -> None:
    inst = load_registry()[key]
    row = next(
        line for line in TEXT["source-readiness"].splitlines() if line.startswith(f"| {name} ")
    )
    assert inst.review_status.value in row and inst.content_policy.value in row
    assert inst.verified_on is not None and inst.verified_on.isoformat() in row
    assert not inst.source_permitted and inst.llm_refusal(hosted=True) is not None


@pytest.mark.parametrize("name", BANKS)
def test_every_bank_has_a_checklist_with_the_owners_pending_decision(name: str) -> None:
    text = TEXT["source-readiness"]
    section = text[text.index(f"### {name}") :].split("\n### ", 1)[0]
    for needle in ("Terms to read", "Evidence to record", "Owner's pending decision"):
        assert needle in section, (name, needle)


def test_the_readiness_matrix_uses_the_registrys_evidence_and_reads_nothing_new() -> None:
    text = TEXT["source-readiness"].lower()
    assert "no new web read was made" in text and "not examined" in text


def test_the_pilot_names_its_exact_conditions() -> None:
    text = TEXT["first-bank-pilot"]
    assert "Exact conditions" in text and "dry-run" in text.lower()
    assert "no model" in text.lower()


def _commands(text: str) -> list[list[str]]:
    out = []
    for block in re.findall(r"```sh\n(.*?)```", text, flags=re.S):
        for line in block.splitlines():
            tokens = line.split("#")[0].split()
            if tokens[:1] == ["nzstats"]:
                out.append(tokens[1:])
    return out


def test_every_runbook_command_exists() -> None:
    commands = _commands(TEXT["runbook"])
    assert len(commands) >= 6
    for tokens in commands:
        head = tokens[:2] if tokens[0] == "research" else tokens[:1]
        if tokens[0] == "research" and tokens[1] == "tables":
            head = tokens[:3]
        with pytest.raises(SystemExit) as stop:
            main([*head, "--help"])
        assert stop.value.code == 0, tokens


def test_local_links_resolve() -> None:
    for name, text in TEXT.items():
        for target in re.findall(r"\]\(([^)#]+)(?:#[^)]*)?\)", text):
            if target.startswith(("http", "mailto")):
                continue
            assert (DOCS / target).resolve().exists(), (name, target)


def test_the_other_documents_point_at_phase_4af() -> None:
    assert "Phase 4AF" in (DOCS / "progress.md").read_text(encoding="utf-8")
    assert "Phase 4AF" in (DOCS / "data-sources" / "research.md").read_text(encoding="utf-8")
    claude = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
    assert "docs/phase-4af-pdf-tables.md" in claude and "research tables" in claude
    assert "phase-4af" in (DOCS / "phase-4ae-bank-research.md").read_text(encoding="utf-8")
