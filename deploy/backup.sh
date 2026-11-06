#!/bin/sh
# Daily Postgres backup, keeps 14 days. Restore: gunzip -c FILE | psql "$DATABASE_URL"
set -eu
mkdir -p /backups
while true; do
  f="/backups/alaap-$(date +%Y%m%d-%H%M).sql.gz"
  pg_dump --no-owner --clean --if-exists | gzip > "$f" && echo "backup: $f"
  find /backups -name 'alaap-*.sql.gz' -mtime +14 -delete
  sleep 86400
done
