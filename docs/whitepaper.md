# Sentinel — One-Page Product Brief

## What it is

**Sentinel is an open-source, AI-native Security Operations Center (SOC) platform.** It pairs a high-throughput Rust Sigma rule engine with a LangGraph multi-agent AI pipeline, so alerts are triaged at machine speed and ambiguous cases get deep LLM analysis — automatically.

## The problem

SOC teams drown in alerts (≈80% false positives). Traditional SIEMs are rule-only and manual; pure-LLM tools are slow, expensive, and hallucinate. Neither scales to modern log volumes.

## The approach: rules first, AI where it matters

```
Log stream → Rust Sigma engine (10,276 EPS) → high-confidence verdict
                                        └→ ambiguous → LangGraph agents
                                             (Triage → Analyst → Hunter → Reporter)
                                             → verdict + MITRE ATT&CK map + actions
```

## Verified key metrics

| Metric | Value |
|--------|-------|
| Sigma engine throughput | **10,276 EPS** single-log / **14,336 EPS** batch |
| Test coverage (Python) | 90% |
| Streaming | Kafka, verified against a real broker in CI |
| Supply chain | SBOM + cosign-signed releases |

## Architecture at a glance

- **sentinel-core** — Rust Sigma engine (Rayon parallelism, Aho-Corasick)
- **sentinel-agents** — LangGraph multi-agent system; pluggable LLMs (OpenAI / Anthropic / Ollama) with per-incident cost tracking
- **sentinel-api** — FastAPI gateway: multi-tenant JWT, RBAC, audit logging
- **sentinel-web** — React UI, real-time WebSocket streaming, 5-language i18n
- **Data plane** — PostgreSQL (JSONB), Kafka streaming ingestion, Redis

## Where it fits

| Scenario | Why Sentinel |
|----------|--------------|
| SOC analyst augmentation | Auto-triage cuts manual workload; analysts handle only ambiguous cases |
| Threat hunting | HunterAgent generates hypotheses and queries automatically |
| Incident response | Instant verdicts with ATT&CK mapping and recommended actions |
| Detection engineering | Evaluate millions of logs against 3,000+ Sigma rules in seconds |
| Air-gapped / regulated | Ollama local LLMs + single-binary Rust core + signed releases |

## Business model

Open core: everything above is **MIT-licensed, free forever**. A planned enterprise edition (SAML SSO, advanced reporting, audit-log export, SLA support — see [enterprise.md](enterprise.md)) funds development. Commercial support and custom development are available today via [SUPPORT.md](https://github.com/sentinel-project/sentinel/blob/main/SUPPORT.md).

## Get started

```bash
git clone https://github.com/sentinel-project/sentinel.git && cd sentinel
docker-compose up   # → http://localhost:3000
```

Full guide: [quickstart.md](quickstart.md) · Source: [github.com/sentinel-project/sentinel](https://github.com/sentinel-project/sentinel)
