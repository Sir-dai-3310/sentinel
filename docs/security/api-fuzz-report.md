# API 模糊测试报告 — Schemathesis

- **日期**: 2026-08-18
- **工具**: schemathesis 4.24.3（pip）
- **命令**:
  ```bash
  schemathesis run http://127.0.0.1:8000/openapi.json --checks all \
    -H "Authorization: Bearer <fuzz-token>" --max-examples 30 --request-timeout 10000
  ```
- **目标**: 本地真实运行的 Sentinel API（uvicorn + SQLite + JWT 鉴权），23/23 个 OpenAPI 操作入选。

## 结果演进

| 轮次 | 生成用例 | 唯一失败 | Server error | Response violates schema | Rejected compliant | Undocumented Content-Type | Undocumented status |
|---|---|---|---|---|---|---|---|
| 修复前 (seed …79270) | 1201 | 36 | 1 | 1 | 2 | 1 | 31 |
| 修复后复跑 | 1826 | 37→实质 2 类 | 1(同因) | **0** ✅ | 1(误报类) | **0** ✅ | 34(性质同上) |

> 复跑总失败数相近是覆盖率阶段随机生成差异所致（401/404 未声明类噪音 ±3）；关键类别（schema 违例、Content-Type 违例）**已清零**。

## 真实缺陷与修复

### FUZZ-1 【中】POST /api/v1/tenants 422 响应违反 OpenAPI 声明的 HTTPValidationError 模式 — 已修复

- **现象**: `POST /tenants {"name":"0","slug":""}` 返回
  `{"detail":"The request could not be validated."}`（string），而 schema 声明 422 的
  `detail` 为 array（FastAPI HTTPValidationError）。同时触发 "API rejected schema-compliant request"
  （`slug:""` 通过 schema 却被 handler 拒绝）。
- **根因**: slug 合法性在 **handler 内**用 `_SLUG_RE` 校验并抛字符串 detail 的 HTTPException(422)，
  绕过了 FastAPI 校验层；再经 i18n 中间件把字符串 detail 本地化，响应不再匹配声明。
- **修复**: `TenantCreate.slug` 增加 `pattern=_SLUG_RE.pattern`（`routers/tenants.py`），
  校验前移到 pydantic 层 → 标准 array detail，schema 合规。handler 内检查保留为防线。
- **修复后实证**:
  ```json
  {"detail":[{"type":"string_pattern_mismatch","loc":["body","slug"],
   "msg":"String should match pattern '^[a-z0-9][a-z0-9-]{1,62}$'",...}],
   "message":"The request could not be validated."}  // status=422
  ```

### FUZZ-2 【低】GET /metrics 声明的 Content-Type 与实际不符 — 已修复

- **现象**: `/metrics` 经 `include_in_schema=True` 进入 OpenAPI 且默认声明
  `application/json`，实际返回 `text/plain; version=1.0.0`（Prometheus 文本格式）。
- **修复**: `expose(..., include_in_schema=False)`（基础设施端点不进公开 schema）。
- **修复后实证**: "Undocumented Content-Type" 失败清零。

### FUZZ-3 【标注】POST /api/v1/analyze 空 log `{}` → 500（环境依赖，响应已脱敏）

- **根因链**: 本测试环境无 `OPENAI_API_KEY` → `sentinel_agents.graph.analyze_log` 实例化
  ChatOpenAI 抛 `OpenAIError: Missing credentials` → 全局异常处理器返回脱敏 500：
  `{"detail":"Internal server error.","message":...}`。
- **判定**: 响应**无任何内部信息泄漏**（无堆栈/无路径/无密钥）；属部署配置缺失而非输入校验缺陷。
  生产部署配置 LLM key 后不复现。状态语义（500 vs 503）留待后续 API 语义化专题。
- **关联建议（未改代码，保持手术纪律）**: `global_exception_handler` 当前不落日志，生产排障需
  依赖外部 APM；建议后续加 `logger.exception`（本任务不改）。

## 判定为噪音/误报的类别（说明）

| 类别 | 数量 | 判定说明 |
|---|---|---|
| 401 undocumented（负向用例摘除/伪造鉴权头） | ~21 | **正确行为**。FastAPI 不为依赖注入的 401 生成响应文档；为全部受保护端点补 401 响应当将是一次独立 API 文档治理（diff 面大，本任务不做）。 |
| 404 undocumented（`/rules/{id}`、`/tenants/{slug}` 等不存在资源） | ~5 | **正确行为**，同上属规范完备性噪音。 |
| 400 "error parsing the body"（畸形 JSON/multipart） | ~3 | starlette 对无法解析的 body 返回 400，FastAPI 生态常态，不计缺陷。 |
| logs/import "Expected UploadFile, received str" | 1 | schemathesis 以普通 form 字段（字符串）填充 `file` 部分部件，FastAPI 按声明的 `UploadFile` 正确 422 拒绝——multipart binary 序列化的已知工具交互问题，非服务端缺陷。 |
| POST /api/v1/auth/login 401 | 1 | 新登录端点对错误凭据返回 401，正确行为。 |

## 复现

```bash
pip3 install schemathesis
# 起 API（见 dast-report.md 复现节），然后：
schemathesis run http://127.0.0.1:8000/openapi.json --checks all \
  -H "Authorization: Bearer <token>" --max-examples 30
```
