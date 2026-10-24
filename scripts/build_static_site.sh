#!/usr/bin/env bash
# Build the public static site from a validated snapshot.
#
#   scripts/build_static_site.sh --snapshot DIR --site-url https://example.com [--allow-fixture]
#
# Output: frontend/dist-static (the directory Netlify publishes). Refuses a snapshot that is not production data
# unless --allow-fixture is given, which is for local and CI testing and produces a noindex, clearly labelled build.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SNAPSHOT="" SITE_URL_ARG="${SITE_URL:-}" ALLOW_FIXTURE=0 SKIP_INSTALL=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --snapshot) SNAPSHOT="$2"; shift 2 ;;
    --site-url) SITE_URL_ARG="$2"; shift 2 ;;
    --allow-fixture) ALLOW_FIXTURE=1; shift ;;
    --skip-install) SKIP_INSTALL=1; shift ;;
    *) echo "unknown argument: $1" >&2; exit 64 ;;
  esac
done

if [[ -z "$SNAPSHOT" ]]; then
  cat >&2 <<MSG
No snapshot given. The public site is built from a snapshot exported from the production database; the Git
checkout does not contain one on purpose. Export one first:

  NZSTATS_DATA_DIR=/path/to/data nzstats export-snapshot ./snapshot
  scripts/build_static_site.sh --snapshot ./snapshot --site-url https://your-site.example
MSG
  exit 64
fi
[[ -n "$SITE_URL_ARG" ]] || { echo "--site-url (or SITE_URL) is required: canonical URLs, the sitemap and share links need it" >&2; exit 64; }
SNAPSHOT="$(cd "$SNAPSHOT" && pwd)"

validate=(nzstats validate-snapshot "$SNAPSHOT")
[[ $ALLOW_FIXTURE -eq 1 ]] || validate+=(--for-publish)
"${validate[@]}"

cd "$ROOT/frontend"
[[ $SKIP_INSTALL -eq 1 ]] || npm ci --no-audit --no-fund
VITE_SITE_URL="$SITE_URL_ARG" npm run build:static
mkdir -p dist-static/data/v1
cp -R "$SNAPSHOT"/. dist-static/data/v1/
node scripts/prerender.mjs --snapshot "$SNAPSHOT" --dist dist-static --site-url "$SITE_URL_ARG"

check=(nzstats check-site dist-static --site-url "$SITE_URL_ARG" --netlify-toml "$ROOT/netlify.toml")
[[ $ALLOW_FIXTURE -eq 1 ]] || check+=(--for-publish)
"${check[@]}"
echo "static site ready: $ROOT/frontend/dist-static"
