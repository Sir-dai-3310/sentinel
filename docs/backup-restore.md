# Backup & Restore

Sentinel persists its source of truth in **PostgreSQL** (analysis results,
audit logs, tenants, rules metadata, import tasks). Redis, when enabled, is a
rebuildable cache and is backed up only best-effort.

This document covers the logical backup/restore flow provided by
`scripts/backup.sh` and `scripts/restore.sh`.

## Backup strategy

| Item | Approach | RPO target |
|------|----------|-----------|
| PostgreSQL | `pg_dump` custom format, compressed, UTC-timestamped | 24 h (daily cron) |
| Redis (optional) | `BGSAVE` snapshot | best-effort, cache is rebuildable |
| Retention | local pruning of dumps older than `RETENTION_DAYS` (default 14) | — |

Logical (not physical/WAL) backups are used for portability and simplicity.
For tighter RPO, enable WAL archiving / point-in-time recovery — see
`docs/disaster-recovery.md`.

### Running a backup

```bash
# Defaults: localhost:5432, db/user "sentinel", output /var/backups/sentinel
./scripts/backup.sh [backup_dir]

# Override connection + retention via env
PGHOST=db.internal PGUSER=sentinel PGPASSWORD=*** \
PGDATABASE=sentinel RETENTION_DAYS=30 \
  ./scripts/backup.sh /mnt/backups
```

Output: `sentinel-pg-<UTC timestamp>.dump` in the backup directory.

### Scheduled backups (cron)

```cron
# /etc/cron.d/sentinel-backup — daily at 02:00 UTC
0 2 * * * sentinel PGHOST=localhost PGUSER=sentinel PGPASSWORD=*** \
  /opt/sentinel/scripts/backup.sh /var/backups/sentinel \
  >> /var/log/sentinel/backup.log 2>&1
```

On Kubernetes, use a CronJob mounting a PVC for `/var/backups/sentinel`.

## Restore

> **Destructive.** By default `restore.sh` runs `pg_restore --clean
> --if-exists`, which drops existing objects before recreating them. A
> confirmation guard is enforced.

```bash
# Interactive (prompts for "yes")
./scripts/restore.sh /var/backups/sentinel/sentinel-pg-20260818T020000Z.dump

# Non-interactive (automation)
RESTORE_CONFIRM=yes ./scripts/restore.sh /var/backups/sentinel/sentinel-pg-20260818T020000Z.dump

# Restore WITHOUT dropping existing objects (merge into current schema)
RESTORE_CLEAN=0 RESTORE_CONFIRM=yes ./scripts/restore.sh <file.dump>
```

After a restore, if the backup predates the current schema, re-apply
migrations:

```bash
cd sentinel-api && alembic upgrade head
```

## Verifying a backup

A backup is only useful if it restores. Periodically verify into a throwaway
database:

```bash
createdb sentinel_restore_check
PGDATABASE=sentinel_restore_check RESTORE_CONFIRM=yes \
  ./scripts/restore.sh /var/backups/sentinel/<latest>.dump
psql -d sentinel_restore_check -c 'select count(*) from analysis_results;'
dropdb sentinel_restore_check
```

## Reproducing locally with docker compose

The current dev environment has **no live PostgreSQL instance**, so the
backup/restore cycle is verified against a compose-launched database:

```bash
# 1. Start Postgres (service defined in docker-compose.yml)
docker compose up -d postgres

# 2. Apply schema
cd sentinel-api && DATABASE_URL=postgresql+asyncpg://sentinel:sentinel@localhost:5432/sentinel \
  alembic upgrade head && cd ..

# 3. Take a backup
PGHOST=localhost PGUSER=sentinel PGPASSWORD=sentinel PGDATABASE=sentinel \
  ./scripts/backup.sh /tmp/sentinel-backups

# 4. Restore into a fresh database to prove the dump is valid
docker compose exec postgres createdb -U sentinel sentinel_verify
PGDATABASE=sentinel_verify RESTORE_CONFIRM=yes \
  ./scripts/restore.sh /tmp/sentinel-backups/sentinel-pg-*.dump
```

> ⚠️ **Not verified in this environment** — no PostgreSQL server was running
> during authoring. The scripts pass `bash -n` syntax checks; execute the
> compose steps above to validate end-to-end.
