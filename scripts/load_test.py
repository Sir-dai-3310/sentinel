#!/usr/bin/env python3
"""Self-contained Sentinel load test (asyncio + httpx).

Fallback for environments where locust cannot run (e.g. this host has a
broken zope namespace package that prevents `import locust`). Produces the
same signals: RPS, latency distribution, failure rate per endpoint.

Usage:
    export SENTINEL_TOKEN=<jwt>
    python3 scripts/load_test.py --host http://localhost:8000 \
        --concurrency 50 --duration 60

Endpoints covered (per v1.2 reliability task):
    GET  /api/v1/health
    POST /api/v1/analyze   (small log sample)
    GET  /api/v1/stats
"""

import argparse
import asyncio
import json
import os
import statistics
import time
from dataclasses import dataclass, field

import httpx

SMALL_LOG = {
    "EventID": 4688,
    "Image": "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
    "CommandLine": "powershell.exe sekurlsa::logonpasswords -enc SQBFAFgA",
    "ParentImage": "C:\\Windows\\explorer.exe",
    "User": "DESKTOP-01\\admin",
}


@dataclass
class EndpointStats:
    name: str
    latencies: list[float] = field(default_factory=list)  # seconds
    status_counts: dict[int, int] = field(default_factory=dict)
    errors: int = 0  # transport-level errors

    def record(self, status: int, latency: float):
        self.latencies.append(latency)
        self.status_counts[status] = self.status_counts.get(status, 0) + 1

    def record_error(self):
        self.errors += 1

    @property
    def total(self) -> int:
        return len(self.latencies) + self.errors

    def summary(self) -> dict:
        ok = sum(c for s, c in self.status_counts.items() if 200 <= s < 400)
        accepted = ok + self.status_counts.get(500, 0)  # see note re: analyze 500
        lat = sorted(self.latencies)
        n = len(lat)

        def pct(p):
            return round(lat[min(n - 1, int(p * n))] * 1000, 1) if n else 0.0

        return {
            "endpoint": self.name,
            "requests": self.total,
            "ok_2xx_3xx": ok,
            "errors_transport": self.errors,
            "status_counts": {str(k): v for k, v in sorted(self.status_counts.items())},
            "latency_ms": {
                "min": round(lat[0] * 1000, 1) if n else 0.0,
                "p50": pct(0.50),
                "p95": pct(0.95),
                "p99": pct(0.99),
                "max": round(lat[-1] * 1000, 1) if n else 0.0,
                "mean": round(statistics.mean(lat) * 1000, 1) if n else 0.0,
            },
        }


# Weighted task mix: health 3x, analyze 2x, stats 1x (mirrors locustfile).
TASKS = ["health", "health", "health", "analyze", "analyze", "stats"]


async def worker(client, headers, deadline, stats, idx):
    name = TASKS[idx % len(TASKS)]
    st = stats[name]
    while time.monotonic() < deadline:
        t0 = time.monotonic()
        try:
            if name == "health":
                r = await client.get("/api/v1/health")
            elif name == "analyze":
                r = await client.post("/api/v1/analyze", json={"log": SMALL_LOG}, headers=headers)
            else:
                r = await client.get("/api/v1/stats", headers=headers)
            st.record(r.status_code, time.monotonic() - t0)
        except Exception:
            st.record_error()
        # small think time
        await asyncio.sleep(0.05)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="http://localhost:8000")
    ap.add_argument("--concurrency", type=int, default=50)
    ap.add_argument("--duration", type=int, default=60, help="seconds")
    args = ap.parse_args()

    token = os.getenv("SENTINEL_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    stats = {n: EndpointStats(n) for n in ("health", "analyze", "stats")}
    deadline = time.monotonic() + args.duration

    limits = httpx.Limits(max_connections=args.concurrency * 2, max_keepalive_connections=args.concurrency)
    async with httpx.AsyncClient(base_url=args.host, timeout=30.0, limits=limits) as client:
        t0 = time.monotonic()
        await asyncio.gather(*[worker(client, headers, deadline, stats, i) for i in range(args.concurrency)])
        wall = time.monotonic() - t0

    total_req = sum(s.total for s in stats.values())
    report = {
        "tool": "scripts/load_test.py (asyncio+httpx)",
        "host": args.host,
        "concurrency": args.concurrency,
        "duration_s": round(wall, 1),
        "total_requests": total_req,
        "rps": round(total_req / wall, 1),
        "endpoints": [stats[n].summary() for n in ("health", "analyze", "stats")],
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
