# Redis Usage Evaluation

Status: **evaluation + one targeted change shipped** (rate-limiter backend).

This document audits where Redis *is* used today, evaluates three candidate
scenarios (rate limiting, WebSocket session state, distributed locking), and
records a recommendation and priority for each.

## Current usage

| Layer | Reality |
|-------|---------|
| Code (Python) | **No `import redis` anywhere.** All state is in-process memory. |
| Config | `REDIS_URL=redis://redis:6379` is injected into the API/worker services in `docker-compose.yml`, and a `redis:7-alpine` service is defined — but nothing consumes it. |
| Dependency | `redis-py` is **not** in the Python dependency set. |

So Redis is provisioned in the deployment topology but unused by the
application. Every stateful concern is currently single-process.

## Scenario 1 — Rate-limit counter  ✅ shipped

**Today:** `RateLimiter` (app/security.py) keeps a per-process sliding window
in a `defaultdict(list)`. With N API replicas each enforces its own limit, so
the effective global limit is `rate × N`, and limits reset on restart.

**Fit for Redis:** excellent. A fixed-window counter (`INCR` + `EXPIRE`) is the
canonical Redis rate-limit pattern, is shared across replicas, and survives
process restarts.

**Change made:** `RateLimiter` now prefers Redis when `REDIS_URL` is set **and**
`redis-py` is importable, and **falls back to in-memory** on any error
(missing lib, unreachable server, mid-request failure). No behaviour change
when Redis is absent — the default single-process path is untouched.

*Implementation note:* `redis-py` must be added to the API requirements to
activate the Redis path (`pip install redis`). Until then the limiter runs in
memory — exactly the safe fallback required.

## Scenario 2 — WebSocket session storage  ⏸ deferred (docs only)

**Today:** `ConnectionManager` holds `active_connections: list[WebSocket]` in
memory. WebSocket connections are inherently pinned to the process that
accepted them — a socket can't be "moved" to Redis.

**Fit for Redis:** partial. Redis can't hold the sockets, but it *can* hold
**presence/subscription metadata** (which tenant/user is connected, which
analysis IDs they follow) so that other replicas can `PUBLISH` events and each
node forwards to its own local sockets via Redis Pub/Sub. This is the standard
multi-node WebSocket fan-out design.

**Recommendation:** only worth doing when running >1 API replica *and* needing
cross-node push. That's a real architectural change (introduce a Redis
pub/sub bridge in `ConnectionManager`). **Priority: medium**, defer until
horizontal scaling of the realtime channel is required. Not changed here.

## Scenario 3 — Distributed locking  ⏸ deferred (docs only)

**Today:** no distributed locking exists; background jobs (retention sweep)
run inside the single API process.

**Fit for Redis:** when multiple replicas run the retention sweep (or any
leader-elected cron), a Redis lock (`SET key token NX PX <ttl>` + Lua release)
prevents duplicate concurrent sweeps. Single-node `SET NX PX` is adequate for
this low-stakes mutex; full Redlock is overkill.

**Recommendation:** adopt only alongside multi-replica deployment of the
sweep. **Priority: low**. Not changed here (single-process loop is correct
today; adding a lock now would be speculative).

## Conclusion & priorities

| Scenario | Verdict | Priority | Status |
|----------|---------|----------|--------|
| Rate-limit counter | Strong fit, low risk | **High** | ✅ Implemented (with memory fallback) |
| WebSocket presence/fan-out | Real change, needs scaling driver | Medium | 📄 Documented |
| Distributed lock (sweep leader) | Only with multi-replica jobs | Low | 📄 Documented |

**Operational note:** to turn on the Redis rate limiter, add `redis` to the API
requirements and ensure `REDIS_URL` is reachable. Without either, the system
behaves exactly as before (in-memory), so this is a zero-risk, opt-in upgrade.
