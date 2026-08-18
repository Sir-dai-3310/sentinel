# Sentinel CLI Reference

Command-line interface for the Sentinel API, built on the Python SDK.
Entry point: `python -m app.cli` (from `sentinel-api/`) — backwards compatible
with the v1.x invocation.

## Install

```bash
pip install -e sdk/          # CLI depends on the SDK
cd sentinel-api
python -m app.cli --help
```

## Configuration

```text
~/.sentinel/config.toml     # written 0600 — contains the token
```

```bash
python -m app.cli config set-url http://127.0.0.1:8000
python -m app.cli login --username admin --password admin     # saves JWT
python -m app.cli config show                                  # token masked
python -m app.cli config path
```

Resolution order:

| Setting | Priority (highest first) |
|---|---|
| API URL | `--api-url` → `SENTINEL_API_URL` env → config `api_url` → `http://localhost:8000` |
| Token | `--token` → `SENTINEL_TOKEN` env → config `token` |

Global flags: `--json` (raw JSON output), `--timeout <secs>`.

## Commands

### login

```bash
$ python -m app.cli login --username admin --password admin
✅ Logged in as admin — token saved to /root/.sentinel/config.toml
```

Omit `--password` to be prompted interactively (getpass, no echo).

### health

```bash
$ python -m app.cli health
Status: healthy
Version: 1.0.0
  api: up
  core_engine: up
  agents: up
```

### analyze

Single JSON log or JSONL batch:

```bash
$ python -m app.cli analyze examples/logs/mimikatz_detection.json
malicious:      True
danger_level:   96
reason:         [R011] Mimikatz credential dumping tool detected
mitre:          T1003
action:         Isolate affected host
rule_hits:      1
agent_trace:    TriageAgent
skipped_llm:    True

$ python -m app.cli --json analyze examples/logs/suspicious_powershell.json
{
  "verdict": {"malicious": false, "danger_level": 0, ...},
  "rule_hits": [{"rule_id": "R001", "confidence": 85, ...}],
  ...
}
```

`.jsonl`/`.ndjson` files go through the batch endpoint with per-row verdicts.

### rules

```bash
$ python -m app.cli rules list
Total rules: 100
  [medium  ] R103: WScript Execution
  [high    ] R001: PowerShell Encoded Command
  ...

$ python -m app.cli --json rules get R001        # full rule JSON
$ python -m app.cli rules create rule.json       # from a JSON file
✅ Rule created at execution/acme-ps-encode-001.yml
$ python -m app.cli rules update rule.json
$ python -m app.cli rules delete acme-ps-encode-001
✅ Rule acme-ps-encode-001 deleted
$ python -m app.cli rules reload
✅ 100 rules reloaded
```

### stats / llm-costs

```bash
$ python -m app.cli stats
total_events: 0
alerts:       0
critical:     0
accuracy:     0.0

$ python -m app.cli --json llm-costs
{"total_calls": 0, "total_tokens": 0, "estimated_cost_usd": 0.0, ...}
```

### import

```bash
$ python -m app.cli import batch.jsonl --wait
import task f91957811a11412582493139f129663a: pending
✅ completed: 3/3 processed, 0 failed
```

Flags: `--interval <secs>` (poll cadence, default 1.0),
`--poll-timeout <secs>` (abort with an error after N seconds, default 300).
Without `--wait` the task id is printed immediately; poll manually via the
SDK's `poll_import`.

### privacy (admin)

```bash
$ python -m app.cli privacy export alice
subject: alice
record_count: 2
[ ... full JSON of analysis_results ... ]

$ python -m app.cli privacy delete alice --yes
✅ erased 1 records for alice
```

`delete` prompts for confirmation unless `--yes` is passed.

## Errors

Errors are one line on stderr (never a stack trace); exit code 1 (2 for
usage/auth problems, 130 on Ctrl-C):

```text
$ python -m app.cli rules get no-such-id
Error: The requested resource was not found.

$ python -m app.cli --token bad stats
Error: Authentication required or credentials invalid.

$ python -m app.cli stats                       # no token configured
Error: not authenticated. Run `python -m app.cli login` or set a token via
--token / SENTINEL_TOKEN / `config set-token`.
```

Error messages are localized by the API's i18n middleware from the
`Accept-Language` header (`en` default, `zh` supported).
