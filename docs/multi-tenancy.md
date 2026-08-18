# Multi-Tenancy Architecture

Sentinel supports two deployment modes for tenant isolation.

## Modes

| Mode | Enable | Behavior |
|------|--------|----------|
| Single-tenant (default) | — | All requests resolve to the `default` tenant. No `tenants` row required. Fully backward compatible. |
| Multi-tenant | `MULTI_TENANT_ENABLED=true` | The `tenant` claim in the JWT selects the tenant. Every tenant-scoped query is filtered by `tenant_id`. |

## Data isolation

- `analysis_results.tenant_id` and `audit_logs.tenant_id` (indexed, `server_default='default'`)
- Queries apply `tenant_filter(stmt, Model, tenant_id)` from `app/tenancy.py`
- Legacy rows (pre-migration) carry `tenant_id='default'` and are invisible to named tenants
- Isolation is verified by real database tests (`tests/test_tenancy.py`) — not mocks

## Tenant claims in JWT

```python
from app.auth.jwt import create_access_token

token = create_access_token("alice", tenant_id="acme-corp", roles=["analyst"])
```

`get_current_user` populates `User.tenant_id` and `User.roles` from the token.

## Tenant management API (admin only)

| Endpoint | Description |
|----------|-------------|
| `POST /api/v1/tenants` | Create tenant (slug, name, quotas). Slug must match `^[a-z0-9][a-z0-9-]{1,62}$`; `default` is reserved. |
| `GET /api/v1/tenants` | List all tenants |
| `DELETE /api/v1/tenants/{slug}` | Disable tenant (data retained, access revoked) |
| `GET /api/v1/tenants/current` | Show resolved tenant for the current request |

Admin endpoints require the `admin` role (`require_admin` dependency → 403 otherwise).

## Quotas

`tenants.max_requests_per_minute` and `tenants.max_analyses_per_day` (0 = unlimited) are stored per tenant for enforcement by the rate-limit middleware.

## Migration

```bash
alembic upgrade head    # 002_multitenancy: tenants table + tenant_id columns + indexes
alembic downgrade -1    # cleanly removes tenant columns and tenants table
```

Verified: upgrade → schema with 5 tenant indexes → downgrade → clean removal → re-upgrade.

## Security considerations

- Tenant is resolved **only** from the signed JWT claim — never from client-supplied headers or query params.
- Disabling a tenant does not delete data; rotate API keys/tokens for revoked tenants.
- Cross-tenant aggregation (global stats) must be an explicit admin operation, never the default.
