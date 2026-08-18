# Sentinel Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Web UI (React)                               │
│  Dashboard │ Analysis │ Rules │ Settings                           │
│  - Real-time stats  - Drag & drop  - CRUD  - Config viewer        │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ REST / WebSocket
┌──────────────────────────▼──────────────────────────────────────────┐
│                     API Gateway (FastAPI)                           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │ JWT Auth │ │  RBAC    │ │  Rate    │ │ Security │ │Prometheus│ │
│  │          │ │          │ │ Limiting │ │ Headers  │ │ Metrics  │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ │
│  Endpoints: /api/v1/analyze, /api/v1/rules, /api/v1/stats, /metrics │
└──────┬──────────────────┬──────────────────────┬────────────────────┘
       │                  │                      │
┌──────▼──────┐   ┌──────▼──────┐       ┌────────▼────────┐
│  Core       │   │  Agent      │       │  Intelligence   │
│  Engine     │   │  Service    │       │  Service        │
│  (Rust)     │   │  (Python)   │       │  (Python)       │
│             │   │             │       │                 │
│ - Sigma     │   │ - LangGraph │       │ - VirusTotal    │
│ - Parser    │   │ - LLM       │       │ - AbuseIPDB     │
│ - Metrics   │   │ - Output    │       │ - IOC Extractor │
└──────┬──────┘   └──────┬──────┘       └────────┬────────┘
       │                 │                        │
       └─────────────────┴────────────────────────┘
                         │
              ┌──────────▼──────────┐
              │  PostgreSQL + Redis │
              └─────────────────────┘
```

## Component Details

### Rust Core (`sentinel-core`)

High-performance Sigma rule engine with:
- **Sigma YAML parser**: Full syntax support (and/or/not/1 of */all of */parentheses)
- **Log parsers**: JSON, Sysmon XML
- **Pre-filtering indices**: product/service/category-based rule filtering
- **Fast paths**: EventID check, field presence check, pre-computed lowercase
- **Prometheus metrics**: evaluations, hits, latency, cache performance
- **Parallel evaluation**: Rayon-based multi-threading

### Python Agents (`sentinel-agents`)

LangGraph-based multi-agent system:
- **TriageAgent**: Rule engine first-pass, skips LLM on high-confidence hits
- **AnalystAgent**: LLM deep analysis with threat intelligence enrichment
- **HunterAgent**: Generates threat hunting hypotheses
- **ReporterAgent**: Creates structured incident reports
- **Output Plugins**: Slack, Webhook, Elasticsearch
- **Threat Intelligence**: VirusTotal, AbuseIPDB with IOC extraction

### FastAPI Backend (`sentinel-api`)

RESTful API with:
- **JWT Authentication**: Bearer token-based auth
- **RBAC**: admin/analyst/viewer role-based access control
- **Rate Limiting**: Token bucket algorithm (configurable)
- **Security Headers**: CSP, HSTS, X-Frame-Options, etc.
- **Prometheus Metrics**: Request latency, status codes, in-progress requests
- **Structured Logging**: JSON format with request ID correlation
- **WebSocket**: Real-time analysis streaming
- **Batch API**: Parallel log analysis

### React Frontend (`sentinel-web`)

Modern SPA with:
- **Dashboard**: Real-time statistics (auto-refresh every 5s)
- **Analysis**: Drag & drop log upload, real-time streaming results
- **Rules**: Full CRUD management
- **Settings**: Configuration viewer
- **E2E Tests**: Playwright with system Chrome

## Data Flow

```
1. User uploads log (Web UI)
   │
2. API Gateway authenticates + rate limits
   │
3. Rust Core evaluates Sigma rules
   ├─ Pre-filter by logsource (product/service)
   ├─ Fast path: EventID check
   ├─ Fast path: field presence check
   ├─ Parallel rule matching (Rayon)
   └─ Return rule hits
   │
4. Python Agents process
   ├─ TriageAgent: skip LLM if confidence ≥ 90
   ├─ AnalystAgent: LLM analysis + threat intel
   ├─ HunterAgent: generate hunting queries
   └─ ReporterAgent: create report
   │
5. Output Plugins notify
   ├─ Slack webhook
   ├─ Generic webhook
   └─ Elasticsearch
   │
6. WebSocket streams results to frontend
```

## Communication

| From | To | Protocol | Purpose |
|------|----|----------|---------|
| Web UI | API | REST/HTTPS | CRUD operations |
| Web UI | API | WebSocket | Real-time analysis |
| API | Rust Core | FFI (PyO3) | Rule evaluation |
| API | Agents | gRPC | Agent orchestration |
| Agents | VirusTotal | REST/HTTPS | IP/hash/domain lookup |
| Agents | AbuseIPDB | REST/HTTPS | IP reputation |
| API | PostgreSQL | TCP | Data persistence |
| API | Redis | TCP | Caching, task queue |
| Prometheus | All | HTTP | Metrics scraping |

## Security Architecture

- **Authentication**: JWT Bearer tokens (HS256)
- **Authorization**: RBAC (admin/analyst/viewer)
- **Rate Limiting**: Token bucket per IP
- **Security Headers**: CSP, HSTS, X-Frame-Options, X-Content-Type-Options
- **Input Validation**: Pydantic models on all endpoints
- **Audit Logging**: JSON-formatted security events
- **Non-root Containers**: All Docker images run as non-root user

## Deployment

### Docker Compose (Single Node)
```bash
docker-compose up
```

### Kubernetes (Distributed)
```bash
helm install sentinel ./helm/sentinel
```
