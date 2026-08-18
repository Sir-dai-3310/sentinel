# Plugin Development Guide

Sentinel supports a plugin architecture for extending functionality.

## Output Plugins

Output plugins send analysis results to external systems.

### Creating an Output Plugin

1. Create a new file in `sentinel-agents/sentinel_agents/output/`:

```python
from sentinel_agents.output import OutputPlugin
from sentinel_agents.state import IncidentState

class MyPlugin(OutputPlugin):
    @property
    def name(self) -> str:
        return "myplugin"

    async def send(self, state: IncidentState) -> bool:
        # Send state.verdict to your destination
        webhook_url = os.getenv("MYPLUGIN_URL")
        if not webhook_url:
            return False

        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    webhook_url,
                    json={"verdict": state.verdict.model_dump()},
                    timeout=10,
                )
                return response.status_code == 200
        except Exception:
            return False
```

2. Register in `sentinel-agents/sentinel_agents/output/__init__.py`:

```python
def _register_default_plugins(self):
    self.register(SlackPlugin())
    self.register(WebhookPlugin())
    self.register(ElasticsearchPlugin())
    self.register(MyPlugin())  # Add your plugin
```

3. Enable via environment variable:

```bash
export OUTPUT_MYPLUGIN_ENABLED=true
export MYPLUGIN_URL=https://your-webhook.com/endpoint
```

### Built-in Output Plugins

| Plugin | Environment Variables | Description |
|--------|-----------------------|-------------|
| Slack | `SLACK_WEBHOOK_URL`, `OUTPUT_SLACK_ENABLED` | Send alerts to Slack |
| Webhook | `WEBHOOK_URL`, `OUTPUT_WEBHOOK_ENABLED` | Send to any HTTP endpoint |
| Elasticsearch | `ELASTICSEARCH_URL`, `ELASTICSEARCH_INDEX`, `OUTPUT_ELASTICSEARCH_ENABLED` | Index alerts in ES |

## Threat Intelligence Plugins

Threat intelligence plugins enrich analysis with external data.

### Creating a Threat Intel Plugin

1. Create a new file in `sentinel-agents/sentinel_agents/intelligence/`:

```python
from sentinel_agents.intelligence import ThreatIntelProvider
from sentinel_agents.state import ThreatIntel

class MyIntelProvider(ThreatIntelProvider):
    async def lookup_ip(self, ip: str) -> ThreatIntel | None:
        # Query your threat intel source
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://api.myintel.com/ip/{ip}",
                    headers={"Authorization": f"Bearer {os.getenv('MYINTEL_API_KEY')}"},
                )
                data = response.json()
                return ThreatIntel(
                    source="MyIntel",
                    ioc_type="ip",
                    ioc_value=ip,
                    malicious=data.get("malicious", False),
                    confidence=data.get("confidence", 0),
                    details=data,
                )
        except Exception:
            return None

    async def lookup_hash(self, file_hash: str) -> ThreatIntel | None:
        return None  # Not supported

    async def lookup_domain(self, domain: str) -> ThreatIntel | None:
        return None  # Not supported
```

2. Register in the AnalystAgent:

```python
# In agents/__init__.py, _get_intel_aggregator method
providers.append(MyIntelProvider())
```

### Built-in Threat Intel Providers

| Provider | Environment Variables | IOC Types |
|----------|-----------------------|-----------|
| VirusTotal | `VT_API_KEY` | IP, hash, domain |
| AbuseIPDB | `ABUSEIPDB_API_KEY` | IP |

## Rule Loading

Rules can be loaded from multiple sources:

### Local Directory (Default)
```bash
export RULES_DIR=rules/
```

### Git Repository (Planned)
```bash
export RULES_GIT_URL=https://github.com/SigmaHQ/sigma.git
export RULES_GIT_BRANCH=master
```

### HTTP URL (Planned)
```bash
export RULES_HTTP_URL=https://example.com/rules.tar.gz
```

## Testing Plugins

```python
# tests/test_my_plugin.py
import pytest
from sentinel_agents.output.my_plugin import MyPlugin

@pytest.mark.asyncio
async def test_my_plugin():
    plugin = MyPlugin()
    assert plugin.name == "myplugin"

    # Test send
    result = await plugin.send(mock_state)
    assert result is True
```
