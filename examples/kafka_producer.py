#!/usr/bin/env python3
"""
Simulated log producer for Sentinel Kafka streaming demo.

Usage:
    python examples/kafka_producer.py --count 100 --interval 0.1
"""

import argparse
import asyncio
import json
import random
import sys
import time

sys.path.insert(0, "/home/nami/.namiwork/workspace/agents/namiwork/.od/projects/8a4cc2a0-1812-4be7-9e91-22c3fd34306c/sentinel-v1.0/sentinel-agents")

from sentinel_agents.streaming import LogProducer


SAMPLE_LOGS = [
    # Malicious
    {
        "EventID": 1,
        "Image": "powershell.exe",
        "CommandLine": "powershell -enc JABjAGwAaQBlAG4AdAA=",
        "ParentImage": "explorer.exe",
    },
    {
        "EventID": 10,
        "TargetImage": "lsass.exe",
        "GrantedAccess": "0x1410",
    },
    {
        "EventID": 1,
        "Image": "cmd.exe",
        "CommandLine": "mimikatz.exe sekurlsa::logonpasswords",
    },
    {
        "EventID": 13,
        "TargetObject": "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run\\Update",
        "Details": "C:\\Users\\Public\\update.exe",
    },
    {
        "EventID": 1,
        "Image": "cmd.exe",
        "CommandLine": "vssadmin delete shadows /all /quiet",
    },
    # Benign
    {
        "EventID": 1,
        "Image": "chrome.exe",
        "CommandLine": "chrome.exe --type=renderer",
        "ParentImage": "explorer.exe",
    },
    {
        "EventID": 1,
        "Image": "notepad.exe",
        "CommandLine": "notepad.exe readme.txt",
        "ParentImage": "explorer.exe",
    },
]


async def main():
    parser = argparse.ArgumentParser(description="Sentinel Kafka Log Producer")
    parser.add_argument("--count", type=int, default=100, help="Number of logs to produce")
    parser.add_argument("--interval", type=float, default=0.1, help="Interval between logs (seconds)")
    parser.add_argument("--servers", default="localhost:9094", help="Kafka bootstrap servers")
    parser.add_argument("--topic", default="sentinel-logs", help="Kafka input topic")
    args = parser.parse_args()

    producer = LogProducer(bootstrap_servers=args.servers, topic=args.topic)
    await producer.start()

    print(f"Producing {args.count} logs to {args.topic} on {args.servers}...")

    for i in range(args.count):
        log = random.choice(SAMPLE_LOGS).copy()
        log["TimeCreated"] = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
        log["Computer"] = f"WORKSTATION{random.randint(1, 10):02d}"
        log["ProcessId"] = random.randint(1000, 9999)
        log["_seq"] = i

        await producer.send_log(log)

        if (i + 1) % 10 == 0:
            print(f"  Produced {i + 1}/{args.count} logs")

        await asyncio.sleep(args.interval)

    await producer.stop()
    print(f"Done. Produced {args.count} logs.")


if __name__ == "__main__":
    asyncio.run(main())
