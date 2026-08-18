#!/usr/bin/env bash
# Kafka broker kill/restart chaos test for Sentinel streaming consumers.
#
# REAL execution against a KRaft-mode Kafka broker on localhost:9092.
#
# Flow:
#   1. Baseline: produce N log events, confirm consumer processes them.
#   2. CHAOS:    kill -9 the Kafka broker while a consumer is running;
#                observe consumer failure / reconnection attempts.
#   3. Recover:  restart the broker; produce more events;
#                confirm the consumer group resumes and NO message is lost
#                (all produced offsets are eventually consumed).
#
# Usage:
#   bash scripts/chaos/kafka-kill.sh
#
# Env overrides:
#   KAFKA_HOME   (default /tmp/kafka-setup/kafka)
#   JAVA_HOME    (default /tmp/kafka-setup/jdk)
#   BOOTSTRAP    (default localhost:9092)
#
# Exit code: 0 = chaos test passed (recovery + no loss), 1 = failure.

set -u
BOOTSTRAP="${BOOTSTRAP:-localhost:9092}"
KAFKA_HOME="${KAFKA_HOME:-/tmp/kafka-setup/kafka}"
JAVA_HOME="${JAVA_HOME:-/tmp/kafka-setup/jdk}"
export JAVA_HOME PATH="$JAVA_HOME/bin:$KAFKA_HOME/bin:$PATH"

PROJ_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
AGENTS_DIR="$PROJ_ROOT/sentinel-agents"
LOG="/tmp/chaos-kafka.log"
: > "$LOG"

say() { echo "[chaos $(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

broker_pid() {
  # Match the running KafkaServer java process (KRaft combined mode).
  pgrep -f "kafka.Kafka" | head -1
}

wait_broker_up() {
  local tries="${1:-40}"
  for _ in $(seq 1 "$tries"); do
    if (exec 3<>"/dev/tcp/127.0.0.1/9092") 2>/dev/null; then exec 3>&- 3<&-; return 0; fi
    sleep 1
  done
  return 1
}

wait_broker_down() {
  local tries="${1:-20}"
  for _ in $(seq 1 "$tries"); do
    if ! (exec 3<>"/dev/tcp/127.0.0.1/9092") 2>/dev/null; then return 0; fi
    sleep 1
  done
  return 1
}

# --- Python chaos probe: consume the whole log, assert all expected ids present ---
run_probe() {  # $1 = JSON array of expected chaos_ids
  local EXPECTED="$1"
  PYTHONPATH="$AGENTS_DIR" python3 - "$BOOTSTRAP" "$EXPECTED" <<'PYEOF'
import asyncio, json, sys, uuid
from aiokafka import AIOKafkaConsumer

BOOTSTRAP = sys.argv[1]
expect = set(json.loads(sys.argv[2]))
TOPIC = "sentinel-logs"

async def consume(expect_ids, timeout=45):
    # Fresh group each run + earliest: read the whole log so we can assert that
    # every produced chaos_id (pre-kill and post-kill) is still present, i.e. no loss.
    c = AIOKafkaConsumer(TOPIC, bootstrap_servers=BOOTSTRAP,
                         group_id=f"chaos-probe-{uuid.uuid4().hex[:8]}",
                         auto_offset_reset="earliest",
                         value_deserializer=lambda m: json.loads(m.decode()))
    await c.start()
    got = set()
    deadline = asyncio.get_event_loop().time() + timeout
    try:
        while asyncio.get_event_loop().time() < deadline and not expect_ids.issubset(got):
            batch = await c.getmany(timeout_ms=1500)
            for _tp, msgs in batch.items():
                for m in msgs:
                    cid = m.value.get("chaos_id")
                    if cid:
                        got.add(cid)
            await asyncio.sleep(0.2)
    finally:
        await c.stop()
    return got

async def main():
    got = await consume(expect)
    missing = expect - got
    print(f"PROBE consumed={len(got & expect)}/{len(expect)} missing={len(missing)}")
    if missing:
        print("MISSING:", sorted(missing)[:10])
        return 1
    print("PROBE OK: no message loss")
    return 0

sys.exit(asyncio.run(main()))
PYEOF
}

produce_batch() {  # $1=count $2=prefix -> prints JSON list of ids (stdout, aiokafka logs silenced)
  PYTHONPATH="$AGENTS_DIR" python3 - "$BOOTSTRAP" "$1" "$2" <<'PYEOF'
import asyncio, json, sys, logging
logging.disable(logging.CRITICAL)  # keep stdout clean: only the JSON id list
from aiokafka import AIOKafkaProducer
BOOTSTRAP, N, PREFIX = sys.argv[1], int(sys.argv[2]), sys.argv[3]
async def go():
    p = AIOKafkaProducer(bootstrap_servers=BOOTSTRAP)
    await p.start()
    ids = []
    for i in range(N):
        key = f"{PREFIX}-{i}"
        await p.send_and_wait("sentinel-logs", json.dumps({"chaos_id": key, "EventID": 4688}).encode())
        ids.append(key)
    await p.stop()
    sys.stdout.write(json.dumps(ids))
asyncio.run(go())
PYEOF
}

say "=== Sentinel Kafka chaos test (kill/restart) ==="
say "broker bootstrap=$BOOTSTRAP kafka_home=$KAFKA_HOME"

# 0. Preconditions
PID_BEFORE="$(broker_pid || true)"
if [ -z "$PID_BEFORE" ]; then
  say "ERROR: no Kafka broker process found. Start one first (see docs/chaos-testing.md)."
  exit 1
fi
say "baseline: broker running pid=$PID_BEFORE"

# 1. Baseline produce + confirm consumable (no loss while healthy)
say "phase 1: baseline produce 20 events"
IDS_A="$(produce_batch 20 baseline)"
say "baseline ids captured: $(echo "$IDS_A" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))' 2>/dev/null || echo '?')"
run_probe "$IDS_A" | tee -a "$LOG"
say "phase 1 done"

# 2. CHAOS: kill -9 the broker
say "phase 2: CHAOS -> kill -9 broker pid=$PID_BEFORE"
kill -9 "$PID_BEFORE"
if wait_broker_down 20; then
  say "broker confirmed DOWN (9092 closed)"
else
  say "WARNING: 9092 still open after kill"
fi

# 3. Observe consumer behaviour while broker is down (expect failures)
say "phase 3: probe consumer during outage (expect connection failure)"
PYTHONPATH="$AGENTS_DIR" python3 - "$BOOTSTRAP" <<'PYEOF' 2>&1 | tee -a "$LOG"
import asyncio, sys
from aiokafka import AIOKafkaConsumer
async def go():
    try:
        c = AIOKafkaConsumer("sentinel-logs", bootstrap_servers=sys.argv[1],
                             group_id="chaos-outage", request_timeout_ms=4000)
        await asyncio.wait_for(c.start(), timeout=6)
        print("UNEXPECTED: consumer connected during outage")
        await c.stop()
        return 0
    except Exception as e:
        print(f"EXPECTED consumer failure during outage: {type(e).__name__}: {e}")
        return 0
asyncio.run(go())
PYEOF

# 4. Recover: restart broker
say "phase 4: restart broker"
nohup kafka-server-start.sh "$KAFKA_HOME/config/server.properties" >> /tmp/kafka-setup/kafka-server.log 2>&1 &
if wait_broker_up 40; then
  NEWPID="$(broker_pid)"
  say "broker recovered pid=$NEWPID (9092 listening)"
else
  say "ERROR: broker did not come back"
  exit 1
fi

# 5. Post-recovery produce + verify ALL messages (pre-kill + post-kill) consumed, none lost
say "phase 5: post-recovery produce 20 more events"
IDS_B="$(produce_batch 20 recovery)"

say "phase 6: verify no message loss across the kill window"
# Re-check baseline batch is still consumable (offsets survived the crash) AND new batch works.
MERGED="$(python3 -c "import json,sys; a=json.loads(sys.argv[1]); b=json.loads(sys.argv[2]); print(json.dumps(a+b))" "$IDS_A" "$IDS_B")"
FINAL_OUT="$(run_probe "$MERGED")"
echo "$FINAL_OUT" | tee -a "$LOG"
if echo "$FINAL_OUT" | grep -q "PROBE OK"; then
  say "=== CHAOS TEST PASSED: broker recovered, consumer resumed, no message loss ==="
  exit 0
else
  say "=== CHAOS TEST FAILED: message loss detected ==="
  exit 1
fi
