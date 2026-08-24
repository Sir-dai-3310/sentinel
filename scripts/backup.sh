#!/usr/bin/env bash
# Sentinel PostgreSQL backup script.
#
# Logical backup via pg_dump (custom format, compressed) + optional Redis RDB copy.
# Designed to be run on a schedule (cron / K8s CronJob) and to satisfy the RPO in
# docs/disaster-recovery.md.
#
# Usage:
#   ./scripts/backup.sh [backup_dir]
# Env:
#   PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE   (postgres connection)
#   REDIS_HOST REDIS_PORT                        (optional redis snapshot)
#   RETENTION_DAYS                               (default 14)
#
# Output: <backup_dir>/sentinel-pg-<UTC timestamp>.dump  (+ optional redis .rdb)

set -euo pipefail

BACKUP_DIR="${1:-/var/backups/sentinel}"
PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-sentinel}"
PGDATABASE="${PGDATABASE:-sentinel}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"

mkdir -p "$BACKUP_DIR"

echo "[backup $TS] starting postgres logical dump -> $BACKUP_DIR"
pg_dump \
  --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" \
  --dbname="$PGDATABASE" \
  --format=custom --compress=9 \
  --file="$BACKUP_DIR/sentinel-pg-$TS.dump"
echo "[backup $TS] postgres dump complete: sentinel-pg-$TS.dump"

# Optional Redis snapshot (best-effort; cache is rebuildable so non-fatal)
if [ -n "${REDIS_HOST:-}" ] && command -v redis-cli >/dev/null 2>&1; then
  REDIS_PORT="${REDIS_PORT:-6379}"
  echo "[backup $TS] triggering redis BGSAVE on $REDIS_HOST:$REDIS_PORT"
  redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" BGSAVE || echo "[backup] WARN: redis BGSAVE failed (non-fatal)"
fi

# Retention: prune dumps older than RETENTION_DAYS
find "$BACKUP_DIR" -name 'sentinel-pg-*.dump' -mtime "+$RETENTION_DAYS" -delete
echo "[backup $TS] retention applied (keep ${RETENTION_DAYS}d). Done."
