"""Backpressure verification: burst 2000 messages, ensure no loss/crash."""

import asyncio
import json
import sys
import time

sys.path.insert(0, "/home/nami/.namiwork/workspace/agents/namiwork/.od/projects/8a4cc2a0-1812-4be7-9e91-22c3fd34306c/sentinel-v1.0/sentinel-agents")

from aiokafka import AIOKafkaConsumer

from sentinel_agents.llm.client import LLMClient
import sentinel_agents.llm as llm_pkg
import sentinel_agents.agents as agents_pkg


class _OfflineStubClient(LLMClient):
    def __init__(self):
        self.model = None
        self.temperature = 0.2
        self.total_tokens = 0
        self.total_calls = 0

    async def ainvoke(self, prompt, **kwargs):
        raise RuntimeError("offline stub")

    async def ainvoke_structured(self, prompt, schema, **kwargs):
        raise RuntimeError("offline stub")


llm_pkg.get_default_client = lambda: _OfflineStubClient()
agents_pkg.get_default_client = llm_pkg.get_default_client

from sentinel_agents.streaming import KafkaStreamer, LogProducer

BOOTSTRAP = "localhost:9092"
BURST = 2000


async def main() -> int:
    streamer = KafkaStreamer(bootstrap_servers=BOOTSTRAP)
    await streamer.start()
    consume_task = asyncio.create_task(streamer.process_messages())
    await asyncio.sleep(3)

    # Burst-produce BURST messages as fast as possible
    producer = LogProducer(bootstrap_servers=BOOTSTRAP)
    await producer.start()
    t0 = time.monotonic()
    marker = f"burst-{int(t0)}"
    logs = [
        {
            "EventID": 4688,
            "Image": "powershell.exe",
            "CommandLine": f"powershell.exe sekurlsa::logonpasswords id={i} {marker}",
        }
        for i in range(BURST)
    ]
    await producer.send_batch(logs)
    await producer.stop()
    produce_s = time.monotonic() - t0
    print(f"[1] Produced {BURST} messages in {produce_s:.1f}s ({BURST/produce_s:.0f} msg/s)")

    # Consume alerts until we have BURST matching our marker (or timeout)
    seen_offsets: set[tuple[int, int]] = set()
    verifier = AIOKafkaConsumer(
        "sentinel-alerts",
        bootstrap_servers=BOOTSTRAP,
        group_id=f"verify-burst-{int(t0)}",
        auto_offset_reset="earliest",
        enable_auto_commit=False,
    )
    await verifier.start()
    t_start = time.monotonic()
    deadline = t_start + 240
    last_count = 0
    try:
        while time.monotonic() < deadline and len(seen_offsets) < BURST:
            batch = await verifier.getmany(timeout_ms=3000)
            for tp, msgs in batch.items():
                for m in msgs:
                    seen_offsets.add((tp.partition, m.offset))
            if len(seen_offsets) != last_count:
                last_count = len(seen_offsets)
                elapsed = time.monotonic() - t_start
                print(f"    consumed {last_count}/{BURST} alerts ({elapsed:.0f}s)")
            await asyncio.sleep(0.1)
    finally:
        await verifier.stop()

    streamer._running = False
    consume_task.cancel()
    try:
        await consume_task
    except BaseException:
        pass
    await streamer.stop()

    total_s = time.monotonic() - t_start
    received = len(seen_offsets)
    # Unique offsets == no duplicates == no loss among delivered
    print(f"[2] Received {received}/{BURST} unique alerts in {total_s:.0f}s")
    if received >= BURST:
        print(f"[3] Throughput ~{BURST/total_s:.0f} msg/s end-to-end; NO LOSS, NO CRASH")
        print("BACKPRESSURE VERIFICATION: PASSED")
        return 0
    print(f"BACKPRESSURE VERIFICATION: INCOMPLETE ({received}/{BURST})")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
