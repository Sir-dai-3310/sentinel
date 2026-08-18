# Sentinel 灾难恢复计划（Disaster Recovery Plan, v1.2）

## 1. 目标（RPO / RTO）

| 指标 | 目标值 | 依据 |
|---|---|---|
| **RPO**（可容忍数据丢失量） | **24 小时** | Sentinel 的核心持久状态是「分析结果 / 规则 / 统计」等 PostgreSQL 数据，属分析型而非交易型数据；每日一次逻辑备份的成本与价值平衡合理。流式 Kafka 输入本身有 broker 端持久化与重放能力，可进一步缩小有效数据丢失窗口。 |
| **RTO**（可容忍恢复时间） | **4 小时** | 逻辑备份 `pg_restore` 在数十 GB 量级通常在 1–2 小时内完成；加上环境重建（compose/helm 重新部署）与验证，4 小时是可达成且对安全分析业务可接受的恢复窗口。 |

> 若业务对 RPO 要求更高，应升级到 **WAL 归档 + PITR**（见 §4.3），可将 RPO 降至分钟级。

## 2. 数据资产与备份范围

| 资产 | 存储 | 备份方式 | 频率 |
|---|---|---|---|
| 分析结果 / 规则 / 统计 / 租户 | PostgreSQL 16 | `pg_dump`（custom 压缩格式） | 每日（见 §3） |
| 缓存 / 队列 | Redis 7 | `BGSAVE` RDB 快照（**尽力而为**，可重建，非关键） | 每日，失败不阻断 |
| 流式日志/告警 | Kafka topic | broker 端日志段持久化 + `retention.ms`；不在本 DRP 备份范围（依赖 Kafka 自身副本/重放） | — |
| 规则定义 | `rules/`（Git 版本控制） | 代码库即真相源 | 随提交 |
| 配置 / 密钥 | K8s Secret / compose env | 由密钥管理系统（Vault/sealed-secrets）另行管理，**不**进入普通备份 | — |

## 3. 备份步骤（引用 scripts/backup.sh）

`scripts/backup.sh` 执行 PostgreSQL 逻辑备份 + 可选 Redis 快照 + 保留期清理：

```bash
# 手动执行一次备份
export PGHOST=localhost PGPORT=5432 PGUSER=sentinel PGPASSWORD=*** PGDATABASE=sentinel
./scripts/backup.sh /var/backups/sentinel
# 产出: /var/backups/sentinel/sentinel-pg-<UTC时间戳>.dump
```

建议用 **cron / K8s CronJob** 每日调度（满足 RPO 24h）：

```yaml
# 示例：K8s CronJob（每日 02:00 UTC）
apiVersion: batch/v1
kind: CronJob
metadata:
  name: sentinel-backup
  namespace: sentinel
spec:
  schedule: "0 2 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: backup
              image: postgres:16-alpine
              command: ["/bin/sh", "/scripts/backup.sh", "/backups"]
              envFrom: [{ secretRef: { name: sentinel-credentials } }]
          restartPolicy: OnFailure
```

**异地/异质副本**：备份文件应同步到对象存储（S3/MinIO）或异地卷，避免单点。可用
`rclone` / `aws s3 sync` 在 backup.sh 之后追加上传步骤。

## 4. 恢复与故障转移

### 4.1 从逻辑备份恢复（标准路径）

```bash
# 1. 准备一个干净的 PostgreSQL 实例（compose 或 K8s StatefulSet）
# 2. 恢复
pg_restore --host=<host> --username=sentinel --dbname=sentinel \
  --clean --if-exists --jobs=4 \
  /var/backups/sentinel/sentinel-pg-<时间戳>.dump

# 3. 验证
psql -h <host> -U sentinel -d sentinel -c "SELECT count(*) FROM <核心表>;"

# 4. 重新部署应用层并指向恢复后的数据库
docker compose up -d            # 或: kubectl apply -k k8s/
```

### 4.2 故障转移（可用性提升路径）

- **应用层多副本**：`k8s/api.yaml` / `k8s/web.yaml` 默认 `replicas: 2`，配合 Service
  负载均衡与 readiness 探针，单 Pod 故障自动摘除；HPA（`helm` `autoscaling`）应对流量峰。
- **PostgreSQL 读副本 / 主备**：生产建议使用 Patroni / CloudNativePG / 云厂商托管
  （RDS/Aurora/Cloud SQL）实现自动主备切换（秒级~分钟级 RTO）。本仓库的
  `k8s/postgres.yaml` StatefulSet 是自包含的单副本默认方案，适用于 dev/小部署。
- **Redis**：缓存可重建，故障时重启即可；如需高可用可上 Redis Sentinel / Cluster。

### 4.3 PITR（Point-in-Time Recovery，进阶）

要把 RPO 从 24h 降到分钟级：

1. 开启 PostgreSQL WAL 归档：`archive_mode=on`，`archive_command` 将 WAL 段
   推送到对象存储（可用 `wal-g` / `pgBackRest` / `barman`）。
2. 保留一个 base backup + 连续 WAL 流。
3. 恢复时：还原 base backup → 重放 WAL 至目标时间点（`recovery_target_time`）。

落地路径（推荐顺序）：`pgBackRest`（成熟、支持增量与 S3）或 `wal-g`。

## 5. 演练清单（DR Drill Checklist）

每季度至少演练一次完整恢复流程：

- [ ] 从最新备份执行 `pg_restore` 到隔离环境，确认无报错
- [ ] 校验关键表行数 / 抽样数据与生产一致
- [ ] 用恢复后的库重启应用栈，`/api/v1/health` 与 `/api/v1/stats` 返回 200
- [ ] 测量并记录实际 RTO（从"宣告灾难"到"服务可用"），与 4h 目标比对
- [ ] 验证备份文件异地副本可下载（对象存储取回测试）
- [ ] 演练 Kafka topic 数据重放（如启用），确认消费者能追上
- [ ] 记录演练结果、发现的问题与改进项，更新本文档

## 6. 关联文档

- 混沌测试（broker kill / 依赖降级实测）：`docs/chaos-testing.md`
- 自动恢复机制（restart policy / 探针自愈）：`docs/auto-recovery.md`
- 备份脚本：`scripts/backup.sh`
