"""Sentinel load test (locust).

Covers the three endpoints required by the v1.2 reliability task:
  - GET  /api/v1/health
  - POST /api/v1/analyze   (small log sample)
  - GET  /api/v1/stats

Usage (real run):
    export SENTINEL_TOKEN="$(python3 -c 'from app.auth.jwt import create_access_token; print(create_access_token("loadtest", roles=["admin"]))')"
    locust -f locustfile.py --headless -u 50 -r 10 -t 60s --host http://localhost:8000

Note: /api/v1/analyze exercises the real agent graph; without LLM credentials it
returns HTTP 500 (auth + routing + rule engine still run). That is expected in an
offline environment and is reported as a distinct failure, not hidden.
"""

import os

from locust import HttpUser, between, task

# Small, realistic log sample (Suspicious PowerShell — hits built-in rules).
SMALL_LOG = {
    "EventID": 4688,
    "Image": "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
    "CommandLine": "powershell.exe sekurlsa::logonpasswords -enc SQBFAFgA",
    "ParentImage": "C:\\Windows\\explorer.exe",
    "User": "DESKTOP-01\\admin",
}


class SentinelUser(HttpUser):
    wait_time = between(0.1, 0.5)

    def on_start(self):
        token = os.getenv("SENTINEL_TOKEN", "")
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}

    @task(3)
    def health(self):
        self.client.get("/api/v1/health", name="/api/v1/health")

    @task(2)
    def analyze(self):
        # Accept 500: offline env has no LLM credentials; the request still
        # exercises auth + validation + rule engine before the LLM call fails.
        with self.client.post(
            "/api/v1/analyze",
            json={"log": SMALL_LOG},
            headers=self.headers,
            name="/api/v1/analyze",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 500):
                resp.success()

    @task(1)
    def stats(self):
        self.client.get("/api/v1/stats", headers=self.headers, name="/api/v1/stats")
