"""REAL Kafka end-to-end verification using Sentinel's own classes.

Flow: LogProducer -> [sentinel-logs] -> KafkaStreamer consumes -> analyze_log()
      -> [sentinel-alerts] -> verify alerts contain real analysis results.
Also verifies: malformed message -> routed to sentinel-alerts-errors.
"""

import asyncio
import json
import sys

sys.path.insert(0, "/home/nami/.namiwork/workspace/agents/namiwork/.od/projects/8a4cc2a0-1812-4be7-9e91-22c3fd34306c/sentinel-v1.0/sentinel-agents")

from aiokafka import AIOKafkaConsumer

from sentinel_agents.llm.client import LLMClient
import sentinel_agents.llm as llm_pkg
import sentinel_agents.agents as agents_pkg


class _OfflineStubClient(LLMClient):
    """Skip ChatOpenAI constructor; LLM calls always raise."""

    def __init__(self):
        self.model = None
        self.temperature = 0.2
        self.total_tokens = 0
        self.total_calls = 0

    async def ainvoke(self, prompt, **kwargs):
        raise RuntimeError("offline stub: no LLM credentials in verification env")

    async def ainvoke_structured(self, prompt, output_schema, **kwargs):
        raise RuntimeError("offline stub: no LLM credentials in verification env")


llm_pkg.get_default_client = lambda: _OfflineStubClient()
llm_pkg.client.get_default_client = llm_pkg.get_default_client
agents_pkg.get_default_client = llm_pkg.get_default_client

from sentinel_agents.streaming import KafkaStreamer, LogProducer

BOOTSTRAP = "localhost:9092"

# A log event shaped to hit the built-in Sigma-like rules (suspicious powershell)
MALICIOUS_LOG = {
    "EventID": 4688,
    "Image": "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
    "CommandLine": "powershell.exe sekurlsa::logonpasswords -enc SQBFAFgA",
    "ParentImage": "C:\\Windows\\explorer.exe",
    "User": "DESKTOP-01\\admin",
}

BENIGN_LOG = {
    "EventID": 4624,
    "Image": "C:\\Windows\\System32\\svchost.exe",
    "LogonType": 5,
    "User": "SYSTEM",
}


async def main() -> int:
    streamer = KafkaStreamer(bootstrap_servers=BOOTSTRAP)
    await streamer.start()
    print(f"[1] KafkaStreamer started (input={streamer.input_topic}, output={streamer.output_topic})")

    # Run the consumer loop in the background
    consume_task = asyncio.create_task(streamer.process_messages())

    # Give the consumer group time to join
    await asyncio.sleep(3)

    # Produce real log events using the project's own producer class
    producer = LogProducer(bootstrap_servers=BOOTSTRAP)
    await producer.start()
    await producer.send_log(MALICIOUS_LOG)
    await producer.send_log(BENIGN_LOG)
    await producer.send_log(MALICIOUS_LOG)  # second hit
    await producer.stop()
    print("[2] Produced 3 log events to sentinel-logs")

    # Also inject a malformed event directly (string instead of dict) to test error path
    from aiokafka import AIOKafkaProducer

    raw = AIOKafkaProducer(bootstrap_servers=BOOTSTRAP)
    await raw.start()
    await raw.send_and_wait("sentinel-logs", json.dumps("not-a-dict-log").encode())
    await raw.send_and_wait("sentinel-logs", b"{invalid json")  # broken JSON
    await raw.stop()
    print("[3] Injected 1 non-dict event + 1 broken-JSON event")

    # Read alerts and errors with a plain consumer
    alerts: list[dict] = []
    errors: list[dict] = []
    verifier = AIOKafkaConsumer(
        "sentinel-alerts",
        "sentinel-alerts-errors",
        bootstrap_servers=BOOTSTRAP,
        group_id="verify-e2e",
        auto_offset_reset="earliest",
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        enable_auto_commit=True,
    )
    await verifier.start()
    deadline = asyncio.get_event_loop().time() + 60
    try:
        while asyncio.get_event_loop().time() < deadline and (len(alerts) < 3 or len(errors) < 1):
            batch = await verifier.getmany(timeout_ms=2000)
            for _tp, msgs in batch.items():
                for m in msgs:
                    if m.topic == "sentinel-alerts":
                        alerts.append(m.value)
                    else:
                        errors.append(m.value)
            await asyncio.sleep(0.2)
    finally:
        await verifier.stop()

    # Stop the streamer loop
    streamer._running = False
    consume_task.cancel()
    try:
        await consume_task
    except (asyncio.CancelledError, Exception):
        pass
    await streamer.stop()
    print(f"[4] Consumed {len(alerts)} alerts, {len(errors)} error events")

    # --- Assertions ---
    failures = []

    if len(alerts) < 3:
        failures.append(f"expected >=3 alerts, got {len(alerts)}")

    # Check the malicious alert content
    malicious_alerts = [
        a for a in alerts
        if a.get("verdict") and (a["verdict"].get("malicious") or a.get("rule_hits"))
    ]
    if not malicious_alerts:
        failures.append("no malicious alert found among produced alerts")
    else:
        a = malicious_alerts[0]
        print(f"[5] Sample malicious alert verdict: malicious={a['verdict']['malicious']}, "
              f"danger={a['verdict']['danger_level']}, rule_hits={len(a['rule_hits'])}")
        assert a["kafka_metadata"]["topic"] == "sentinel-logs"
        assert "offset" in a["kafka_metadata"]

    # Kafka metadata present
    for a in alerts:
        if "kafka_metadata" not in a:
            failures.append("alert missing kafka_metadata")
            break

    # Error routing: broken JSON / non-dict should produce error records
    if len(errors) < 1:
        failures.append(f"expected >=1 error event on sentinel-alerts-errors, got {len(errors)}")
    else:
        print(f"[6] Error routing works: {errors[0].get('error', '')[:80]}")

    # Every benign log should not crash the pipeline
    benign_count = sum(1 for a in alerts if a.get("verdict") and not a["verdict"].get("malicious"))
    print(f"[7] benign verdicts: {benign_count}, malicious alerts: {len(malicious_alerts)}")

    if failures:
        print("FAILURES:", failures)
        return 1
    print("E2E KAFKA VERIFICATION: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
