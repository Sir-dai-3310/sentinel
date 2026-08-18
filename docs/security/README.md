# 安全测试总报告 — Sentinel v1.2（2026-08-18）

本目录汇总 v1.2 深度增强安全专项的全部测试与修复。各分项报告：

| 报告 | 工具 | 结论 |
|---|---|---|
| [sast-report.md](sast-report.md) | Semgrep 1.173.0 (`--config auto`, 559 规则) | 51 发现：修复 3（k8s securityContext），误报 3，其余标注治理 |
| [secret-scan-report.md](secret-scan-report.md) | gitleaks 8.24.3（全量 git 历史） | 2 发现：1 真实泄露（cosign 私钥，已移除+轮换建议），1 占位符误报 |
| [dast-report.md](dast-report.md) | 自写 OWASP API Top10 baseline（ZAP 环境不可用，见报告） | 10 检查修复后全 PASS；修复 3 个真实漏洞（含 1 严重） |
| [api-fuzz-report.md](api-fuzz-report.md) | Schemathesis 4.24.3 `--checks all` | 修复 2（422 schema 违例、/metrics Content-Type），标注 5xx/噪音 |
| [dependency-audit.md](dependency-audit.md) | pip-audit 2.10.1 / npm audit / cargo-audit 0.20.1 | Python 项目闭包 0 漏洞、npm 0 漏洞、Rust quick-xml 高危×2（工具链受限，记录跟踪） |

## 一、真实漏洞修复清单（全部带修复前后实证）

| # | 严重度 | 问题 | 位置 | 修复 |
|---|---|---|---|---|
| DAST-2 | **严重** | 已认证用户经 `POST /rules` 的 `rule.id` 路径穿越，任意路径写文件（实证写入 /tmp 成功） | `sentinel-api/app/routers/rules.py` | `Rule.id` 加 `pattern=^[A-Za-z0-9_-]+$`；category 消毒 |
| DAST-1 | 高 | i18n 中间件复制陈旧 `Content-Length`，**所有错误响应 body 损坏**（h11 协议错误） | `sentinel-api/app/main.py` | `_response_headers()` 剔除 framing 头 |
| DAST-3 | 高 | 默认 `JWT_SECRET` 可伪造任意身份（默认部署实证） | `sentinel-api/app/auth/jwt.py` | 生产模式默认值拒绝启动 |
| FUZZ-1 | 中 | `POST /tenants` 422 响应违反 OpenAPI schema（handler 级字符串 detail） | `sentinel-api/app/routers/tenants.py` | slug 校验前移到 pydantic `pattern` |
| FUZZ-2 | 低 | `/metrics` 声明 Content-Type 与实际不符 | `sentinel-api/app/main.py` | `include_in_schema=False` |
| SECRET-1 | 高 | cosign 加密私钥入库（历史 commit 6438c88） | `sbom/cosign.key` | 移除 + .gitignore + 轮换要求（历史重写留待决策） |
| SAST-F1 | 中 | 一方 k8s 容器无 securityContext | `k8s/{api,agents,web}.yaml` | `allowPrivilegeEscalation: false` + seccomp |

## 二、残余风险（已知未闭环）

1. **quick-xml 0.30.0 两条 7.5 分 DoS**（解析不可信 Sysmon XML）：修复版 ≥0.41 需
   rustc ≥1.79，本机 1.75 且基线不可破 → 已回滚、Cargo.toml 留注释、报告给出升级步骤。
2. **git 历史中的 cosign.key**：未做 filter-repo 历史重写（手术纪律），**必须轮换密钥对**。
3. **CI 供应链卫生**：29 处可变 action tag、release.yml `curl|sh`、dependabot 无 cooldown —— 标注待治理。
4. **OpenAPI 401/404 未声明**：正确行为但规范不完备；建议独立 API 文档治理任务。
5. **postgres/redis 容器**未加 `allowPrivilegeEscalation: false`（官方镜像入口依赖 setuid，需 fsGroup 方案 + 集群实测）。
6. `global_exception_handler` 不落服务端日志（排障建议，未改）。

## 三、CI 集成

`.github/workflows/ci.yml` 新增 **secret-scan job**（gitleaks-action@v2 + 仓库内
`.gitleaks.toml` allowlist），并挂入 docker job 的 needs 门控。

## 四、回归验证（最终状态）

| 层 | 命令 | 结果 |
|---|---|---|
| Rust | `cd sentinel-core && cargo test` | **55/55 通过** |
| Python agents | `cd sentinel-agents && python3 -m pytest tests/ -q` | 208 通过 / 1 失败（**非本任务引入**，见下） |
| API | `cd sentinel-api && PYTHONPATH=../sentinel-agents:. python3 -m pytest tests/ -q` | **71/71 通过**（含全部安全修复后） |

> agents 层 1 个失败 `test_additional.py::test_analyze_log_integration`：断言旧的
> dict 返回契约；并发提交的 `81d8e29`（SDK/CLI 任务）有意将 `analyze_log` 改为返回
> `IncidentState`（修复 /analyze 的 AttributeError），该测试需由对应任务更新。
> 本任务改动不涉及 sentinel-agents 目录（git 可证）。

## 五、环境受限项

| 项 | 限制 | 已采用的替代/复现路径 |
|---|---|---|
| OWASP ZAP | 无 docker daemon、Java 下载不可行 | 自写 `scripts/security/dast_baseline.py`（httpx）等价覆盖 |
| quick-xml 升级 | rustc 1.75 < 1.79，无 rustup | 见 dependency-audit.md 复现步骤 |
| cargo-audit 0.22.2 | 需 rustc 1.88 | 使用 0.20.1 + 剪除 CVSS4.0 条目的 advisory-db（1158 条） |
| semgrep 官方 PyPI | 69.8MB wheel 多次超时；腾讯镜像该 wheel 哈希损坏 | 清华镜像安装成功 |
| npm audit | qihoo 镜像无 audit 端点（Nexus 404） | 官方 registry 实测通过 |

## 六、复现命令清单

```bash
# SAST
semgrep scan --config auto
# Secret
gitleaks detect --source . -v --config .gitleaks.toml
# DAST（先起 API，见 dast-report.md）
JWT_SECRET=<secret> python3 scripts/security/dast_baseline.py
# Fuzz
schemathesis run http://127.0.0.1:8000/openapi.json --checks all -H "Authorization: Bearer <token>"
# 依赖
pip-audit
cd sentinel-web && npm audit --registry=https://registry.npmjs.org
cargo audit   # 或 --db <pruned-db> --no-fetch
```
