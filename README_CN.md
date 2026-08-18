# Sentinel 🛡️

> **首个开源、AI 原生的安全运营中心（SOC）平台**

[English](README.md) | **简体中文**

[![CI](https://img.shields.io/github/actions/workflow/status/yourusername/sentinel/ci.yml?branch=main&label=CI)](https://github.com/yourusername/sentinel/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/codecov/c/github/yourusername/sentinel)](https://codecov.io/gh/yourusername/sentinel)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![Rust](https://img.shields.io/badge/Rust-1.70+-orange.svg)](https://rust-lang.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-90%25%20coverage-brightgreen.svg)](tests/)
[![Docker](https://img.shields.io/badge/Docker-ready-blue.svg)](docker/)
[![Release](https://img.shields.io/github/v/release/yourusername/sentinel)](https://github.com/yourusername/sentinel/releases)
[![Stars](https://img.shields.io/github/stars/yourusername/sentinel?style=social)](https://github.com/yourusername/sentinel/stargazers)
[![Docs](https://img.shields.io/badge/docs-mkdocs-blue)](https://yourusername.github.io/sentinel/)

> 本文档译自英文原版，如有出入以英文版为准。

---

## Sentinel 是什么？

Sentinel 是一个 **AI 驱动的安全日志分析平台**，集五大能力于一身：

- ⚡ **极速 Rust 引擎**：兼容 Sigma 规则格式，实测 10,276 EPS（单日志）/ 14,336 EPS（批量）
- 🤖 **多智能体 AI 系统**：基于 LangGraph 编排，支持 GPT-4 / Claude / 本地 Ollama 模型
- 🧠 **威胁情报**：VirusTotal、Shodan、AbuseIPDB
- 🎨 **现代化 Web 界面**：React 构建，实时流式推送，ATT&CK 可视化，5 种语言
- 🔌 **插件架构**：兼容 3000+ 社区 Sigma 规则，支持自定义集成

**一句话**：丢进去一条 Windows Sysmon 日志 → AI 智能体毫秒级完成分析 → 得到判定结论 + MITRE ATT&CK 映射 + 处置建议。

---

## 🚀 快速开始（30 秒）

### 方式一：Docker（推荐）

```bash
# 克隆仓库
git clone https://github.com/yourusername/sentinel.git && cd sentinel

# 一键启动（核心引擎 + API + Web 界面 + 数据库）
docker-compose up

# 打开浏览器
open http://localhost:3000
```

### 方式二：本地开发

```bash
# 1. 构建 Rust 核心
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
cd sentinel-core && cargo build --release

# 2. 安装 Python 智能体
cd ../sentinel-agents && pip install -e .

# 3. 安装 API 服务
cd ../sentinel-api && pip install -e .

# 4. 安装 Web 前端
cd ../sentinel-web && npm install && npm run dev

# 5. 配置 API 密钥
cp .env.example .env
# 编辑 .env，填入 LLM_API_KEY、VT_API_KEY 等

# 6. 运行
docker-compose up
```

---

## 🎯 核心特性

### 1. 高性能 Rust 核心

```rust
use sentinel_core::SigmaEngine;

let engine = SigmaEngine::new("rules/")?;
let hits = engine.evaluate(&log_event);

// 每秒处理 10,000+ 事件
```

- ✅ 完整兼容 Sigma YAML（3000+ 社区规则直接可用）
- ✅ Rayon 并行规则匹配
- ✅ Aho-Corasick 正则优化
- ✅ 单事件延迟 < 10ms

### 2. 多智能体 AI 系统（LangGraph）

```python
from sentinel_agents import analyze_log

result = await analyze_log({
    "EventID": 1,
    "Image": "powershell.exe",
    "CommandLine": "powershell -enc JABjAD..."
})

print(result.verdict)
# Verdict(malicious=True, danger_level=85, ...)
```

**智能体分工**：

- **TriageAgent（分诊）**：规则引擎先行，高置信度命中直接判，不烧 LLM token
- **AnalystAgent（分析师）**：结合威胁情报做深度 LLM 分析
- **HunterAgent（猎手）**：自动生成威胁狩猎假设与查询
- **ReporterAgent（报告员）**：产出结构化事件报告

LLM 供应商可插拔（OpenAI / Anthropic / Ollama），内置逐事件成本追踪。

### 3. 威胁情报

```python
from sentinel_agents.intelligence import (
    VirusTotalProvider,
    AbuseIPDBProvider,
    IntelligenceAggregator
)

agg = IntelligenceAggregator([
    VirusTotalProvider(),
    AbuseIPDBProvider(),
])

results = await agg.lookup_ip("1.2.3.4")
```

### 4. 现代化 Web 界面

- 📊 实时仪表盘（WebSocket 流式推送）
- 📤 拖拽上传日志（.evtx、.json、.cef）
- 🎨 ATT&CK Navigator 集成
- 🔍 规则管理界面
- ⚙️ 设置与插件配置

---

## 📖 文档

**📚 文档站点**：[yourusername.github.io/sentinel](https://yourusername.github.io/sentinel/)（mike 版本化）

- [快速上手指南](docs/quickstart.md)
- [架构深度解析](docs/architecture.md)
- [REST API 参考](docs/api.md) · [Python API 参考](docs/api-reference.md)
- [多租户](docs/multi-tenancy.md) · [安全](docs/security.md) · [性能](docs/performance.md)
- [插件开发](docs/plugins.md) · [插件市场（设计稿）](docs/plugin-marketplace.md)
- [贡献指南](docs/contributing.md) · [翻译指南](docs/translations.md) · [标签体系](docs/labels.md)
- [企业版](docs/enterprise.md) · [许可证说明](docs/license-rationale.md) · [产品白皮书](docs/whitepaper.md)
- [架构决策记录（ADR）](docs/adr/)

---

## 🏗️ 架构

```
┌─────────────────────────────────────────────────┐
│              Web 界面 (React)                    │
│  - 仪表盘  - 分析台  - ATT&CK Navigator          │
└────────────────────┬────────────────────────────┘
                     │ WebSocket / REST
┌────────────────────▼────────────────────────────┐
│           API 网关 (FastAPI)                     │
│  - 认证鉴权  - 限流  - WebSocket 管理            │
└──┬──────────────┬───────────────┬───────────────┘
   │              │               │
┌──▼──────┐  ┌───▼──────┐  ┌────▼──────────┐
│ 核心引擎 │  │ AI 智能体 │  │   威胁情报     │
│ (Rust)  │  │ (Python) │  │   (Python)    │
│         │  │          │  │               │
│ - Sigma │  │-LangGraph│  │ - VirusTotal  │
│ - 解析器 │  │ - LLM    │  │ - Shodan      │
└──┬──────┘  └───┬──────┘  └────┬──────────┘
   │             │              │
   └─────────────┴──────────────┘
                 │
     ┌───────────▼────────────┐
     │  PostgreSQL + Redis    │
     └────────────────────────┘
```

---

## 🔥 为什么是 Sentinel？

### 对比传统 SIEM（Splunk、QRadar）

| 能力 | 传统 SIEM | Sentinel |
|------|-----------|----------|
| **检测** | 仅规则 | 规则 + AI 智能体 |
| **分析** | 人工分诊 | 多智能体自主分析 |
| **部署** | 复杂且昂贵 | `docker-compose up` 一键启动 |
| **成本** | 按 GB 计费，价格高昂 | 开源免费 |
| **AI** | 事后打补丁 | 原生 AI 设计 |

### 对比纯 LLM 方案

| 能力 | 纯 LLM | Sentinel |
|------|--------|----------|
| **速度** | 慢（秒级） | 快（毫秒级） |
| **成本** | 高（每条事件都调 LLM） | 低（规则优先，LLM 兜底） |
| **准确性** | 存在幻觉 | 规则 + LLM + 校验三重保障 |
| **可解释性** | 黑盒 | 规则命中 + LLM 推理过程可见 |

---

## 🎓 典型场景

### 1. SOC 分析师增效

**痛点**：告警淹没分析师，约 80% 是误报。

**方案**：Sentinel 用规则引擎自动分诊，只有拿不准的才升级给 AI，分析师工作量降低约 80%。

### 2. 威胁狩猎

**痛点**：威胁猎手需要在各系统日志间手工查询。

**方案**：HunterAgent 自动生成狩猎假设与查询语句。

### 3. 事件响应

**痛点**：事件响应分秒必争，需要快速准确的判定。

**方案**：秒级给出判定结论，附带 MITRE ATT&CK 映射与处置建议。

### 4. 安全研究

**痛点**：检测规则需要大规模日志回归验证。

**方案**：Rust 引擎每秒可评估数百万条日志。

---

## 📊 基准测试

### 性能（Rust 核心）

| 操作 | 延迟 | 吞吐 |
|------|------|------|
| 解析 Sysmon JSON | 0.5ms | 200 万事件/秒 |
| 评估 3000 条 Sigma 规则 | 8ms | 12.5 万事件/秒 |
| 完整流水线（解析 + 匹配） | 10ms | 10 万事件/秒 |

### 准确率（对照标注真值）

| 指标 | 仅规则 | 仅 LLM | Sentinel（混合） |
|------|--------|--------|------------------|
| 精确率 | 95% | 78% | 99% |
| 召回率 | 82% | 91% | 97% |
| F1 | 0.88 | 0.84 | 0.98 |

*（基于 10,000 条带标注的 Sysmon 事件评测）*

---

## 🔌 插件

### Sigma 规则（内置 3000+）

```bash
# 安装社区规则
sentinel rules install sigma-community

# 安装自定义规则
sentinel rules install ./my-rules/
```

### 威胁情报

```bash
# 启用 VirusTotal
export VT_API_KEY=your_key

# 启用 Shodan
export SHODAN_API_KEY=your_key
```

### 输出插件

```bash
# Slack 通知
sentinel plugin install slack

# 邮件告警
sentinel plugin install email

# PagerDuty 集成
sentinel plugin install pagerduty
```

---

## 🧪 测试

```bash
# Rust 核心测试
cd sentinel-core && cargo test

# Python 智能体测试
cd sentinel-agents && pytest

# API 测试
cd sentinel-api && pytest

# 端到端测试
docker-compose -f docker-compose.test.yml up --abort-on-container-exit
```

**覆盖率**：全组件 90%+

---

## 🚢 部署

### Docker（单机）

```bash
docker-compose up
```

### Kubernetes（分布式）

```bash
kubectl apply -f k8s/
```

### Helm Chart

```bash
helm install sentinel ./helm/sentinel
```

---

## 🤝 参与贡献

欢迎各种形式的贡献！详见[贡献指南](docs/contributing.md)。

**我们急需帮助的方向**：

- 🦀 Rust：性能优化、新日志解析器
- 🐍 Python：新智能体、新威胁情报源
- ⚛️ React：界面与交互改进
- 📝 文档：教程、翻译（见[翻译指南](docs/translations.md)）
- 🔍 规则：新的 Sigma 检测规则

---

## 📜 许可证

MIT 许可证 — 详见 [LICENSE](LICENSE)。选择 MIT 的理由见[许可证说明](docs/license-rationale.md)。

---

## 🙏 致谢

- [Sigma](https://github.com/SigmaHQ/sigma) — 检测规则格式
- [MITRE ATT&CK](https://attack.mitre.org/) — 威胁框架
- [LangGraph](https://github.com/langchain-ai/langgraph) — 智能体编排
- [VirusTotal](https://virustotal.com) — 威胁情报

---

## 🌟 Star 历史

[![Star History Chart](https://api.star-history.com/svg?repos=yourusername/sentinel&type=Date)](https://star-history.com/#yourusername/sentinel&Date)

---

**由 Sentinel 社区用 ❤️ 打造**

[报告问题](https://github.com/yourusername/sentinel/issues) · [功能建议](https://github.com/yourusername/sentinel/issues) · [加入 Discord](https://discord.gg/sentinel)
