#!/usr/bin/env bash
# Entry point of the publisher container.
#   (no argument)  check for new data every PUBLISH_INTERVAL_MINUTES
#   once           one run, then exit (use it for a first check or from cron)
# Publishing stays off until PUBLISH_ENABLED=1, so starting the container can never change the public site by accident.
set -uo pipefail

: "${PUBLISH_SITE_URL:?set PUBLISH_SITE_URL in .env.publisher}"
interval="${PUBLISH_INTERVAL_MINUTES:-60}"
args=(--work-dir /work --site-url "$PUBLISH_SITE_URL" --min-interval-hours "${PUBLISH_MIN_INTERVAL_HOURS:-24}")
if [[ "${PUBLISH_ENABLED:-0}" != "1" ]]; then
  echo "publishing is disabled (PUBLISH_ENABLED is not 1): runs build and validate only"
  args+=(--dry-run)
elif [[ "${PUBLISH_DRAFT:-0}" == "1" ]]; then
  echo "draft mode: deploys go to a Netlify draft URL, not the public site"
  args+=(--draft)
fi

if [[ "${1:-}" == "once" ]]; then
  exec nzstats publish-site "${args[@]}"
fi
while true; do
  nzstats publish-site "${args[@]}" || echo "run failed (exit $?); the site keeps showing its last published data"
  sleep "$((interval * 60))"
done
