#!/usr/bin/env bash
# Offline container smoke: persistent SQLite state and scheduler startup.
set -euo pipefail

image="${1:-nzstats:ci}"
container="nzstats-ci-${RANDOM}"
volume="${container}-data"

cleanup() {
  docker logs "$container" 2>/dev/null || true
  docker rm -f "$container" >/dev/null 2>&1 || true
  docker volume rm "$volume" >/dev/null 2>&1 || true
}
trap cleanup EXIT
docker volume create "$volume" >/dev/null

start_api() {
  # No network access: neither these checks nor scheduler jobs can reach Stats NZ.
  docker run -d --name "$container" --network none \
    --mount "type=volume,source=$volume,target=/data" "$image" \
    nzstats serve --no-scheduler --host 0.0.0.0 --port 8000 >/dev/null
}

wait_healthy() {
  for _ in $(seq 1 30); do
    if docker exec "$container" python -c \
      "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)"; then
      return 0
    fi
    sleep 1
  done
  return 1
}

check_persistence() {
  docker exec "$container" python -c \
    "import sqlite3; db = sqlite3.connect('/data/nzstats.db'); assert db.execute('SELECT value FROM ci_persistence').fetchone() == ('retained',)"
}

# Research (Phase 3A): the baked-in registry loads, and the PDF dependency is installed. Both make no request.
docker run --rm --network none "$image" nzstats research sources >/dev/null
docker run --rm --network none "$image" python -c "import pypdf"

start_api
wait_healthy
docker exec "$container" python -c \
  "import sqlite3; db = sqlite3.connect('/data/nzstats.db'); db.execute('CREATE TABLE ci_persistence(value TEXT)'); db.execute(\"INSERT INTO ci_persistence VALUES ('retained')\"); db.commit()"
docker restart "$container" >/dev/null
wait_healthy
check_persistence
docker rm -f "$container" >/dev/null
start_api
wait_healthy
check_persistence
docker rm -f "$container" >/dev/null

# Start the production command with scheduler enabled, on the same persistent volume.
docker run -d --name "$container" --network none \
  --mount "type=volume,source=$volume,target=/data" "$image" >/dev/null
wait_healthy
check_persistence
docker exec "$container" nzstats backup /data/backups/ci-online.db
docker exec "$container" python -c \
  "import sqlite3; db = sqlite3.connect('/data/backups/ci-online.db'); assert db.execute('PRAGMA integrity_check').fetchone() == ('ok',); assert db.execute('SELECT value FROM ci_persistence').fetchone() == ('retained',)"
docker logs "$container" 2>&1 | python -c '
import sys
logs = sys.stdin.read()
started = next((line for line in logs.splitlines() if "scheduler started with jobs" in line), "")
assert started, logs
for job in ("refresh_calendar", "release_watch", "catch_up", "startup_refresh", "startup_catch_up"):
    assert job in started, started
'
echo "Offline Docker health, SQLite persistence across restart/recreation, online backup, and scheduler startup passed."
