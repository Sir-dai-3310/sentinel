# Open Source vs Enterprise

Sentinel's core is MIT-licensed open source. An enterprise edition with additional capabilities is planned to fund long-term development. **Everything listed below as "Open Source" is what you have today** — no feature in the open-source edition will ever be removed or paywalled retroactively.

## Feature comparison

| Capability | Open Source | Enterprise (planned) |
|------------|:-----------:|:--------------------:|
| Rust Sigma engine (10,276 EPS single / 14,336 EPS batch) | ✅ | ✅ |
| LangGraph multi-agent analysis (Triage/Analyst/Hunter/Reporter) | ✅ | ✅ |
| Pluggable LLM providers (OpenAI/Anthropic/Ollama) + cost tracking | ✅ | ✅ |
| Kafka streaming ingestion | ✅ | ✅ |
| Multi-tenant JWT + RBAC + audit log | ✅ | ✅ |
| Web UI, 5-language i18n | ✅ | ✅ |
| SBOM + cosign-signed releases | ✅ | ✅ |
| Community support (Issues/Discussions) | ✅ | ✅ |
| Advanced scheduled & executive PDF reports | — | ✅ |
| SAML SSO / SCIM provisioning | — | ✅ |
| Audit log export (SIEM forwarding, WORM retention) | — | ✅ |
| Multi-cluster management console | — | ✅ |
| Guaranteed SLA support (24h critical response) | — | ✅ |
| Custom detection-content onboarding | — | ✅ |

## Current status

The enterprise edition does not exist yet — the table is a roadmap commitment, not a sales page. If your organization needs an enterprise capability today, see [SUPPORT.md](https://github.com/yourusername/sentinel/blob/main/SUPPORT.md) for commercial support and custom development options.

## Why this model

- **Open core, honestly**: the open-source edition is a complete, production-capable product. Enterprise features are additive (SSO, reporting, fleet management) — things large organizations need but hobbyists don't.
- **Sustainability**: enterprise revenue funds maintainers, CI infrastructure, and rule-content curation for everyone.
