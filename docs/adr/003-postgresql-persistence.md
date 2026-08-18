# ADR-003: PostgreSQL for Data Persistence

## Status
Accepted

## Context
Sentinel needs to store analysis results, audit logs, rule metadata, and system statistics. The data is semi-structured (JSON logs) but requires relational queries.

## Decision
Use PostgreSQL as the primary database, with JSONB columns for semi-structured data.

## Rationale
1. **JSONB**: Native JSON support with indexing (best of both worlds)
2. **Reliability**: ACID compliance, battle-tested
3. **Indexing**: Rich indexing options (B-tree, GIN, GiST)
4. **Ecosystem**: Wide support, mature tooling (Alembic for migrations)
5. **Scalability**: Read replicas, partitioning, connection pooling

## Consequences
- **Positive**: Reliable, well-supported, JSONB for flexibility
- **Negative**: Additional infrastructure dependency
- **Mitigation**: Docker Compose includes PostgreSQL, K8s Helm Chart for production

## Alternatives Considered
- **MongoDB**: Native document store but weaker consistency guarantees
- **SQLite**: Too limited for concurrent access
- **Elasticsearch**: Great for search but not ideal as primary store
- **Redis**: In-memory only, not suitable for persistence
