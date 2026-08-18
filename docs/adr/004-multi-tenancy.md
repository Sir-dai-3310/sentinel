# ADR-004: JWT Claim-Driven Multi-Tenancy

## Status
Accepted

## Context
Sentinel is deployed both as a single-organization appliance and as a shared service for MSSPs and large enterprises with multiple business units. We needed tenant isolation without forcing single-tenant users through a complex onboarding flow.

## Decision
Implement a dual-mode tenancy model driven by JWT claims:

1. **Single-tenant (default)**: All requests resolve to the `default` tenant. No `tenants` row required. Fully backward compatible with pre-multi-tenancy deployments.
2. **Multi-tenant** (`MULTI_TENANT_ENABLED=true`): The `tenant` claim in the JWT selects the tenant. Every tenant-scoped query is filtered by `tenant_id` via the `tenant_filter()` helper in `app/tenancy.py`.

Data isolation is enforced at the database layer: `analysis_results.tenant_id` and `audit_logs.tenant_id` are indexed columns with `server_default='default'`. Legacy rows (pre-migration) carry `tenant_id='default'` and are invisible to named tenants.

## Rationale
1. **Backward compatibility**: Existing single-tenant deployments upgrade with zero configuration changes
2. **Claim-driven**: Tenant resolution happens at the auth layer; no per-request lookup overhead beyond JWT validation
3. **Defense in depth**: Isolation is verified by real database tests (`tests/test_tenancy.py`) — not mocks
4. **Simple mental model**: One `tenant_id` column per scoped table, one filter helper

## Consequences
- **Positive**: Zero-downtime migration path, predictable query plans (indexed `tenant_id`), auditable per-tenant audit logs
- **Negative**: Cross-tenant analytics require an explicit super-tenant path; every new scoped table must remember to add `tenant_id`
- **Mitigation**: `tenant_filter()` centralizes the filter; code review checklist requires tenancy tests for new scoped models

## Alternatives Considered
- **Schema-per-tenant**: Strong isolation but migration complexity grows linearly with tenant count
- **Database-per-tenant**: Maximum isolation but operational cost and connection management overhead are unacceptable at MSSP scale
- **Row-level security (RLS) only**: Elegant but ties us to PostgreSQL-specific policy management and complicates audit-log reasoning
