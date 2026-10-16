#!/usr/bin/env bash
# Start the dashboard locally (no Docker): bootstraps the venv and UI build on first run, then serves
# API + built UI on http://localhost:8000.
#
#   scripts/run.sh                  serve with the scheduler (polls stats.govt.nz, 10 s throttle)
#   scripts/run.sh --no-scheduler   serve only; makes no requests to stats.govt.nz
#   scripts/run.sh --rebuild        force reinstall of dependencies and a fresh UI build
#   scripts/run.sh --port 9000      any other flags are passed to `nzstats serve`
#
# First-time data: run `scripts/run.sh discover` then `scripts/run.sh backfill` (slow, throttled).
# Subcommands (migrate, discover, ingest, backfill, health, backup, ...) are passed to `nzstats`.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/backend/.venv"
cd "$ROOT"  # relative paths in .env (NZSTATS_DATA_DIR=./data) resolve against the repo
rebuild=0
args=()
for a in "$@"; do
  if [[ "$a" == "--rebuild" ]]; then rebuild=1; else args+=("$a"); fi
done

PY="${PYTHON:-python3}"
"$PY" -c 'import sys; sys.exit(sys.version_info < (3, 11))' \
  || { echo "Python 3.11+ required (set PYTHON=/path/to/python3.12)" >&2; exit 1; }

if [[ $rebuild -eq 1 || ! -x "$VENV/bin/nzstats" ]]; then
  echo "==> Installing backend into $VENV"
  [[ -d "$VENV" ]] || "$PY" -m venv "$VENV"
  "$VENV/bin/pip" install --quiet -e "$ROOT/backend"
fi

if [[ $rebuild -eq 1 || ! -f "$ROOT/frontend/dist/index.html" ]]; then
  command -v npm >/dev/null || { echo "npm is required to build the UI" >&2; exit 1; }
  echo "==> Building frontend"
  (cd frontend && { [[ -d node_modules && $rebuild -eq 0 ]] || npm ci; } && npm run build)
fi

export NZSTATS_STATIC_DIR="${NZSTATS_STATIC_DIR:-$ROOT/frontend/dist}"
export NZSTATS_DATA_DIR="${NZSTATS_DATA_DIR:-$ROOT/data}"
mkdir -p "$NZSTATS_DATA_DIR"
[[ -f "$ROOT/.env" ]] && { set -a; . "$ROOT/.env"; set +a; }

case "${args[0]:-}" in
  migrate|discover|ingest|backfill|health|backup|openapi)
    exec "$VENV/bin/nzstats" "${args[@]}" ;;
  *)
    # Loopback only: the container image binds 0.0.0.0, a dev machine should not.
    echo "==> serving on http://localhost:8000 unless --port is given (data: $NZSTATS_DATA_DIR)"
    exec "$VENV/bin/nzstats" serve --host 127.0.0.1 "${args[@]}" ;;
esac
