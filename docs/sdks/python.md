# Sentinel Python SDK Reference

Async Python client for the Sentinel API (`sentinel_sdk`). Runtime dependency: `httpx` only.

- Source: [`sdk/sentinel_sdk/`](https://github.com/sentinel-project/sentinel/tree/main/sdk)
- Tests: [`sdk/tests/`](https://github.com/sentinel-project/sentinel/tree/main/sdk/tests) (real ASGI transport against the actual app — no mocks)

## Installation

```bash
pip install -e sdk/
python -c "import sentinel_sdk; print(sentinel_sdk.__version__)"
```

Requires Python ≥ 3.11.

## Authentication

The API issues JWT bearer tokens via `POST /api/v1/auth/login`.

```python
from sentinel_sdk import SentinelClient

async with SentinelClient("http://localhost:8000") as client:
    token = await client.login("admin", "admin")   # stores client.token automatically
    print(token.access_token[:16], "...")
```

With an existing token:

```python
client = SentinelClient("http://localhost:8000", token="<jwt>")
# or later:
client.authenticate("<jwt>")
```

Default credentials for local dev are `admin` / `admin` (override via
`ADMIN_USERNAME` / `ADMIN_PASSWORD` or the `SENTINEL_USERS` JSON env var on the server).

## Client constructor

```python
SentinelClient(
    base_url="http://localhost:8000",   # origin only — no /api/v1 suffix
    token=None,                          # bearer token, optional if you call login()
    timeout=30.0,                        # per-request timeout, seconds
    retries=3,                           # total attempts for retriable failures
    retry_backoff=0.5,                   # initial exponential backoff, seconds
    transport=None,                      # httpx transport override (tests)
)
```

Always use `async with` (or call `await client.aclose()`) to release connections.

## Method reference

| Method | HTTP | Returns |
|---|---|---|
| `login(username, password)` | `POST /auth/login` | `Token` |
| `authenticate(token)` | — | `SentinelClient` (fluent) |
| `health()` | `GET /health` | `Health` |
| `analyze(log)` | `POST /analyze` | `AnalysisResult` |
| `analyze_batch(logs)` | `POST /analyze/batch` | `BatchAnalysisResult` |
| `list_rules()` | `GET /rules` | `RuleList` |
| `get_rule(rule_id)` | `GET /rules/{id}` | `Rule` |
| `create_rule(rule)` | `POST /rules` | `{"status","file_path"}` |
| `update_rule(rule_id, rule)` | `PUT /rules/{id}` | `{"status","file_path"}` |
| `delete_rule(rule_id)` | `DELETE /rules/{id}` | `{"status","rule_id"}` |
| `reload_rules()` | `POST /rules/reload` | `{"status","count"}` |
| `get_stats()` | `GET /stats` | `Stats` |
| `llm_costs()` | `GET /stats/llm-costs` | `dict` |
| `get_settings()` | `GET /settings` | `dict` |
| `import_logs(file)` | `POST /logs/import` | `ImportStatus` |
| `import_status(task_id)` | `GET /logs/import/{task_id}` | `ImportStatus` |
| `poll_import(task_id, wait, interval, timeout)` | polling | `ImportStatus` (terminal) |
| `export_privacy(subject)` | `GET /privacy/export` | `dict` (admin) |
| `delete_privacy(subject)` | `DELETE /privacy/data` | `dict` (admin) |

`import_logs` accepts a filesystem path or a binary file object. Files larger
than 50 MiB are rejected client-side with `ValueError`.

## Examples

### Analyze a log

```python
import asyncio, json
from sentinel_sdk import SentinelClient

async def main():
    async with SentinelClient("http://localhost:8000", token="<jwt>") as client:
        result = await client.analyze(json.load(open("examples/logs/mimikatz_detection.json")))
        v = result.verdict
        print(v["malicious"], v["danger_level"], v["reason"])
        print("rule hits:", len(result.rule_hits), "| trace:", result.agent_trace)

asyncio.run(main())
```

### Manage rules

```python
from sentinel_sdk import Rule

rules = await client.list_rules()
print(f"{rules.total} rules")
rule = await client.get_rule(rules.rules[0].id)

await client.create_rule(Rule(
    id="acme-ps-encode-001",
    title="PowerShell -enc via CLI",
    level="high",
    logsource={"product": "windows", "category": "process_creation"},
    detection={"selection": {"CommandLine|contains": " -enc "}, "condition": "selection"},
    tags=["attack.execution"],
))
await client.delete_rule("acme-ps-encode-001")
```

### Bulk import with polling

```python
task = await client.import_logs("batch.jsonl")
final = await client.poll_import(task.task_id, wait=True, interval=1.0, timeout=120)
print(final.status, final.processed, "/", final.total, "failed:", final.failed)
```

`poll_import(..., wait=False)` performs a single status fetch. Timeout raises
`TimeoutError` with current progress in the message.

## Error handling

| Condition | Exception | Notes |
|---|---|---|
| 401 | `AuthError` | re-run `login()` and retry |
| 403 | `ForbiddenError` | missing role (e.g. admin-only endpoint) |
| 404 | `NotFoundError` | |
| 409 | `ConflictError` | e.g. duplicate rule id |
| 400 / 422 | `RequestError` | malformed payload |
| 429 | `RateLimitError` | `.retry_after` seconds when the server provides it |
| 5xx | `ServerError` | retried automatically |
| connect/timeout | `NetworkError` | retried automatically |

Every exception carries `.status_code` (HTTP status when applicable) and
`.detail` (server-provided `detail`/`message`/`error` field).

```python
from sentinel_sdk import AuthError, RateLimitError

try:
    await client.analyze(log)
except AuthError:
    await client.login("admin", "admin")
except RateLimitError as e:
    await asyncio.sleep(e.retry_after or 60)
```

## Retry behavior

Only **5xx** and **network/timeout** failures are retried; 4xx fail fast.
Back-off schedule: `retry_backoff * 2**attempt` (0.5s, 1s, 2s, …).
Set `retries=1` to disable retrying entirely.

## Testing the SDK itself

```bash
cd sdk && python -m pytest tests/ -v
```

Tests boot the real FastAPI app on a temp SQLite database and drive the SDK
through `httpx.ASGITransport` — the exact request/response stack used over
the network.
