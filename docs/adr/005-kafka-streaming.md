# ADR-005: Kafka for Log Streaming Ingestion

## Status
Accepted

## Context
Sentinel must ingest high-volume log streams (10K+ EPS sustained) from diverse sources while preserving ordering per source and surviving downstream consumer failures. A synchronous HTTP-only ingestion path backpressures directly onto senders and drops data during deploys.

## Decision
Use Kafka as the streaming ingestion backbone between producers (agents, forwarders, the REST API) and the Rust analysis engine. The integration is verified against a real broker in CI (see `docker-compose.kafka.yml` and the streaming integration tests) — not mocks.

Poison-message protection:
1. **Schema validation at the edge**: Events that fail JSON/schema validation are rejected before publish.
2. **Deserialization guard**: Consumers wrap deserialization in a strict try/except; failures are routed to a dead-letter topic (`sentinel.dlq`) with the original payload and error metadata.
3. **Bounded retries**: Transient processing errors retry with exponential backoff (max 5 attempts); permanent failures go to the DLQ after the first attempt.
4. **DLQ monitoring**: DLQ depth is a first-class metric; a non-empty DLQ page is an operational alert, not silent data loss.

## Rationale
1. **Decoupling**: Producers never block on analysis throughput
2. **Replayability**: Offsets let us re-process windows after rule updates
3. **Ordering**: Per-partition ordering preserves event sequence per source
4. **Ecosystem**: Existing connectors (Filebeat, Fluentd, Logstash) work out of the box
5. **Verified**: Real-broker integration tests catch serialization and consumer-group regressions

## Consequences
- **Positive**: Durable buffering, horizontal consumer scaling, replay capability
- **Negative**: Additional infrastructure (Kafka + ZooKeeper/KRaft) for small deployments
- **Mitigation**: Docker Compose ships a single-broker profile for evaluation; direct HTTP ingestion remains available for lightweight setups

## Alternatives Considered
- **Redis Streams**: Lighter weight but weaker durability and replay semantics
- **NATS JetStream**: Operationally simpler, smaller ecosystem for log-shipping connectors
- **Direct HTTP only**: Simplest, but no buffering, no replay, and data loss during consumer restarts
