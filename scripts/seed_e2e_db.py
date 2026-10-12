"""Create a demo database from real fixture files. Usage: python scripts/seed_e2e_db.py DIR"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from tests.support import seed_from_fixtures

if __name__ == "__main__":
    target = Path(sys.argv[1])
    if (target / "nzstats.db").exists():
        print(f"{target} already seeded; delete it to re-seed")
    else:
        seed_from_fixtures(target)
        print(f"seeded {target}")
