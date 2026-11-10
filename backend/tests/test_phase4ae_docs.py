"""The Phase 4AE documents must describe what the code and the registry actually do."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from nzstats.cli import main
from nzstats.research.registry import load_registry

REPO = Path(__file__).resolve().parents[2]
DOCS = REPO / "docs"
MATRIX = (DOCS / "phase-4ae-permissions-matrix.md").read_text(encoding="utf-8")
RUNBOOK = (DOCS / "phase-4ae-bank-runbook.md").read_text(encoding="utf-8")
OVERVIEW = (DOCS / "phase-4ae-bank-research.md").read_text(encoding="utf-8")
BANKS = {
    "ANZ New Zealand": "anz",
    "ASB": "asb",
    "BNZ": "bnz",
    "Westpac New Zealand": "westpac",
    "Kiwibank": "kiwibank",
}


def test_every_document_says_there_is_no_live_ingestion() -> None:
    for text in (MATRIX, RUNBOOK, OVERVIEW):
        assert re.search(r"no live ingestion", text, re.IGNORECASE)


@pytest.mark.parametrize(("name", "key"), BANKS.items())
def test_the_matrix_row_matches_the_registry(name: str, key: str) -> None:
    inst = load_registry()[key]
    row = next(line for line in MATRIX.splitlines() if line.startswith(f"| {name} "))
    assert inst.review_status.value in row and inst.content_policy.value in row
    assert inst.verified_on is not None and inst.verified_on.isoformat() in row
    assert not inst.source_permitted and inst.llm_refusal(hosted=True) is not None


def test_the_matrix_says_the_evidence_is_the_registrys_and_nothing_new_was_read() -> None:
    assert "no new web read was made" in MATRIX.lower()
    assert "not examined" in MATRIX.lower()


def _commands() -> list[list[str]]:
    out = []
    for block in re.findall(r"```sh\n(.*?)```", RUNBOOK, flags=re.S):
        for line in block.splitlines():
            tokens = line.split("#")[0].split()
            if tokens[:1] == ["nzstats"]:
                out.append(tokens[1:])
    return out


def test_every_runbook_command_exists() -> None:
    commands = _commands()
    assert len(commands) >= 12
    for tokens in commands:
        head = tokens[:2] if tokens[0] == "research" else tokens[:1]
        with pytest.raises(SystemExit) as stop:
            main([*head, "--help"])
        assert stop.value.code == 0, tokens


def test_the_other_documents_point_at_phase_4ae() -> None:
    assert "Phase 4AE" in (DOCS / "data-sources" / "research.md").read_text(encoding="utf-8")
    assert "Phase 4AE" in (DOCS / "progress.md").read_text(encoding="utf-8")
    claude = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
    assert "docs/phase-4ae-bank-research.md" in claude and "bank-status" in claude
