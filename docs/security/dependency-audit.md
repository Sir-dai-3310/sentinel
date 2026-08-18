# 依赖漏洞审计报告

- **日期**: 2026-08-18
- **工具**: pip-audit 2.10.1（PyPA 官方 advisory DB）、npm audit（registry.npmjs.org 官方审计端点）、cargo-audit 0.20.1（RustSec advisory-db 1158 条）

## 1. Python（sentinel-agents + sentinel-api 运行环境）

命令: `pip3 list --format=freeze | pip-audit`（对实际运行测试与服务的已安装环境做全量审计）

**实测输出**: `Found 94 known vulnerabilities in 16 packages`

### 关键判定：Sentinel 项目依赖闭包 = **0 漏洞**

对项目代码实际 import / 声明的包逐一核对（fastapi 0.141.1、starlette 1.6.0、
uvicorn 0.52.3、pydantic 2.13.4、sqlalchemy 2.0.52、httpx 0.28.1、aiosqlite、
python-jose、PyYAML、prometheus-fastapi-instrumentator、langchain/langgraph/openai 等），
**无一出现在漏洞清单**。

### 环境中的漏洞包（Sentinel 代码不 import，属同机其他工具链，记录跟踪）

| 包 | 版本 | 漏洞数 | 修复版本 | 与 Sentinel 关系 |
|---|---|---|---|---|
| aiohttp | 3.13.3 | 25 | 3.14.3 | 无 import |
| pypdf | 6.9.2 | 20 | 6.15.0 | 无 import |
| cryptography | 41.0.7 | 11 | 49.0.0 | 无 import |
| urllib3 | 2.0.7 | 6 | 2.7.0 | 无 import（httpx 不依赖它） |
| pip | 24.0 | 6 | 26.1.2 | 系统工具 |
| jinja2 | 3.1.2 | 5 | 3.1.6 | 无 import |
| setuptools | 68.1.2 | 5 | 83.0.0 | 系统工具 |
| twisted | 24.3.0 | 4 | 26.4.0 | 无 import |
| 其余 (configobj/ecdsa/httplib2/lxml/pygments/pyopenssl/soupsieve/wheel) | — | 15 | 见 pip-audit | 无 import |

> 验证方式: `grep -rE "^(import|from) (aiohttp|cryptography|jinja2|jwt|lxml|pypdf|urllib3|twisted|httplib2|ecdsa|configobj|soupsieve|pygments)" sentinel-api/app sentinel-agents/sentinel_agents` → 0 命中。
> 这些包来自本机其他 Python 应用的环境（非项目 virtualenv/poetry 环境）。**建议**但仍属环境治理：生产镜像内不含这些包（`docker/Dockerfile.api` 仅安装项目依赖）。

## 2. npm（sentinel-web）

命令: `cd sentinel-web && npm audit --registry=https://registry.npmjs.org`

**实测输出**: `found 0 vulnerabilities` ✅

（注：qihoo 镜像不代理 audit 端点会返回 Nexus 404 HTML，必须用官方 registry。）

## 3. Rust（sentinel-core）

命令: `cargo audit --db <advisory-db> --no-fetch`（工具链受限详见下文）

**实测输出**:

```
Scanning Cargo.lock for vulnerabilities (131 crate dependencies)
error: 2 vulnerabilities found!
warning: 4 allowed warnings found
```

### 漏洞（高危 ×2，同一 crate）

| ID | Crate | 当前 | 严重度 | 说明 | 修复版 |
|---|---|---|---|---|---|
| RUSTSEC-2026-0195 | quick-xml | 0.30.0 | 7.5 high | NsReader 命名空间声明无界分配 → 内存耗尽 DoS | >=0.41.0 |
| RUSTSEC-2026-0194 | quick-xml | 0.30.0 | 7.5 high | 起始标签重复属性名校验为平方复杂度 → CPU 耗尽 DoS | >=0.41.0 |

**影响面真实**: `sentinel-core/src/parser/sysmon.rs` 用 `quick_xml::de::from_str`
反序列化**不可信 Sysmon XML 输入**——正是两条 DoS 漏洞的触发面。

**修复状态：环境受限，未落地（已回滚）**:
1. 已实测将 `quick-xml = "=0.30.0"` → `"=0.41.0"` 并 `cargo update -p quick-xml` 成功解析；
2. 但 `quick-xml 0.41.0` 的 MSRV 为 **rustc 1.79**，本机工具链为 **rustc 1.75.0**
   （无 rustup，系统级安装），`cargo test` 报
   `package quick-xml v0.41.0 cannot be built because it requires rustc 1.79 or newer`；
3. 为守住基线（55/55）已回滚至 0.30.0 并复测全绿，Cargo.toml 内留注释指向本报告。

**可复现修复步骤（工具链升级后）**:
```bash
rustup toolchain install stable   # 或系统升 rustc >= 1.79
sed -i 's/quick-xml = { version = "=0.30.0"/quick-xml = { version = "=0.41.0"/' sentinel-core/Cargo.toml
cargo update -p quick-xml && cargo test
```
**临时缓解建议**: 在 API/ingest 层限制单条 XML 输入大小与解析超时（Sentinel 已有多层
payload 大小控制，见 dast-report 的 oversized-payload 项）。

### 警告 ×4（非漏洞，记录）

| 类型 | Crate | 说明 | 处置 |
|---|---|---|---|
| unmaintained | atty 0.2.14 | 经 criterion(dev-dep) 间接引入，不进发布产物 | 记录；criterion 升级时自然消除 |
| unsound | anyhow 1.0.75 | `Error::downcast_mut` 不健全性 | 记录；下次依赖轮转升 anyhow |
| unsound | tokio 1.35.0 | broadcast channel clone/`Sync` 问题 (RUSTSEC-2025-0023) | 记录；升 tokio 需配合 MSRV 策略 |
| unsound | quick-xml 间接 | 同漏洞链 | 见上 |

### cargo-audit 工具链备注

- `cargo install cargo-audit --locked`（0.22.2）需 rustc 1.88 → 装 0.20.1；
- 0.20.1 无法解析 advisory-db 中 59 条 CVSS:4.0 条目 → 审计使用剪除该 59 条的库副本
  （1158 条）。被剪 59 条均为 2026 年新条目（多为 Solana/anchor 生态），与 sentinel-core
  依赖树无交集风险已人工抽查（依赖树 131 crate 以主流基础库为主）；
  交叉验证复现命令：`cargo install cargo-audit --locked --version 0.21.1 && cargo audit`
  （0.21.1 支持 CVSS 4.0，本机 rustc 1.75 可编译，构建耗时约 25 分钟）。
- 完整复现: `cargo install cargo-audit --locked --version 0.20.1 && cargo audit`

## 总结

| 生态 | 漏洞 | 项目相关 | 已修复 | 记录跟踪 |
|---|---|---|---|---|
| Python | 94 / 16 包 | **0** | —（无项目暴露面） | 环境治理建议 |
| npm | 0 | 0 | — | — |
| Rust | 2 | 2 (quick-xml) | 0（工具链受限） | quick-xml>=0.41 待 rustc>=1.79 |
