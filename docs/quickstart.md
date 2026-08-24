# Quickstart Guide

Get Sentinel up and running in 5 minutes.

## Prerequisites

- Docker & Docker Compose
- (Optional) Rust 1.70+, Python 3.11+, Node.js 20+ for local development

## Option 1: Docker (Recommended)

```bash
# 1. Clone repository
git clone https://github.com/sentinel-project/sentinel.git
cd sentinel

# 2. Configure environment
cp .env.example .env
# Edit .env with your API keys

# 3. Start all services
docker-compose up

# 4. Open browser
open http://localhost:3000
```

That's it! You should see the Sentinel dashboard.

## Option 2: Local Development

### 1. Install Rust Core

```bash
cd sentinel-core
cargo build --release
```

### 2. Install Python Agents

```bash
cd sentinel-agents
pip install -e .
```

### 3. Install API

```bash
cd sentinel-api
pip install -e .
```

### 4. Install Web UI

```bash
cd sentinel-web
npm install
```

### 5. Start Services

```bash
# Terminal 1: Core engine
cd sentinel-core && cargo run --release

# Terminal 2: Agents
cd sentinel-agents && python -m sentinel_agents.server

# Terminal 3: API
cd sentinel-api && uvicorn app.main:app --reload

# Terminal 4: Web UI
cd sentinel-web && npm run dev
```

## First Analysis

### Via Web UI

1. Go to http://localhost:3000/analysis
2. Upload a sample log (or drag & drop)
3. Watch real-time AI analysis
4. View verdict + MITRE ATT&CK mapping

### Via API

```bash
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "log": {
      "EventID": 1,
      "Image": "powershell.exe",
      "CommandLine": "powershell -enc JABjAD..."
    }
  }'
```

### Via Python SDK

```python
from sentinel_agents import analyze_log

result = await analyze_log({
    "EventID": 1,
    "Image": "powershell.exe",
    "CommandLine": "powershell -enc JABjAD..."
})

print(result.verdict)
```

## Next Steps

- [Add your own Sigma rules](../rules/)
- [Configure threat intelligence](.env)
- [Deploy to production](../k8s/)
- [Contribute](contributing.md)

## Troubleshooting

### "Connection refused" errors

Make sure all services are running:
```bash
docker-compose ps
```

### "LLM_API_KEY not set"

Edit `.env` and add your OpenAI/Anthropic/DeepSeek API key.

### "No rules loaded"

Make sure the `rules/` directory exists and contains `.yml` files.

## Getting Help

- [GitHub Issues](https://github.com/sentinel-project/sentinel/issues)
- [Discord](https://discord.gg/sentinel)
- [Documentation](https://docs.sentinel.dev)
