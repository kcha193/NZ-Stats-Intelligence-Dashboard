"""Create a demo database from real fixture files. Usage: python scripts/seed_e2e_db.py DIR"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from nzstats.config import load_settings
from nzstats.pipeline.ingest import ingest_release
from nzstats.runtime import build_runtime
from tests.cpi_support import NOW as CPI_NOW
from tests.cpi_support import seed_cpi
from tests.ect_support import NOW, seed_ect
from tests.support import FakeSite, seed_from_fixtures


def seed_ect_from_fixtures(target: Path) -> None:
    site = FakeSite()
    rt = build_runtime(
        load_settings({"NZSTATS_DATA_DIR": str(target)}), fetcher=site.fetcher()
    )
    for month in ("2026-08", "2026-09"):
        _, key, _ = seed_ect(rt, site, month)
        result = ingest_release(rt, key, now_fn=lambda: NOW)
        if result.outcome not in ("ingested", "unchanged"):
            raise RuntimeError(f"ECT fixture ingestion failed: {result.detail}")


def seed_cpi_from_fixtures(target: Path) -> None:
    site = FakeSite()
    rt = build_runtime(
        load_settings({"NZSTATS_DATA_DIR": str(target)}), fetcher=site.fetcher()
    )
    for month in ("2026-03", "2026-06"):
        _, key, _, _ = seed_cpi(rt, site, month)
        result = ingest_release(rt, key, now_fn=lambda: CPI_NOW)
        if result.outcome not in ("ingested", "unchanged"):
            raise RuntimeError(f"CPI fixture ingestion failed: {result.detail}")


if __name__ == "__main__":
    target = Path(sys.argv[1])
    if (target / "nzstats.db").exists():
        print(f"{target} already seeded; delete it to re-seed")
    else:
        seed_from_fixtures(target)
        print(f"seeded {target}")
    seed_ect_from_fixtures(target)
    seed_cpi_from_fixtures(target)
