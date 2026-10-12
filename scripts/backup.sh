#!/usr/bin/env sh
# Consistent online backup of the SQLite database into ./data/backups/. Raw artifacts are
# content-addressed and re-fetchable; copy ./data/raw too if you want a full archive.
set -eu
dest="data/backups/nzstats-$(date +%F-%H%M).db"
mkdir -p data/backups
docker compose exec -T nzstats nzstats backup "/data/backups/$(basename "$dest")"
echo "backup written to $dest"
