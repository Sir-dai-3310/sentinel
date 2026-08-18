"""Kafka streaming integration for Sentinel."""

import asyncio
import json
import os
from typing import Any

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.errors import KafkaConnectionError

from sentinel_agents.graph import analyze_log


class KafkaStreamer:
    """
    Kafka-based log streaming and analysis.

    Consumes log events from a Kafka topic, analyzes them,
    and produces results to another topic.
    """

    def __init__(
        self,
        bootstrap_servers: str | None = None,
        input_topic: str | None = None,
        output_topic: str | None = None,
        group_id: str | None = None,
    ):
        self.bootstrap_servers = bootstrap_servers or os.getenv(
            "KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"
        )
        self.input_topic = input_topic or os.getenv("KAFKA_INPUT_TOPIC", "sentinel-logs")
        self.output_topic = output_topic or os.getenv("KAFKA_OUTPUT_TOPIC", "sentinel-alerts")
        self.group_id = group_id or os.getenv("KAFKA_GROUP_ID", "sentinel")

        self._consumer: AIOKafkaConsumer | None = None
        self._producer: AIOKafkaProducer | None = None
        self._running = False

    async def start(self) -> None:
        """Start the Kafka consumer and producer."""
        self._consumer = AIOKafkaConsumer(
            self.input_topic,
            bootstrap_servers=self.bootstrap_servers,
            group_id=self.group_id,
            # Raw bytes: deserialization happens inside the message loop so a
            # malformed payload becomes an error record instead of a poison
            # pill that kills the consumer and blocks offset commits.
            auto_offset_reset="latest",
            enable_auto_commit=True,
            max_poll_records=100,
        )

        self._producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            acks="all",
        )

        await self._consumer.start()
        await self._producer.start()
        self._running = True

    async def stop(self) -> None:
        """Stop the Kafka consumer and producer."""
        self._running = False
        if self._consumer:
            await self._consumer.stop()
        if self._producer:
            await self._producer.stop()

    async def process_messages(self) -> None:
        """Process messages from the input topic."""
        if not self._consumer or not self._producer:
            raise RuntimeError("Kafka streamer not started")

        try:
            async for message in self._consumer:
                if not self._running:
                    break

                try:
                    log_event = json.loads(message.value.decode("utf-8"))
                    if not isinstance(log_event, dict):
                        raise ValueError(
                            f"expected dict log event, got {type(log_event).__name__}"
                        )

                    result = await analyze_log(log_event)

                    # langgraph returns a plain dict; support both shapes
                    verdict = result.get("verdict") if isinstance(result, dict) else result.verdict
                    rule_hits = result.get("rule_hits") if isinstance(result, dict) else result.rule_hits
                    agent_trace = (
                        result.get("agent_trace") if isinstance(result, dict) else result.agent_trace
                    )
                    skipped_llm = (
                        result.get("skipped_llm") if isinstance(result, dict) else result.skipped_llm
                    )

                    # Produce result to output topic
                    alert = {
                        "verdict": verdict.model_dump() if verdict else None,
                        "rule_hits": [
                            h.model_dump() if hasattr(h, "model_dump") else h for h in rule_hits
                        ],
                        "agent_trace": agent_trace,
                        "skipped_llm": skipped_llm,
                        "kafka_metadata": {
                            "topic": message.topic,
                            "partition": message.partition,
                            "offset": message.offset,
                            "timestamp": message.timestamp,
                        },
                    }

                    await self._producer.send_and_wait(self.output_topic, alert)

                except Exception as e:
                    # Route to error topic and keep consuming: a bad message
                    # must never kill the loop (poison-pill protection)
                    error_alert = {
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "raw_preview": message.value[:200].decode("utf-8", errors="replace")
                        if isinstance(message.value, bytes)
                        else str(message.value)[:200],
                        "kafka_metadata": {
                            "topic": message.topic,
                            "partition": message.partition,
                            "offset": message.offset,
                        },
                    }
                    await self._producer.send_and_wait(
                        f"{self.output_topic}-errors", error_alert
                    )

        except KafkaConnectionError:
            # Reconnect logic would go here
            pass


class LogProducer:
    """Produce log events to Kafka for analysis."""

    def __init__(self, bootstrap_servers: str | None = None, topic: str | None = None):
        self.bootstrap_servers = bootstrap_servers or os.getenv(
            "KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"
        )
        self.topic = topic or os.getenv("KAFKA_INPUT_TOPIC", "sentinel-logs")
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        """Start the producer."""
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            acks="all",
        )
        await self._producer.start()

    async def stop(self) -> None:
        """Stop the producer."""
        if self._producer:
            await self._producer.stop()

    async def send_log(self, log: dict[str, Any]) -> None:
        """Send a log event to Kafka."""
        if not self._producer:
            raise RuntimeError("Producer not started")
        await self._producer.send_and_wait(self.topic, log)

    async def send_batch(self, logs: list[dict[str, Any]]) -> None:
        """Send multiple log events to Kafka."""
        if not self._producer:
            raise RuntimeError("Producer not started")
        for log in logs:
            await self._producer.send(self.topic, log)
        await self._producer.flush()


async def main():
    """Example: Run the Kafka streamer."""
    streamer = KafkaStreamer()
    await streamer.start()
    print(f"Kafka streamer started, consuming from {streamer.input_topic}")

    try:
        await streamer.process_messages()
    except KeyboardInterrupt:
        print("Stopping...")
    finally:
        await streamer.stop()


if __name__ == "__main__":
    asyncio.run(main())
