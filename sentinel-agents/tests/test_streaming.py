"""Tests for Kafka streaming module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sentinel_agents.streaming import KafkaStreamer, LogProducer


class TestLogProducer:
    """Tests for LogProducer."""

    @pytest.mark.asyncio
    async def test_start_and_stop(self):
        """Test producer start/stop lifecycle."""
        producer = LogProducer(bootstrap_servers="localhost:9092", topic="test")

        with patch("sentinel_agents.streaming.AIOKafkaProducer") as mock_class:
            mock_producer = AsyncMock()
            mock_class.return_value = mock_producer

            await producer.start()
            assert producer._producer is not None
            mock_producer.start.assert_called_once()

            await producer.stop()
            mock_producer.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_log(self):
        """Test sending a single log."""
        producer = LogProducer(bootstrap_servers="localhost:9092", topic="test")

        with patch("sentinel_agents.streaming.AIOKafkaProducer") as mock_class:
            mock_producer = AsyncMock()
            mock_class.return_value = mock_producer
            await producer.start()

            log = {"EventID": 1, "Image": "test.exe"}
            await producer.send_log(log)

            mock_producer.send_and_wait.assert_called_once()
            call_args = mock_producer.send_and_wait.call_args
            assert call_args[0][0] == "test"
            # Verify the log was serialized
            sent_value = call_args[0][1]
            assert sent_value["EventID"] == 1

    @pytest.mark.asyncio
    async def test_send_batch(self):
        """Test sending multiple logs."""
        producer = LogProducer(bootstrap_servers="localhost:9092", topic="test")

        with patch("sentinel_agents.streaming.AIOKafkaProducer") as mock_class:
            mock_producer = AsyncMock()
            mock_class.return_value = mock_producer
            await producer.start()

            logs = [{"id": i} for i in range(5)]
            await producer.send_batch(logs)

            assert mock_producer.send.call_count == 5
            mock_producer.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_log_not_started(self):
        """Test sending without starting raises error."""
        producer = LogProducer(bootstrap_servers="localhost:9092", topic="test")
        with pytest.raises(RuntimeError, match="not started"):
            await producer.send_log({"test": True})


class TestKafkaStreamer:
    """Tests for KafkaStreamer."""

    @pytest.mark.asyncio
    async def test_start_and_stop(self):
        """Test streamer start/stop lifecycle."""
        streamer = KafkaStreamer(
            bootstrap_servers="localhost:9092",
            input_topic="input",
            output_topic="output",
        )

        with patch("sentinel_agents.streaming.AIOKafkaConsumer") as mock_consumer_class, \
             patch("sentinel_agents.streaming.AIOKafkaProducer") as mock_producer_class:
            mock_consumer = AsyncMock()
            mock_producer = AsyncMock()
            mock_consumer_class.return_value = mock_consumer
            mock_producer_class.return_value = mock_producer

            await streamer.start()
            assert streamer._running is True
            mock_consumer.start.assert_called_once()
            mock_producer.start.assert_called_once()

            await streamer.stop()
            assert streamer._running is False
            mock_consumer.stop.assert_called_once()
            mock_producer.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_messages(self):
        """Test message processing."""
        streamer = KafkaStreamer(
            bootstrap_servers="localhost:9092",
            input_topic="input",
            output_topic="output",
        )

        # Create mock messages (raw bytes, as consumed without deserializer)
        import json as _json

        mock_message1 = MagicMock()
        mock_message1.value = _json.dumps({"EventID": 1, "Image": "powershell.exe"}).encode()
        mock_message1.topic = "input"
        mock_message1.partition = 0
        mock_message1.offset = 0
        mock_message1.timestamp = 1234567890

        mock_message2 = MagicMock()
        mock_message2.value = _json.dumps({"EventID": 1, "Image": "chrome.exe"}).encode()
        mock_message2.topic = "input"
        mock_message2.partition = 0
        mock_message2.offset = 1
        mock_message2.timestamp = 1234567891

        # Create async iterator for consumer
        async def mock_messages():
            yield mock_message1
            yield mock_message2

        with patch("sentinel_agents.streaming.AIOKafkaConsumer") as mock_consumer_class, \
             patch("sentinel_agents.streaming.AIOKafkaProducer") as mock_producer_class, \
             patch("sentinel_agents.streaming.analyze_log") as mock_analyze:

            mock_consumer = AsyncMock()
            mock_consumer.__aiter__ = lambda self: mock_messages()
            mock_producer = AsyncMock()

            mock_consumer_class.return_value = mock_consumer
            mock_producer_class.return_value = mock_producer

            # langgraph returns a plain dict
            from sentinel_agents.state import Verdict
            mock_analyze.return_value = {
                "verdict": Verdict(
                    malicious=True, danger_level=85, reason="Test",
                    mitre_techniques=[], recommended_actions=[]
                ),
                "rule_hits": [],
                "agent_trace": ["TriageAgent"],
                "skipped_llm": False,
            }

            await streamer.start()
            streamer._running = True
            await streamer.process_messages()

            # Verify analyze was called for each message
            assert mock_analyze.call_count == 2

            # Verify results were produced to the output topic (not errors)
            output_calls = [
                call for call in mock_producer.send_and_wait.call_args_list
                if call[0][0] == "output"
            ]
            assert len(output_calls) == 2
            # Alert payload has verdict and kafka metadata
            alert = output_calls[0][0][1]
            assert alert["verdict"]["malicious"] is True
            assert alert["kafka_metadata"]["topic"] == "input"

    @pytest.mark.asyncio
    async def test_process_message_error(self):
        """Test error handling during message processing."""
        streamer = KafkaStreamer(
            bootstrap_servers="localhost:9092",
            input_topic="input",
            output_topic="output",
        )

        import json as _json

        mock_message = MagicMock()
        mock_message.value = _json.dumps({"EventID": 1}).encode()
        mock_message.topic = "input"
        mock_message.partition = 0
        mock_message.offset = 0
        mock_message.timestamp = 1234567890

        async def mock_messages():
            yield mock_message

        with patch("sentinel_agents.streaming.AIOKafkaConsumer") as mock_consumer_class, \
             patch("sentinel_agents.streaming.AIOKafkaProducer") as mock_producer_class, \
             patch("sentinel_agents.streaming.analyze_log") as mock_analyze:

            mock_consumer = AsyncMock()
            mock_consumer.__aiter__ = lambda self: mock_messages()
            mock_producer = AsyncMock()

            mock_consumer_class.return_value = mock_consumer
            mock_producer_class.return_value = mock_producer

            # Make analyze fail
            mock_analyze.side_effect = Exception("Analysis failed")

            await streamer.start()
            streamer._running = True
            await streamer.process_messages()

            # Verify error was sent to error topic
            error_calls = [
                call for call in mock_producer.send_and_wait.call_args_list
                if "errors" in str(call)
            ]
            assert len(error_calls) > 0

    @pytest.mark.asyncio
    async def test_poison_pill_malformed_json_does_not_kill_loop(self):
        """Malformed JSON must route to error topic and the loop must continue.

        Regression test for the poison-pill bug: deserialization inside the
        consumer config crashed the fetch loop, blocking offset commits and
        causing infinite redelivery on restart.
        """
        import json as _json

        streamer = KafkaStreamer(
            bootstrap_servers="localhost:9092",
            input_topic="input",
            output_topic="output",
        )

        bad_message = MagicMock()
        bad_message.value = b"{invalid json"
        bad_message.topic = "input"
        bad_message.partition = 0
        bad_message.offset = 0
        bad_message.timestamp = 1234567890

        nondict_message = MagicMock()
        nondict_message.value = _json.dumps("just-a-string").encode()
        nondict_message.topic = "input"
        nondict_message.partition = 0
        nondict_message.offset = 1
        nondict_message.timestamp = 1234567891

        good_message = MagicMock()
        good_message.value = _json.dumps({"EventID": 1, "Image": "ok.exe"}).encode()
        good_message.topic = "input"
        good_message.partition = 0
        good_message.offset = 2
        good_message.timestamp = 1234567892

        async def mock_messages():
            yield bad_message
            yield nondict_message
            yield good_message

        with patch("sentinel_agents.streaming.AIOKafkaConsumer") as mock_consumer_class, \
             patch("sentinel_agents.streaming.AIOKafkaProducer") as mock_producer_class, \
             patch("sentinel_agents.streaming.analyze_log") as mock_analyze:

            mock_consumer = AsyncMock()
            mock_consumer.__aiter__ = lambda self: mock_messages()
            mock_producer = AsyncMock()
            mock_consumer_class.return_value = mock_consumer
            mock_producer_class.return_value = mock_producer

            from sentinel_agents.state import Verdict
            mock_analyze.return_value = {
                "verdict": Verdict(
                    malicious=False, danger_level=0, reason="clean",
                    mitre_techniques=[], recommended_actions=[]
                ),
                "rule_hits": [],
                "agent_trace": ["TriageAgent"],
                "skipped_llm": False,
            }

            await streamer.start()
            streamer._running = True
            await streamer.process_messages()

            calls = mock_producer.send_and_wait.call_args_list
            error_calls = [c for c in calls if c[0][0] == "output-errors"]
            output_calls = [c for c in calls if c[0][0] == "output"]

            # Two bad messages -> two error records
            assert len(error_calls) == 2
            # Loop survived the poison pills and still processed the good one
            assert len(output_calls) == 1
            assert mock_analyze.call_count == 1
            # Error record carries context
            err = error_calls[0][0][1]
            assert err["error_type"] in ("JSONDecodeError", "ValueError")
            assert "raw_preview" in err

    @pytest.mark.asyncio
    async def test_environment_variables(self):
        """Test configuration from environment variables."""
        with patch.dict("os.environ", {
            "KAFKA_BOOTSTRAP_SERVERS": "kafka:9092",
            "KAFKA_INPUT_TOPIC": "custom-logs",
            "KAFKA_OUTPUT_TOPIC": "custom-alerts",
            "KAFKA_GROUP_ID": "custom-group",
        }):
            streamer = KafkaStreamer()
            assert streamer.bootstrap_servers == "kafka:9092"
            assert streamer.input_topic == "custom-logs"
            assert streamer.output_topic == "custom-alerts"
            assert streamer.group_id == "custom-group"
