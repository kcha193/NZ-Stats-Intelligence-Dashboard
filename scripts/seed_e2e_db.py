"""Create a demo database from real fixture files. Usage: python scripts/seed_e2e_db.py DIR"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from tests.support import seed_from_fixtures

if __name__ == "__main__":
    seed_from_fixtures(Path(sys.argv[1]))
    print(f"seeded {sys.argv[1]}")
