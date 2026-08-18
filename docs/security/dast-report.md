# DAST 报告 — OWASP API Security Baseline

- **日期**: 2026-08-18
- **方法**: OWASP ZAP 在本环境不可用（无 docker daemon、Java/大下载受限），按任务降级方案自写等价脚本
  `scripts/security/dast_baseline.py`（httpx），对**真实运行的 API**（uvicorn + SQLite + 真实 JWT 鉴权）执行动态测试。
- **目标实例**: `http://127.0.0.1:8000`，启动命令：
  `PYTHONPATH=../sentinel-agents:. DATABASE_URL=sqlite+aiosqlite:////tmp/sentinel-dast.db JWT_SECRET=<redacted> python3 -m uvicorn app.main:app`
- **覆盖**: OWASP API Security Top 10 中的 Broken Auth(2)、BOLA/文件系统(1)、Resource Consumption(4)、Injection(8)、Security Misconfiguration(7/8/9) + 安全响应头。

## 结果汇总（修复后最终运行）

```
== DAST baseline: 10 checks, 0 FAIL ==
[PASS] unauth-access      9 个受保护端点未认证均返回 401/403
[PASS] forged-token       垃圾/alg=none/错误密钥 token 均被拒绝
[PASS] default-jwt-secret 默认密钥不可用（JWT_SECRET 已配置）
[PASS] sqli-probe         SQLi 探针无 500/SQL 错误泄漏
[PASS] xss-reflection     XSS 载荷经 JSON 返回，非 HTML 上下文
[PASS] path-traversal     rule id 路径穿越被拒绝/无害化
[PASS] oversized-payload  10MB payload -> 422
[PASS] security-headers   nosniff/DENY/XSS-Protection/Referrer-Policy 均在位
[PASS] cors               恶意 Origin 未获 ACAO
[PASS] error-verbosity    畸形请求返回结构化 4xx，无堆栈泄漏
```

## 发现并修复的真实漏洞（均有修复前后实证）

### DAST-1 【高】i18n 错误中间件复制陈旧 Content-Length 导致所有错误响应损坏 — 已修复

- **位置**: `sentinel-api/app/main.py` `i18n_error_middleware`
- **现象（修复前实证）**: 任何产生 4xx/5xx 的请求（如未认证访问）连接被截断：
  ```
  curl -v http://127.0.0.1:8000/api/v1/rules
  < HTTP/1.1 401 Unauthorized
  < content-length: 30
  curl: (18) ... 0 bytes downloaded
  ```
  服务端日志: `h11._util.LocalProtocolError: Too much data for declared Content-Length`
- **根因**: 中间件重写 JSON body（本地化后长度变化）却用 `headers=dict(response.headers)`
  复制了原始 `content-length`。
- **影响**: 可用性/完整性 —— 所有错误响应（401/403/404/422…）body 损坏，客户端协议错误；
  依赖错误响应体的客户端（含前端错误处理）全部失效。
- **修复**: 新增 `_response_headers()`，复制响应头时剔除 `content-length`/`content-encoding`/
  `transfer-encoding`，由 JSONResponse 重新计算（`app/main.py`）。
- **修复后实证**: `unauth_rules=401 size=120`（body 完整返回）。

### DAST-2 【严重】POST /api/v1/rules 路径穿越 → 任意文件写 — 已修复

- **位置**: `sentinel-api/app/routers/rules.py` `create_rule`
- **现象（修复前实证，对未修复实例 127.0.0.1:8001 实测）**:
  ```
  POST /api/v1/rules  {"id": "../"*20 + "tmp/dast_prefix_traversal", ...}
  -> 200 {"status":"created","file_path":"custom/../../../../.../tmp/dast_prefix_traversal.yml"}
  逃逸到 /tmp 的文件存在: True   # 攻击者控制的 YAML 内容落盘
  ```
- **根因**: `rule.id` 无任何校验，直接拼入 `RULES_DIR / category / f"{rule.id...}.yml"`。
- **影响**: 已认证用户可在 API 进程权限内向任意路径写 YAML 内容文件（可覆盖配置、写
  webshell 落盘点、cron 目录等）。
- **修复（手术式）**:
  1. `Rule.id` 增加 `Field(pattern=r"^[A-Za-z0-9_-]+$")`（兼容现有 `R###` 与 Sigma UUID 风格）；
  2. category（来自 `attack.*` tag）经 `re.sub(r"[^A-Za-z0-9_-]", "", ...)` 消毒后再作目录名。
- **修复后实证**: DAST `path-traversal: PASS`（`../`、URL 编码变体均被 422 拒绝）。

### DAST-3 【高】默认 JWT 密钥可伪造任意身份 — 已修复（生产防线）

- **位置**: `sentinel-api/app/auth/jwt.py`，`SECRET_KEY = os.getenv("JWT_SECRET", "CHANGE_THIS_IN_PRODUCTION")`
- **现象（修复前实证）**: 首轮 DAST（未设 JWT_SECRET 的默认部署）中，用公开默认值
  `CHANGE_THIS_IN_PRODUCTION` 自签 HS256 token 即以 admin 身份通过全部鉴权检查。
- **修复**: 与既有 CORS 生产守卫同模式 —— `ENVIRONMENT=production` 且密钥为默认值时拒绝启动
  （`ValueError`）。
- **修复后实证**: 配置真实密钥的实例上 `default-jwt-secret: PASS`（默认密钥 token 被拒）；
  生产环境缺失 JWT_SECRET 将无法启动。
- **残余风险**: 开发模式下默认密钥仍可用（文档已标注 CHANGE_THIS_IN_PRODUCTION；部署模板
  `k8s/secret.yaml` 要求替换）。

## 其他观察（非缺陷）

- SQLi 探针到达 SQLAlchemy 层时以**绑定参数**传递（服务端日志可见 `WHERE import_tasks.task_id = ?`
  参数为 `' OR '1'='1`），无注入面。
- FastAPI 对非法 body 返回 422（含 10MB 超大 payload 的 schema 拒绝），符合规范。
- XSS 载荷存储/返回于 `application/json` 上下文且响应带 `nosniff`，无浏览器执行面。

## 复现

```bash
cd sentinel-api
PYTHONPATH=../sentinel-agents:. DATABASE_URL="sqlite+aiosqlite:////tmp/dast.db" \
  JWT_SECRET=<test-secret> python3 -m uvicorn app.main:app --port 8000 &
cd .. && JWT_SECRET=<test-secret> python3 scripts/security/dast_baseline.py
```
