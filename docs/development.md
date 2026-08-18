# Development Guide

How to set up a local Sentinel dev environment, run every test layer, and
contribute. See also: [CLI reference](cli.md) ·
[Python SDK reference](sdks/python.md) · [API reference](api-reference.md).

## Repository layout

```text
sentinel-core/     Rust detection engine (Sigma matching, PyO3 bindings)
sentinel-agents/   Python LangGraph multi-agent layer (triage/analyst/hunter/reporter)
sentinel-api/      FastAPI backend + CLI (app/cli.py)
sdk/               Async Python SDK (sentinel_sdk) — the CLI is built on it
sentinel-web/      Next.js dashboard
rules/             Sigma rules (YAML) loaded by the engine and API
postman/           Postman collection + generator script
docs/              This documentation site (mkdocs)
```

## Prerequisites

- Python 3.11+ (3.12 used in dev)
- Rust stable toolchain (rustfmt + clippy)
- Node.js 20
- Optional: Docker (compose stacks), kubectl/helm (k8s manifests)

## Python: API + agents + SDK

```bash
# deps (system python is fine; no venv required)
pip install -r sentinel-api/requirements.txt   # fastapi, uvicorn, sqlalchemy, ...
pip install -e sentinel-agents/                # langgraph agents
pip install -e sdk/                            # sentinel_sdk (CLI dependency)

# run the API against a local SQLite database
cd sentinel-api
DATABASE_URL="sqlite+aiosqlite:////tmp/sentinel.db" \
PYTHONPATH=../sentinel-agents:. \
uvicorn app.main:app --reload --port 8000

# then, in another shell: the CLI
export PYTHONPATH=$PWD/../sdk:$PWD
python -m app.cli login --username admin --password admin
python -m app.cli analyze ../examples/logs/mimikatz_detection.json
```

Key environment variables (all optional for local dev):

| Var | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | postgres DSN | set `sqlite+aiosqlite:////tmp/sentinel.db` locally |
| `JWT_SECRET` | `CHANGE_THIS_IN_PRODUCTION` | JWT signing key |
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | — | LLM credentials; unset ⇒ rule-only path |
| `RULES_DIR` | `rules` | Sigma rules directory |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | `admin` / `admin` | bootstrap login account |
| `SENTINEL_USERS` | — | JSON map of users `{name: {password, roles, tenant}}` |
| `RATE_LIMIT` / `RATE_WINDOW` | `100` / `60` | per-IP rate limit |
| `MULTI_TENANT_ENABLED` | `false` | single-tenant mode when false |

### Test layers (Python)

```bash
# API tests (71 passing on v1.2 baseline)
DATABASE_URL="sqlite+aiosqlite:////tmp/t.db" \
PYTHONPATH=sentinel-agents:sentinel-api \
python -m pytest sentinel-api/tests/ -q

# SDK + CLI tests (32 passing) — real ASGI transport, no mocks
cd sdk && python -m pytest tests/ -q

# agent layer
PYTHONPATH=sentinel-agents python -m pytest sentinel-agents/tests/ -q
```

### Debugging tips

- `DB_ECHO=true` prints every SQL statement.
- `LOG_LEVEL=DEBUG` for verbose API logs; the audit logger writes JSON lines
  to `AUDIT_LOG_FILE` (default `/var/log/sentinel/audit.log`, falls back to stderr).
- `/metrics` exposes Prometheus counters; `/openapi.json` + `/docs` give the
  live schema — regenerate the Postman collection from it:
  `python3 postman/build_collection.py http://127.0.0.1:8000/openapi.json`.
- The analyze pipeline short-circuits when a rule hits with confidence ≥ 90
  (`skipped_llm: true`) — handy for testing without LLM credentials.
- Analysis persistence is best-effort: a missing/broken DB logs a warning
  (`⚠️ analysis persistence skipped`) but never fails the request.

## Rust: sentinel-core

```bash
cargo fmt --all && cargo clippy --all-targets --all-features
cargo test --all-features
cargo bench --no-run        # compile benchmarks
```

The Python bindings are built with maturin (`pip install maturin`,
`maturin develop` from `sentinel-core/`). Without the built extension the
agents fall back to a pure-Python rule matcher — fine for dev, slower.

## Web: sentinel-web

```bash
cd sentinel-web
npm ci
npm run lint && npm run type-check && npm test && npm run build
npm run dev                 # dev server on :3000
```

Playwright E2E: `npx playwright test` (artifacts land in `test-results/`).

## Writing a plugin

Plugins live in `plugins/` and hook the agent pipeline (enrichment, threat
intel, notification sinks). See [docs/plugins.md](plugins.md) for the
interface contract and lifecycle. Keep plugins self-contained: one
directory, its own `pyproject.toml`, and no imports from `sentinel-api`
internals — a plugin must work against the documented host API only.

## CI checks (must pass before merge)

From `.github/workflows/ci.yml`:

1. **Rust Core Tests** — `cargo fmt --check`, `cargo clippy -D warnings`,
   `cargo test --all-features`, `cargo bench --no-run`
2. **Python Agents Tests** — `ruff` lint, `mypy` type check, `pytest` (+coverage upload)
3. **API Tests** — `pytest sentinel-api/tests` (+coverage upload)
4. **Web UI Tests** — lint, type check, unit tests, production build
5. **Secret Scan** — gitleaks

Run the matching local command for whatever layer you touched.

## Commit & PR conventions

- Conventional Commits (enforced by `commitlint.config.js`):
  `feat(scope): summary`, `fix(...)`, `docs(...)`, `test(...)`, `chore(...)`.
- Never `git add -A`; add explicit paths so generated junk (test-results,
  sbom churn) doesn't slip in.
- Small PRs: one concern per PR; include the test command + output in the
  description.
- Docs live in `docs/` and build with mkdocs (`mkdocs build --strict`).
