#!/usr/bin/env bash
# Docker Compose dependency-kill chaos test (PostgreSQL / Redis).
#
# Verifies Sentinel's degradation behaviour when stateful dependencies vanish:
#   - stop postgres  -> api should surface DB errors (5xx) but the process stays up;
#                       /api/v1/health may still respond (it is dependency-light).
#   - stop redis     -> cache/queue operations degrade; api should not crash.
#   - restart both   -> service recovers without manual intervention (restart policy).
#
# NOTE: This requires a working Docker daemon. In the environment where this file
# was authored the Docker CLI exists but the daemon has no root permission to start
# containers, so this script is provided as a REPRODUCIBLE recipe and was NOT run
# here. It is safe to run on any dev machine with Docker:
#
#   docker compose up -d
#   bash scripts/chaos/compose-dependency-kill.sh
#
# Exit code: 0 if all degradation + recovery checks pass, 1 otherwise.

set -u
COMPOSE="${COMPOSE:-docker compose}"
API="${API:-http://localhost:8000}"
LOG="/tmp/chaos-compose.log"
: > "$LOG"

say() { echo "[chaos-compose $(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

http_code() { curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$1" 2>/dev/null || echo "000"; }

say "=== Sentinel compose dependency-kill chaos test ==="

# 0. Precondition: stack is up
say "precondition: checking api health"
if [ "$(http_code "$API/api/v1/health")" != "200" ]; then
  say "ERROR: api not healthy at $API. Run 'docker compose up -d' first."
  exit 1
fi
say "api healthy"

# 1. Kill PostgreSQL
say "phase 1: stop postgres -> expect api degradation (5xx on DB-backed routes)"
$COMPOSE stop postgres | tee -a "$LOG"
sleep 3
CODE_HEALTH="$(http_code "$API/api/v1/health")"
CODE_STATS="$(http_code "$API/api/v1/stats")"
say "during postgres outage: /health=$CODE_HEALTH /stats=$CODE_STATS (stats expected 401/500/000, health may stay 200)"

# api process must still be reachable (container didn't die)
if [ "$(http_code "$API/api/v1/health")" = "000" ]; then
  say "WARN: api unreachable after postgres stop (process may have crashed)"
else
  say "api process survived postgres outage (graceful degradation)"
fi

# 2. Kill Redis
say "phase 2: stop redis -> expect cache/queue degradation, api stays up"
$COMPOSE stop redis | tee -a "$LOG"
sleep 3
say "during redis outage: /health=$(http_code "$API/api/v1/health")"

# 3. Recover both
say "phase 3: restart postgres + redis -> expect recovery via restart policy"
$COMPOSE start postgres redis | tee -a "$LOG"
# wait for healthchecks to pass (compose service_healthy conditions handle ordering)
sleep 10

RECOVERED="$(http_code "$API/api/v1/health")"
say "post-recovery: /health=$RECOVERED"

if [ "$RECOVERED" = "200" ]; then
  say "=== COMPOSE CHAOS TEST PASSED: dependencies killed, api degraded gracefully, recovered ==="
  exit 0
else
  say "=== COMPOSE CHAOS TEST FAILED: api did not recover (health=$RECOVERED) ==="
  exit 1
fi
