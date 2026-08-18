# Sentinel 混沌测试方案与实测结果（v1.2 reliability）

## 1. 目标与范围

验证 Sentinel 在关键基础设施故障下的韧性与恢复能力：

| 场景 | 脚本 | 本环境是否真实执行 |
|---|---|---|
| Kafka broker kill / restart | `scripts/chaos/kafka-kill.sh` | ✅ **真实执行通过** |
| Compose 依赖（PostgreSQL/Redis）kill | `scripts/chaos/compose-dependency-kill.sh` | ⚠️ 未在本环境验证（Docker daemon 无 root 权限），提供可复现步骤 |

## 2. Kafka 混沌测试（真实执行）

### 2.1 环境说明

任务文档假设「本机 9092 已有真实 Kafka broker（v1.4 遗留，/tmp/kafka-setup/）」，
但实测时该目录与进程均不存在。为满足「真实执行」要求，本次先自建了 KRaft 模式
broker（下载便携 JDK 17 + Apache Kafka 4.1.2 至 `/tmp/kafka-setup/`），再对其施测：

```bash
export JAVA_HOME=/tmp/kafka-setup/jdk
export PATH=$JAVA_HOME/bin:/tmp/kafka-setup/kafka/bin:$PATH
# KRaft 格式化 + 启动
kafka-storage.sh format -t $(kafka-storage.sh random-uuid) \
  -c /tmp/kafka-setup/kafka/config/server.properties --standalone
nohup kafka-server-start.sh /tmp/kafka-setup/kafka/config/server.properties &
# 建主题
kafka-topics.sh --create --topic sentinel-logs          --bootstrap-server localhost:9092
kafka-topics.sh --create --topic sentinel-alerts        --bootstrap-server localhost:9092
kafka-topics.sh --create --topic sentinel-alerts-errors --bootstrap-server localhost:9092
```

### 2.2 测试流程（`scripts/chaos/kafka-kill.sh`）

1. **基线**：生产 20 条日志事件到 `sentinel-logs`，确认全部可消费。
2. **注入故障**：`kill -9` broker 进程，确认 9092 端口关闭。
3. **观察失败**：在停服窗口内启动消费者，预期并捕获连接失败。
4. **恢复**：重启 broker，确认 9092 重新监听。
5. **无丢失校验**：恢复后再生产 20 条；用一个全新 consumer group 从 `earliest`
   全量读取，断言「kill 前 + kill 后」共 40 条消息的 `chaos_id` 全部存在，零丢失。

### 2.3 真实运行输出

```text
[chaos 20:45:23] === Sentinel Kafka chaos test (kill/restart) ===
[chaos 20:45:24] baseline: broker running pid=46113
[chaos 20:45:24] phase 1: baseline produce 20 events
[chaos 20:45:24] baseline ids captured: 20
PROBE consumed=20/20 missing=0
PROBE OK: no message loss
[chaos 20:45:29] phase 2: CHAOS -> kill -9 broker pid=46113
[chaos 20:45:30] broker confirmed DOWN (9092 closed)
[chaos 20:45:30] phase 3: probe consumer during outage (expect connection failure)
EXPECTED consumer failure during outage: KafkaConnectionError: KafkaConnectionError:
  Unable to bootstrap from [('localhost', 9092, <AddressFamily.AF_UNSPEC: 0>)]
[chaos 20:45:31] phase 4: restart broker
[chaos 20:45:52] broker recovered pid=49053 (9092 listening)
[chaos 20:45:52] phase 5: post-recovery produce 20 more events
[chaos 20:45:52] phase 6: verify no message loss across the kill window
PROBE consumed=40/40 missing=0
PROBE OK: no message loss
[chaos 20:45:56] === CHAOS TEST PASSED: broker recovered, consumer resumed, no message loss ===
```

恢复确认：

```text
$ pgrep -f "kafka.Kafka"
49053
$ (exec 3<>/dev/tcp/localhost/9092) && echo LISTENING
9092 LISTENING (broker restored)
```

### 2.4 项目自带 e2e 交叉验证

恢复后的 broker 上运行项目自带的 `examples/verify_streaming_e2e.py`
（真实走 `KafkaStreamer` → `analyze_log` → `sentinel-alerts` 全链路）：

```text
[1] KafkaStreamer started (input=sentinel-logs, output=sentinel-alerts)
[2] Produced 3 log events to sentinel-logs
[3] Injected 1 non-dict event + 1 broken-JSON event
[4] Consumed 3 alerts, 2 error events
[5] Sample malicious alert verdict: malicious=True, danger=96, rule_hits=2
[6] Error routing works: expected dict log event, got str
[7] benign verdicts: 1, malicious alerts: 2
E2E KAFKA VERIFICATION: ALL CHECKS PASSED
```

### 2.5 结论

- **无消息丢失**：Kafka 持久化日志 + consumer offset 机制保证 kill -9 后已写入
  的消息全部存活；消费者以新 group 从头读到全部 40 条。
- **消费者行为符合预期**：broker 宕机时 aiokafka 抛出 `KafkaConnectionError`
  （Unable to bootstrap），这是上层 `KafkaStreamer` 需要捕获并做指数退避重连的信号。
- **恢复后自动续跑**：broker 恢复后消费者可立即重新 bootstrap 并继续消费。

> **本环境遗留状态**：测试完成后 Kafka broker 保持运行（pid 49053，9092 监听中），
> 位于 `/tmp/kafka-setup/`。如需清理：`pkill -f kafka.Kafka`。

## 3. Compose 依赖混沌测试（未在本环境验证，提供复现步骤）

本机 Docker CLI 可用，但 daemon 无 root 权限，无法真正启动容器，故该脚本
**未在当前环境真实执行**。以下为可复现步骤（在任何有 Docker 的机器上）：

```bash
# 1. 启动全栈
docker compose up -d

# 2. 确认健康
curl http://localhost:8000/api/v1/health

# 3. 跑依赖混沌测试
bash scripts/chaos/compose-dependency-kill.sh
```

脚本行为：

| 阶段 | 动作 | 预期 |
|---|---|---|
| 1 | `docker compose stop postgres` | `/api/v1/stats` 等 DB 路由返回 5xx，但 api 进程不崩溃（优雅降级） |
| 2 | `docker compose stop redis` | 缓存/队列降级，api 仍存活 |
| 3 | `docker compose start postgres redis` | 借助 compose restart policy + healthcheck，api 自动恢复 200 |

退出码 0 表示「降级 + 恢复」全部符合预期。

## 4. 自动恢复机制（关联文档）

Compose restart policy 与 K8s 探针如何实现自愈、以及本次 Kafka 实测反映的
consumer 重连行为，见 `docs/auto-recovery.md`。
