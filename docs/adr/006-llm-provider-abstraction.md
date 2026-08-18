# ADR-006: Pluggable LLM Provider Abstraction with Cost Tracking

## Status
Accepted

## Context
Sentinel's multi-agent AI pipeline (Triage, Analyst, Hunter, Reporter) needs LLM access, but users have hard constraints that differ per deployment: data-residency rules that forbid public APIs, budget ceilings, offline/air-gapped environments, and preference for specific vendors. Hard-coding a single provider would make the platform unusable for a large share of our audience.

## Decision
Define a provider abstraction (`sentinel_agents.llm.providers`) with first-class implementations for:

- **OpenAI** (GPT-4 family)
- **Anthropic** (Claude family)
- **Ollama** (local, air-gapped models)

Providers are selected via configuration (environment variable / settings file), not code changes. All providers share a common async interface so agents are provider-agnostic.

Cost tracking is built into the abstraction layer (`sentinel_agents.llm.cost_tracker`):
1. Every call records token usage (prompt/completion) per provider, per model, per agent.
2. Per-request cost is computed from a versioned price table and aggregated per incident and per day.
3. Cost metrics are exposed to the API so dashboards can show "what did this analysis cost" — critical for rule-first triage ROI.

## Rationale
1. **Deployment flexibility**: One codebase serves SaaS-like, enterprise, and air-gapped users
2. **Cost governance**: LLM spend is the dominant variable cost; it must be measurable per incident
3. **Testability**: Agents are tested against a fake provider; provider integrations are tested in isolation
4. **Future-proofing**: New providers (Azure OpenAI, Bedrock, self-hosted vLLM) plug in without agent changes

## Consequences
- **Positive**: Users pick cost/latency/privacy trade-offs per deployment; per-incident cost attribution; no vendor lock-in
- **Negative**: Abstraction constrains us to the common denominator (chat completions + tool use); provider-specific features need capability flags
- **Mitigation**: Capability negotiation lives in the provider interface; cost table is versioned alongside provider code

## Alternatives Considered
- **LangChain only**: Ties us to LangChain's abstraction churn; we keep LangGraph for orchestration but own the provider boundary
- **Single provider (OpenAI)**: Simplest, but excludes air-gapped and Anthropic-committed users
- **Per-agent hard-coded providers**: Maximum flexibility, but duplicated retry/cost logic and no unified cost ledger
