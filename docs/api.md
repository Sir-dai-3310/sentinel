# Sentinel API Documentation

## Overview

The Sentinel API provides RESTful endpoints for security log analysis, rule management, and real-time statistics.

**Base URL**: `http://localhost:8000/api/v1`

**Authentication**: JWT Bearer token required for all endpoints except `/health`

---

## Authentication

### Get Access Token

```bash
# Create a token (in production, use a proper auth endpoint)
TOKEN=$(python3 -c "from app.auth.jwt import create_access_token; print(create_access_token('user123'))")
```

### Using the Token

```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/analyze
```

---

## Endpoints

### 1. Health Check

**GET** `/health`

Check API health status. No authentication required.

**Response**:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "services": {
    "api": "up",
    "core_engine": "up",
    "agents": "up"
  }
}
```

---

### 2. Analyze Log

**POST** `/analyze`

Analyze a single security log event.

**Headers**:
- `Authorization: Bearer <token>`
- `Content-Type: application/json`

**Request Body**:
```json
{
  "log": {
    "EventID": 1,
    "Image": "powershell.exe",
    "CommandLine": "powershell -enc JABjAD0AJw"
  }
}
```

**Response** (200 OK):
```json
{
  "verdict": {
    "malicious": true,
    "danger_level": 85,
    "reason": "PowerShell with encoded command detected",
    "mitre_techniques": ["T1059.001"],
    "recommended_actions": [
      "Isolate affected host",
      "Collect forensic evidence"
    ]
  },
  "rule_hits": [
    {
      "rule_id": "R001",
      "rule_name": "PowerShell Encoded Command",
      "technique": "T1059.001",
      "confidence": 85,
      "severity": "high",
      "reason": "PowerShell with encoded command"
    }
  ],
  "threat_intel": [],
  "agent_trace": ["TriageAgent", "AnalystAgent"],
  "metadata": {},
  "skipped_llm": false
}
```

**Error Responses**:
- `401 Unauthorized`: Missing or invalid JWT token
- `422 Unprocessable Entity`: Invalid request body
- `500 Internal Server Error`: Analysis failed

---

### 3. Batch Analyze

**POST** `/analyze/batch`

Analyze multiple logs in a single request.

**Request Body**:
```json
[
  {
    "log": {
      "EventID": 1,
      "Image": "powershell.exe",
      "CommandLine": "powershell -enc test"
    }
  },
  {
    "log": {
      "EventID": 10,
      "TargetImage": "lsass.exe",
      "GrantedAccess": "0x1410"
    }
  }
]
```

**Response** (200 OK):
```json
{
  "results": [
    {
      "verdict": { ... },
      "rule_hits": [ ... ],
      "success": true
    },
    {
      "verdict": { ... },
      "rule_hits": [ ... ],
      "success": true
    }
  ],
  "total": 2
}
```

---

### 4. List Rules

**GET** `/rules`

List all Sigma detection rules.

**Response** (200 OK):
```json
{
  "total": 12,
  "rules": [
    {
      "id": "R001",
      "title": "PowerShell Encoded Command",
      "level": "high",
      "file_path": "execution/powershell_encoded.yml"
    }
  ]
}
```

---

### 5. Get Rule

**GET** `/rules/{rule_id}`

Get details of a specific rule.

**Response** (200 OK):
```json
{
  "id": "R001",
  "title": "PowerShell Encoded Command",
  "description": "Detects PowerShell execution with encoded command",
  "level": "high",
  "logsource": {
    "product": "windows",
    "category": "process_creation"
  },
  "detection": {
    "selection": {
      "CommandLine|contains": ["-enc", "-encodedcommand"]
    },
    "condition": "selection"
  },
  "tags": ["attack.execution", "attack.t1059.001"]
}
```

**Error Responses**:
- `404 Not Found`: Rule not found

---

### 6. Create Rule

**POST** `/rules`

Create a new Sigma rule.

**Request Body**:
```json
{
  "id": "R100",
  "title": "Custom Detection Rule",
  "description": "My custom rule",
  "level": "medium",
  "logsource": {
    "product": "windows",
    "category": "process_creation"
  },
  "detection": {
    "selection": {
      "CommandLine|contains": "malicious_keyword"
    },
    "condition": "selection"
  },
  "tags": ["attack.custom"]
}
```

**Response** (201 Created):
```json
{
  "status": "created",
  "file_path": "custom/r100.yml"
}
```

**Error Responses**:
- `409 Conflict`: Rule ID already exists

---

### 7. Update Rule

**PUT** `/rules/{rule_id}`

Update an existing rule.

**Request Body**: Same as Create Rule

**Response** (200 OK):
```json
{
  "status": "updated",
  "file_path": "execution/r001.yml"
}
```

**Error Responses**:
- `404 Not Found`: Rule not found

---

### 8. Delete Rule

**DELETE** `/rules/{rule_id}`

Delete a rule.

**Response** (200 OK):
```json
{
  "status": "deleted",
  "rule_id": "R100"
}
```

**Error Responses**:
- `404 Not Found`: Rule not found

---

### 9. Reload Rules

**POST** `/rules/reload`

Trigger rule engine to reload all rules from disk.

**Response** (200 OK):
```json
{
  "status": "reloaded",
  "count": 12
}
```

---

### 10. Get Statistics

**GET** `/stats`

Get real-time statistics for dashboard.

**Response** (200 OK):
```json
{
  "total_events": 1234,
  "alerts": 45,
  "critical": 12,
  "accuracy": 0.95
}
```

---

## WebSocket API

### Real-Time Analysis

**WS** `/ws/analysis`

Connect to WebSocket for real-time log analysis with streaming progress updates.

**Connection**:
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/analysis')
```

**Send Log**:
```json
{
  "type": "log",
  "data": {
    "log": {
      "EventID": 1,
      "Image": "powershell.exe",
      "CommandLine": "powershell -enc test"
    }
  }
}
```

**Receive Messages**:

1. **Acknowledgment**:
```json
{
  "type": "ack",
  "data": {"status": "processing"}
}
```

2. **Progress Update**:
```json
{
  "type": "progress",
  "data": {"stage": "rule_engine", "status": "running"}
}
```

3. **Result**:
```json
{
  "type": "result",
  "data": {
    "verdict": { ... },
    "rule_hits": [ ... ],
    "agent_trace": [ ... ]
  }
}
```

4. **Error**:
```json
{
  "type": "error",
  "data": {"error": "Analysis failed: ..."}
}
```

**Heartbeat**:

Client should send `{"type": "ping"}` every 30 seconds. Server responds with `{"type": "pong"}`.

---

## Error Codes

| Code | Description |
|------|-------------|
| 200  | Success |
| 201  | Created |
| 400  | Bad Request - Invalid input |
| 401  | Unauthorized - Missing or invalid JWT token |
| 404  | Not Found - Resource not found |
| 409  | Conflict - Resource already exists |
| 422  | Unprocessable Entity - Validation error |
| 500  | Internal Server Error |

---

## Rate Limiting

Currently no rate limiting is implemented. In production, consider adding rate limiting middleware.

---

## Examples

### Python

```python
import requests

API_URL = "http://localhost:8000/api/v1"
TOKEN = "your_jwt_token"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

# Analyze log
response = requests.post(
    f"{API_URL}/analyze",
    json={
        "log": {
            "EventID": 1,
            "Image": "powershell.exe",
            "CommandLine": "powershell -enc test"
        }
    },
    headers=headers
)

result = response.json()
print(result["verdict"])
```

### JavaScript

```javascript
const API_URL = 'http://localhost:8000/api/v1'
const TOKEN = 'your_jwt_token'

// Analyze log
const response = await fetch(`${API_URL}/analyze`, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${TOKEN}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    log: {
      EventID: 1,
      Image: 'powershell.exe',
      CommandLine: 'powershell -enc test'
    }
  })
})

const result = await response.json()
console.log(result.verdict)
```

### cURL

```bash
# Set token
TOKEN="your_jwt_token"

# Analyze log
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "log": {
      "EventID": 1,
      "Image": "powershell.exe",
      "CommandLine": "powershell -enc test"
    }
  }'
```

---

## OpenAPI Specification

The API follows OpenAPI 3.0 specification. When running, visit:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

---

*Last updated: 2026-08-17*
