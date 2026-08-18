# Issue & PR Label System

Labels organize incoming work. Maintainers apply them during triage; contributors can use them to find work.

## Type labels (what kind of change)

| Label | Color | Use for |
|-------|-------|---------|
| `type/bug` | `#d73a4a` | Something is broken |
| `type/feature` | `#a2eeef` | New capability |
| `type/enhancement` | `#84b6eb` | Improvement to existing behavior |
| `type/docs` | `#0075ca` | Documentation only |
| `type/perf` | `#fbca04` | Performance work |
| `type/security` | `#b60205` | Vulnerability or hardening |
| `type/chore` | `#fef2c0` | Tooling, deps, cleanup |

## Area labels (where in the codebase)

| Label | Covers |
|-------|--------|
| `area/core` | `sentinel-core/` — Rust Sigma engine |
| `area/agents` | `sentinel-agents/` — LangGraph agents, LLM, intelligence |
| `area/api` | `sentinel-api/` — FastAPI gateway, auth, tenancy |
| `area/web` | `sentinel-web/` — React frontend |
| `area/rules` | `rules/` — Sigma rule content |
| `area/infra` | Docker, Compose, K8s, Helm, CI |
| `area/docs` | Documentation, mkdocs site |

## Priority labels

| Label | Meaning |
|-------|---------|
| `priority/critical` | Data loss, security hole, or broken release — drop everything |
| `priority/high` | Scheduled for the current milestone |
| `priority/medium` | Default; ordered by maintainer judgment |
| `priority/low` | Nice to have; no milestone |

## Workflow labels

| Label | Meaning |
|-------|---------|
| `good-first-issue` | Scoped, documented, and mentor-available — start here |
| `help-wanted` | Maintainers won't get to this soon; PRs welcome |
| `needs-triage` | Not yet labeled/sized by a maintainer |
| `needs-repro` | Bug report without a reproducible case |
| `blocked` | Waiting on an external dependency or decision |
| `wontfix` | Explained and closed |

## Rules of thumb

- Exactly **one** `type/*` and at least one `area/*` per issue/PR.
- `priority/*` is set by maintainers only.
- `good-first-issue` must include reproduction/implementation hints in the body — a bare label is not enough.
