"""The browser/fixture seeder must produce displayable summaries under the current contract."""

import sqlite3
import subprocess
import sys
from pathlib import Path

from nzstats.research.public import public_summaries
from nzstats.research.registry import load_registry


def test_synthetic_demo_forecasts_name_their_authors_and_pass_the_display_gate(tmp_path):
    script = Path(__file__).resolve().parents[3] / "scripts" / "seed_research_demo.py"
    result = subprocess.run(
        [sys.executable, str(script), str(tmp_path)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    registry = load_registry(tmp_path / "research_sources.synthetic.toml")
    with sqlite3.connect(f"file:{tmp_path / 'nzstats.db'}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        items = public_summaries(conn, registry)
    assert {item.institution.key for item in items} == {
        "harbourside",
        "kauri",
        "southern",
        "tasman",
    }
    for item in items:
        assert item.summary.contract_version == 2
        assert item.summary.forecasts
        assert all(
            claim.issuer == item.institution.key.title() and claim.issuer_role == "author"
            for claim in item.summary.forecasts
        )
