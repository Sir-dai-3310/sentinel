# Sentinel

Welcome to the Sentinel documentation site.

Sentinel is an open-source, AI-native Security Operations Center (SOC) platform that combines a blazing-fast Rust Sigma rule engine with a LangGraph multi-agent AI system.

Use the navigation on the left to explore:

- **Getting Started** — [Quickstart](quickstart.md), [Architecture](architecture.md), [Performance](performance.md)
- **Reference** — [REST API](api.md), [Python API Reference](api-reference.md)
- **Guides** — [Multi-Tenancy](multi-tenancy.md), [Plugins](plugins.md), [Security](security.md)
- **Community** — [Contributing](contributing.md), [Translations](translations.md), [Labels](labels.md)
- **Enterprise & Sustainability** — [Enterprise](enterprise.md), [License Rationale](license-rationale.md), [Whitepaper](whitepaper.md)
- **Architecture Decisions** — [ADR index](adr/001-rust-core.md)

## Key facts

| Metric | Value |
|--------|-------|
| Rust Sigma engine throughput | 10,276 EPS (single log) / 14,336 EPS (batch) |
| AI orchestration | LangGraph multi-agent (Triage / Analyst / Hunter / Reporter) |
| LLM providers | OpenAI, Anthropic, Ollama (pluggable, with cost tracking) |
| Streaming | Kafka (verified against a real broker) |
| AuthN/AuthZ | Multi-tenant JWT, RBAC, audit logging |
| Frontend i18n | 5 languages |
| Supply chain | SBOM + cosign-signed releases |
| License | MIT |

## Deploying this site (mike versioning)

This site is versioned with [mike](https://github.com/jimporter/mike) (see `extra.version.provider` in `mkdocs.yml`).

```bash
pip install mkdocs mkdocs-material "mkdocstrings[python]" mike

# Build locally
mkdocs build

# Serve locally
mkdocs serve

# Deploy a version to the gh-pages branch (maintainers only)
mike deploy --push --update-aliases 1.2 latest
mike set-default --push latest
```
