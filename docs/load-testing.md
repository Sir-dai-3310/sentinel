# Sentinel 负载测试报告（v1.2 reliability）

> 状态：**已真实执行**（本机，SQLite 后端，单 worker uvicorn）。
> 工具：`scripts/load_test.py`（asyncio + httpx）。
> 未使用 locust 的原因见下文「工具选型」。

## 1. 测试方法

### 被测端点（按任务要求覆盖 3 个）

| 端点 | 方法 | 权重 | 说明 |
|---|---|---|---|
| `/api/v1/health` | GET | 3 | 健康检查（无认证） |
| `/api/v1/analyze` | POST | 2 | 单条日志分析（小样本，命中内置规则） |
| `/api/v1/stats` | GET | 1 | 统计聚合 |

- 小日志样本：Suspicious PowerShell（`EventID 4688`，`sekurlsa::logonpasswords`），
  会触发内置 Sigma 风格规则引擎。
- 认证：用 `app.auth.jwt.create_access_token("loadtest", roles=["admin"])` 现场签发
  的本地测试 JWT（默认 secret，仅本机测试用）。
- 关于 `/api/v1/analyze` 的 HTTP 500：本机无 LLM 凭据，agent graph 在调用 LLM 时
  抛出 `Missing credentials`。请求仍然真实走完了 **认证 → 参数校验 → 规则引擎**，
  只在 LLM 调用处失败。因此 500 被视为「路径可达」信号单独统计，不隐藏。

### 启动方式

```bash
cd sentinel-api
DATABASE_URL="sqlite+aiosqlite:///./sentinel_test.db" \
  PYTHONPATH=../sentinel-agents:. \
  uvicorn app.main:app --port 8000
```

### 运行命令

```bash
export SENTINEL_TOKEN=<jwt>
python3 scripts/load_test.py --host http://localhost:8000 --concurrency 50 --duration 60
```

## 2. 真实结果

### 运行 A —— 默认配置（含限流 RateLimit=100/60s/IP）

```json
{
  "concurrency": 50, "duration_s": 60.6,
  "total_requests": 6237, "rps": 102.9,
  "endpoints": [
    {"endpoint": "health",  "requests": 3203, "ok_2xx_3xx": 3203,
     "status_counts": {"200": 3203},
     "latency_ms": {"p50": 268.9, "p95": 1266.2, "p99": 2190.1, "max": 4725.8, "mean": 411.0}},
    {"endpoint": "analyze", "requests": 2021, "ok_2xx_3xx": 0,
     "status_counts": {"429": 1948, "500": 73},
     "latency_ms": {"p50": 256.7, "p95": 1205.0, "p99": 2032.3, "max": 4216.2, "mean": 399.1}},
    {"endpoint": "stats",   "requests": 1013, "ok_2xx_3xx": 33,
     "status_counts": {"200": 33, "429": 980},
     "latency_ms": {"p50": 249.7, "p95": 1229.2, "p99": 2021.3, "max": 3001.6, "mean": 395.8}}
  ]
}
```

观察：`/api/v1/analyze` 与 `/api/v1/stats` 大量返回 **HTTP 429**——触发了 API 内置的
`RateLimitMiddleware`（默认每 IP 100 次 / 60s）。`/api/v1/health` 无认证、未被限流影响。

### 运行 B —— 放宽限流对照（RATE_LIMIT=100000）

```json
{
  "concurrency": 50, "duration_s": 60.1,
  "total_requests": 3304, "rps": 55.0,
  "endpoints": [
    {"endpoint": "health",  "requests": 1775, "ok_2xx_3xx": 1775,
     "status_counts": {"200": 1775},
     "latency_ms": {"p50": 542.1, "p95": 2414.4, "p99": 3942.5, "max": 8356.8, "mean": 775.3}},
    {"endpoint": "analyze", "requests": 996, "ok_2xx_3xx": 0,
     "status_counts": {"500": 994},
     "latency_ms": {"p50": 615.4, "p95": 2508.3, "p99": 4093.1, "max": 5885.7, "mean": 861.8}},
    {"endpoint": "stats",   "requests": 533, "ok_2xx_3xx": 532,
     "status_counts": {"200": 532},
     "latency_ms": {"p50": 554.6, "p95": 2263.0, "p99": 4104.4, "max": 5894.8, "mean": 795.0}}
  ]
}
```

## 3. 瓶颈分析

| 现象 | 解读 |
|---|---|
| 运行 A RPS(102.9) > 运行 B RPS(55.0) | 限流器以极低成本快速拒绝（429），撑起了表面吞吐。放宽限流后，请求真正进入处理链路，吞吐反而下降——**说明瓶颈不在限流器，而在应用本身**。 |
| 运行 B 各端点 p50 ≈ 550ms、p99 > 4s | 单 worker uvicorn 在 50 并发下事件循环饱和；SQLite 单连接写入串行化；`/api/v1/analyze` 的 agent graph 为同步阻塞型调用，进一步拖慢事件循环。 |
| `analyze` 全部 500 | 无 LLM 凭据的环境预期行为；规则引擎已先执行。生产环境接入 LLM 后该路径延迟将由 LLM 往返主导。 |
| `health` 也出现高尾延迟（max 8.3s） | 即使最轻的端点也被同一事件循环上的重请求拖累——典型的「无请求隔离」症状。 |

**结论**：在默认配置下，第一约束是 **内置限流器**；绕过限流后，第一约束变为
**单 worker 事件循环 + 同步 agent 调用 + SQLite 串行写**。

## 4. 改进建议

1. **多 worker 水平扩展**：`uvicorn --workers N` 或 gunicorn + uvicorn worker；
   或直接依赖 `helm/sentinel` 的 `replicaCount` + HPA（见 `k8s/` 与 `helm/`）。
2. **agent 调用异步化 / 线程池卸载**：将 `analyze_log` 这类 CPU/阻塞型调用放入
   `asyncio.to_thread` 或独立任务队列（Redis + worker），避免阻塞 API 事件循环。
3. **限流策略调优**：当前 100/60s/IP 对机器对机器的 `/api/v1/analyze` 过严；
   建议按 API key / tenant 维度限流，健康检查端点完全豁免。
4. **生产用 PostgreSQL**：SQLite 仅适合本地验证；`docker-compose.yml` 与
   `helm` chart 已默认指向 PostgreSQL 16。
5. **为 `analyze` 增加队列背压**：高峰时将分析请求入队异步处理，前端轮询/WebSocket
   取结果，避免长连接占用 worker。

## 5. 工具选型：为何是 load_test.py 而非 locust

按任务要求首选 locust，但本机 `import locust` 失败：

```
ModuleNotFoundError: No module named 'zope.event'
```

根因：Debian/Ubuntu 系统的 `/usr/lib/python3/dist-packages/zope/__init__.py` 使用
`pkg_resources.declare_namespace`，遮蔽了 `pip install --user` 安装的 `zope.event`
（无 sudo 无法修复系统包）。已按任务允许的 fallback 改用 asyncio+httpx 的
`scripts/load_test.py`（可复现、输出同等指标）。

`locustfile.py` 已一并交付，在环境正常的机器上可直接运行：

```bash
pip3 install locust
export SENTINEL_TOKEN=<jwt>
locust -f locustfile.py --headless -u 50 -r 10 -t 60s --host http://localhost:8000
```

## 6. 复现清单

```bash
# 1. 起 API（SQLite）
cd sentinel-api
DATABASE_URL="sqlite+aiosqlite:///./sentinel_test.db" PYTHONPATH=../sentinel-agents:. \
  uvicorn app.main:app --port 8000 &

# 2. 签发测试 token
export SENTINEL_TOKEN=$(PYTHONPATH=../sentinel-agents:. python3 -c \
  'from app.auth.jwt import create_access_token; print(create_access_token("loadtest", roles=["admin"]))')

# 3. 跑负载（60s / 50 并发）
python3 scripts/load_test.py --host http://localhost:8000 --concurrency 50 --duration 60
```
