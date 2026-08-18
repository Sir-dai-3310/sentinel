# ADR-002: LangGraph for Multi-Agent Orchestration

## Status
Accepted

## Context
Sentinel uses multiple AI agents (Triage, Analyst, Hunter, Reporter) that need to share state and execute conditionally. Managing this manually leads to complex, error-prone code.

## Decision
Use LangGraph for agent orchestration instead of a hand-rolled state machine.

## Rationale
1. **Declarative**: Define agent graph, not imperative control flow
2. **State management**: Automatic state passing between agents
3. **Conditional routing**: Built-in support for conditional edges
4. **Ecosystem**: Compatible with LangChain tools and providers
5. **Community**: Large ecosystem, active development

## Consequences
- **Positive**: Clean agent definitions, easy to add new agents, built-in error handling
- **Negative**: Additional dependency, learning curve for LangGraph concepts
- **Mitigation**: Comprehensive documentation, examples, wrapper classes

## Alternatives Considered
- **Hand-rolled state machine**: Full control but error-prone and hard to maintain
- **Celery**: Task queue, not designed for agent workflows
- **Temporal**: Too heavy for single-node deployment
