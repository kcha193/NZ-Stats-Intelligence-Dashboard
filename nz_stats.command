#!/usr/bin/env bash
# Double-click to start the NZ Stats dashboard and open it in the browser.
# Close this Terminal window (or press Ctrl+C) to stop it.
cd "$(dirname "$0")" || exit 1
PORT=8000

if curl -fs "http://localhost:$PORT/api/health" >/dev/null 2>&1; then
  echo "Already running on port $PORT; opening it."
  open "http://localhost:$PORT"
  exit 0
fi

# Open the browser once the server answers (first run installs and builds, so this can take a while).
(
  for _ in $(seq 1 300); do
    if curl -fs "http://localhost:$PORT/api/health" >/dev/null 2>&1; then
      open "http://localhost:$PORT"
      exit 0
    fi
    sleep 1
  done
) &

scripts/run.sh --port "$PORT"
status=$?
echo
echo "Dashboard stopped (exit $status). Press Return to close this window."
read -r _
