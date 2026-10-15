#!/usr/bin/env bash
# Frontend verification: unit tests, typecheck, production build.
set -euo pipefail
cd "$(dirname "$0")/../frontend"
npm test
npm run typecheck
npm run build >/dev/null
