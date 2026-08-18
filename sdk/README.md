# Sentinel Python SDK

Async Python client for the [Sentinel](../README.md) security log analysis API.
Single runtime dependency: [`httpx`](https://www.python-httpx.org/).

## Installation

```bash
# from the repo root
pip install -e sdk/

# verify
python -c "import sentinel_sdk; print(sentinel_sdk.__version__)"
```

## Authentication

The API issues JWTs via `POST /api/v1/auth/login`. The client can log in for
you and stores the token for subsequent calls:

```python
from sentinel_sdk import SentinelClient

client = SentinelClient("http://localhost:8000")
await client.login("admin", "admin")     # stores the token internally
# or use an existing token:
client = SentinelClient("http://localhost:8000", token="<jwt>")
```

Token lookup order on the wire: whatever is set on `client.token` at request
time is sent as `Authorization: Bearer <token>`.

## Quick start

```python
import asyncio
from sentinel_sdk import SentinelClient

async def main():
    async with SentinelClient("http://localhost:8000") as client:
        await client.login("admin", "admin")
        health = await client.health()
        print(health.status, health.version)

asyncio.run(main())
```

## Example 1 — analyze a log

```python
result = await client.analyze({
    "EventID": 4688,
    "Image": "powershell.exe",
    "CommandLine": "powershell -enc SQBFAFgA...",
})
if result.verdict:
    print(result.verdict["malicious"], result.verdict["danger_level"])
print(f"rule hits: {len(result.rule_hits)}")
```

## Example 2 — rule management

```python
from sentinel_sdk import Rule

rules = await client.list_rules()
print(f"{rules.total} rules loaded")

rule = await client.get_rule(rules.rules[0].id)
print(rule.title, rule.level)

new_rule = Rule(
    id="my-custom-rule-001",
    title="Suspicious certutil usage",
    logsource={"product": "windows", "category": "process_creation"},
    detection={
        "selection": {"Image|endswith": "\\certutil.exe", "CommandLine|contains": "-urlcache"},
        "condition": "selection",
    },
    level="high",
    tags=["attack.command_and_control", "attack.t1105"],
)
created = await client.create_rule(new_rule)
print(created)  # {'status': 'created', 'file_path': 'command_and_control/my-custom-rule-001.yml'}

await client.delete_rule("my-custom-rule-001")
```

## Example 3 — bulk import with polling

```python
task = await client.import_logs("examples/logs/batch.jsonl")
print(f"import task {task.task_id}: {task.status}")

final = await client.poll_import(task.task_id, wait=True, interval=1.0, timeout=120)
print(f"{final.status}: {final.processed}/{final.total} processed, {final.failed} failed")
```

## Error handling

HTTP errors map to typed exceptions (see `sentinel_sdk.exceptions`):

| HTTP status | Exception            |
|-------------|----------------------|
| 401         | `AuthError`          |
| 403         | `ForbiddenError`     |
| 404         | `NotFoundError`      |
| 409         | `ConflictError`      |
| 400 / 422   | `RequestError`       |
| 429         | `RateLimitError`     |
| 5xx         | `ServerError` (retried) |
| connection/timeout | `NetworkError` (retried) |

```python
from sentinel_sdk import AuthError, NotFoundError, RateLimitError

try:
    await client.get_rule("no-such-rule")
except NotFoundError as e:
    print("missing:", e.detail)
except AuthError:
    await client.login("admin", "admin")  # token expired — re-login
except RateLimitError as e:
    await asyncio.sleep(e.retry_after or 60)
```

## Retry configuration

5xx responses and network errors are retried automatically with exponential
backoff (`backoff`, `backoff*2`, `backoff*4`, ...). Tune per client:

```python
SentinelClient(
    "http://localhost:8000",
    timeout=30.0,        # per-request timeout (seconds)
    retries=3,           # total attempts (1 = no retry)
    retry_backoff=0.5,   # initial backoff in seconds
)
```

4xx responses are never retried — they fail fast with the matching exception.

## Testing

The SDK test suite exercises the real HTTP layer against the actual FastAPI
app via `httpx.ASGITransport` (no mocks):

```bash
cd sdk && python -m pytest tests/ -v
```

Full documentation: [`docs/sdks/python.md`](../docs/sdks/python.md).
