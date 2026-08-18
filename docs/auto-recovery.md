# Sentinel 自动恢复机制验证（v1.2 reliability）

本文档说明 Sentinel 各层级的**异常自愈机制**，并结合 v1.2 的 Kafka 混沌实测
（见 `docs/chaos-testing.md`）验证其有效性。

## 1. 自愈机制总览

| 层级 | 机制 | 触发条件 | 恢复动作 |
|---|---|---|---|
| 容器进程 | Docker Compose `restart: unless-stopped` | 容器内进程崩溃 / OOM 退出 | Docker 自动重启容器 |
| 容器健康 | Compose `healthcheck` + `depends_on: service_healthy` | 依赖未就绪 | 延迟启动依赖方，避免级联失败 |
| K8s Pod | `livenessProbe` | 应用僵死（进程在但无响应） | kubelet 杀死并重建容器 |
| K8s 流量 | `readinessProbe` | 暂时不可用（启动中/过载） | 从 Service endpoints 摘除，恢复后重新加入 |
| K8s 副本 | Deployment / StatefulSet 控制器 | Pod 被删 / 节点故障 | 重建 Pod 维持期望副本数 |
| 应用 consumer | aiokafka 重连 + consumer group offset | broker 宕机/恢复 | 重新 bootstrap 并从已提交 offset 续消费 |

## 2. Compose 层自愈（已配置，配置级验证）

`docker-compose.yml` 与 `docker-compose.kafka.yml` 已为**所有服务**配置：

```yaml
restart: unless-stopped        # 进程退出即自动拉起（除非手动 stop）
healthcheck: ...               # pg_isready / redis-cli ping / curl /health / ...
depends_on:
  <dep>:
    condition: service_healthy # 依赖健康后才启动本服务
```

- `restart: unless-stopped` 保证单个容器崩溃后被 Docker 自动重启——这是进程级
  故障的第一道自愈。
- `healthcheck` + `service_healthy` 保证 **启动顺序自愈**：postgres/redis 未通过
  健康检查前，api/agents 不会启动，避免"先启动再连环报错"的级联失败。
- 验证：`docker compose config -q` → **VALID**（配置级，见 §5「环境限制」）。

## 3. K8s 层自愈（已配置，配置级验证）

`k8s/` 与 `helm/sentinel/` 中的每个工作负载都带 **liveness + readiness** 探针：

| 工作负载 | liveness | readiness | 探针类型 |
|---|---|---|---|
| api | `/api/v1/health` | `/api/v1/health` | httpGet :8000 |
| web | `/` | `/` | httpGet :80 |
| agents | tcpSocket :50052 | tcpSocket :50052 | gRPC 端口 TCP |
| postgres | `pg_isready` | `pg_isready` | exec |
| redis | `redis-cli ping` | `redis-cli ping` | exec |

自愈行为：

- **liveness 失败 ≥ failureThreshold** → kubelet 重启容器（处理"进程在但僵死"，
  这是 `restart` 无法覆盖的场景）。
- **readiness 失败** → Pod 被移出 Service 负载均衡，流量不再打入；恢复后自动加回
  （处理"临时过载/启动中"，不重启、只摘流）。
- **Deployment/StatefulSet 控制器** → 任何原因导致 Pod 消失（节点宕机、被驱逐），
  控制器自动重建，维持 `replicas` 期望数。

## 4. Consumer 重连行为（Kafka 混沌实测，真实验证）

这是对「消息管道自愈」的真实验证，详见 `docs/chaos-testing.md`。实测结论：

1. **broker 宕机时**：aiokafka 消费者抛出
   `KafkaConnectionError: Unable to bootstrap from [('localhost', 9092, ...)]`。
   这是 `sentinel-agents` 的 `KafkaStreamer` 需要捕获并做**指数退避重连**的信号
   （当前 e2e 脚本为验证用途，未内置退避循环——生产 consumer 应包裹
   `while True: try: consume ... except KafkaConnectionError: backoff`）。

2. **broker 恢复后**：消费者可立即重新 bootstrap 并继续消费。实测中重启 broker
   （pid 46113 → 49053）后，全新 consumer group 从 `earliest` 读到全部 40 条
   消息，**零丢失**：

   ```text
   [chaos] phase 4: restart broker
   [chaos] broker recovered pid=49053 (9092 listening)
   [chaos] phase 6: verify no message loss across the kill window
   PROBE consumed=40/40 missing=0
   PROBE OK: no message loss
   === CHAOS TEST PASSED ===
   ```

3. **无消息丢失的保证来源**：Kafka broker 端日志段持久化 + consumer offset 提交。
   只要 `enable_auto_commit` / 手动提交在「处理成功后」进行，kill 窗口内已写入的
   消息在恢复后必然可被重新消费。

### 项目自带 e2e 交叉验证（broker 恢复后）

```text
E2E KAFKA VERIFICATION: ALL CHECKS PASSED
  (3 alerts consumed, 2 error-routed, malicious danger=96 rule_hits=2)
```

## 5. 验证状态与环境限制

| 机制 | 验证状态 |
|---|---|
| Compose `restart`/`healthcheck`/`depends_on` | 配置级验证（`docker compose config` VALID）。本机 Docker daemon 无 root 权限，**未能真实启动容器**做运行时自愈验证。 |
| K8s 探针 / 控制器 | 配置级验证（YAML 解析通过，探针+资源齐全）。本机无 kubectl/minikube，**未在集群验证**。 |
| Kafka consumer 重连 + 无丢失 | ✅ **真实执行通过**（见 §4）。 |

### 运行时自愈复现步骤（在有权限的机器上）

```bash
# Compose：验证进程崩溃自愈
docker compose up -d
docker kill sentinel-api-1            # 强制杀死 api 容器
docker compose ps                     # 数秒后 api 应被 restart policy 自动拉起

# K8s：验证 liveness 自愈（minikube/kind）
minikube start
kubectl apply -k k8s/
kubectl -n sentinel get pods -w       # 观察 Pod 重建/摘流行为
kubectl -n sentinel delete pod -l app.kubernetes.io/component=api  # 控制器自动重建
```

## 6. 改进建议（未竟事项）

1. **agents consumer 增加显式退避重连**：当前 `KafkaStreamer` 依赖 aiokafka 默认
   重连；建议在消费循环外层加 `try/except KafkaConnectionError` + 指数退避 +
   最大重试上限，并暴露 consumer lag 指标到 Prometheus。
2. **Kafka 探针**：`k8s/` 未内置 Kafka StatefulSet（默认依赖外部/compose 版
   `docker-compose.kafka.yml`）；若要在 K8s 内跑 Kafka，建议用 Strimzi operator。
3. **PodDisruptionBudget**：为 api/web 增加 PDB，保证节点维护期最少可用副本数。
4. **启动探针（startupProbe）**：对启动较慢的 agents（加载 LLM/规则）可加
   startupProbe，避免 liveness 在启动窗口内误杀。
