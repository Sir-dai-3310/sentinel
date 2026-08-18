#!/usr/bin/env bash
# Sentinel PostgreSQL restore script.
#
# Restores a logical backup produced by scripts/backup.sh (pg_dump custom
# format). Restoring is DESTRUCTIVE: by default this script drops and recreates
# the target database objects, so it requires an explicit confirmation guard.
#
# Usage:
#   ./scripts/restore.sh <backup_file.dump>
# Env:
#   PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE   (postgres connection)
#   RESTORE_CONFIRM=yes                          (required, or answer the prompt)
#   RESTORE_CLEAN=1                              (drop objects before restore)
#
# Example:
#   RESTORE_CONFIRM=yes ./scripts/restore.sh /var/backups/sentinel/sentinel-pg-20260818T020000Z.dump

set -euo pipefail

BACKUP_FILE="${1:-}"
PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-sentinel}"
PGDATABASE="${PGDATABASE:-sentinel}"
RESTORE_CLEAN="${RESTORE_CLEAN:-1}"

if [ -z "$BACKUP_FILE" ]; then
  echo "ERROR: no backup file given." >&2
  echo "Usage: $0 <backup_file.dump>" >&2
  exit 1
fi

if [ ! -f "$BACKUP_FILE" ]; then
  echo "ERROR: backup file not found: $BACKUP_FILE" >&2
  exit 1
fi

echo "============================================================"
echo " Sentinel PostgreSQL RESTORE"
echo "------------------------------------------------------------"
echo "  target host : $PGHOST:$PGPORT"
echo "  database    : $PGDATABASE"
echo "  user        : $PGUSER"
echo "  backup file : $BACKUP_FILE"
echo "  clean first : $RESTORE_CLEAN"
echo "============================================================"
echo "WARNING: this will OVERWRITE data in '$PGDATABASE'."

# Confirmation guard: either RESTORE_CONFIRM=yes or an interactive "yes".
if [ "${RESTORE_CONFIRM:-}" != "yes" ]; then
  read -r -p "Type 'yes' to proceed with restore: " reply
  if [ "$reply" != "yes" ]; then
    echo "Restore aborted."
    exit 1
  fi
fi

TS="$(date -u +%Y%m%dT%H%M%SZ)"
echo "[restore $TS] starting restore -> $PGDATABASE"

CLEAN_ARGS=()
if [ "$RESTORE_CLEAN" = "1" ]; then
  CLEAN_ARGS+=(--clean --if-exists)
fi

pg_restore \
  --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" \
  --dbname="$PGDATABASE" \
  --verbose \
  "${CLEAN_ARGS[@]}" \
  "$BACKUP_FILE"

echo "[restore $TS] restore complete."
echo "NOTE: re-run 'alembic upgrade head' if the backup predates current schema."
