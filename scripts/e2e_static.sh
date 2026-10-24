#!/usr/bin/env bash
# Browser tests against the static site: seed fixture data, export a fixture snapshot, build the live app (for visual
# parity) and the static site, then run Playwright with netlify.toml's rules applied. Needs the backend venv on PATH.
#
#   scripts/e2e_static.sh [playwright args...]     e.g.  --project=mobile -g "parity"
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA="${E2E_DATA_DIR:-/tmp/nzstats-e2e}"
SNAP="$ROOT/frontend/.e2e-snapshot"

python "$ROOT/scripts/seed_e2e_db.py" "$DATA"
rm -rf "$SNAP"
NZSTATS_DATA_DIR="$DATA" nzstats export-snapshot "$SNAP" --allow-fixtures
cd "$ROOT/frontend"
npm run build
"$ROOT/scripts/build_static_site.sh" --snapshot "$SNAP" --site-url https://nzstats.test --allow-fixture --skip-install
npx playwright test -c playwright.static.config.ts "$@"
