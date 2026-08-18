# SAST 报告 — Semgrep

- **日期**: 2026-08-18
- **工具**: semgrep 1.173.0（`pip3 install semgrep`，清华 PyPI 镜像；官方 PyPI 69.8MB wheel 多次超时，腾讯镜像该 wheel 哈希损坏）
- **扫描配置**: `--config auto`（semgrep.dev registry 在线拉取，559 条规则，433 文件）
- **命令**:
  ```bash
  semgrep scan --config auto --json -o semgrep-auto.json \
    --exclude=site --exclude=node_modules --exclude=target --exclude=sentinel-web/test-results
  ```

## 结果汇总

**51 findings（修复前）**: ERROR ×2，WARNING ×38，MEDIUM ×6（审计级），INFO ×5

| 类别 | 数量 | 判定 | 处置 |
|---|---|---|---|
| GitHub Actions 可变 action 标签 (`@v4` 等) | 29 | 真实（供应链卫生，低危） | 标注（见下） |
| release.yml `curl … \| sh` 安装 syft | 1 ERROR | 真实（供应链，低危） | 标注 |
| Sigma 规则误命中 insecure-websocket | 1 ERROR | **误报** | 说明 |
| nginx h2c smuggling | 2 | 误报（内网标准 WebSocket 反代） | 说明 |
| k8s 容器无 securityContext (allowPrivilegeEscalation) | 5 | 真实（加固缺口） | **修复 3 + 标注 2** |
| dependabot 无 cooldown | 6 MEDIUM | 真实（配置加固建议） | 标注 |

## 修复清单

### SAST-F1 k8s 一方镜像容器增加 securityContext（3 文件）

`k8s/api.yaml`、`k8s/agents.yaml`、`k8s/web.yaml` 容器级新增：

```yaml
securityContext:
  allowPrivilegeEscalation: false
  seccompProfile:
    type: RuntimeDefault
```

复扫实证（修复后 auto 规则集仅余 postgres/redis 两条）：

```
修复前: allow-privilege-escalation-no-securitycontext × 5
修复后: allow-privilege-escalation-no-securitycontext × 2 (postgres, redis)
```

**未对 postgres/redis 施加的原因（标注）**: 官方 `postgres:16-alpine` / `redis:7-alpine`
入口脚本以 root 启动后经 `su-exec`/`gosu`（setuid 二进制）降权，
`allowPrivilegeEscalation: false` 会导致容器启动失败；正确姿势是另配
`runAsUser` + `fsGroup` 的 PVC 方案，需集群实测，超出本次手术范围。

复扫另浮现 `run-as-non-root` ×5（此前被 securityContext 缺失掩盖）：一方镜像
Dockerfile 未声明非 root USER，建议后续在 Dockerfile 设 `USER` 后补
`runAsNonRoot: true`；postgres/redis 需配合 fsGroup 方案一并处理（同上）。

## 误报说明

1. **`rules/command_and_control/websocket_c2.yml:13` (ERROR, detect-insecure-websocket)**：
   该文件是 **Sigma 检测规则**（检测 C2 websocket 行为的内容数据），命中的 `ws://` 是被检测
   对象而非项目代码。误报。
2. **`docker/nginx.conf:19,32` (possible-h2c-smuggling)**：规则针对明文 HTTP/2 后端+Upgrade
   头组合；此处是 docker 内网标准 WebSocket 反向代理（`/ws` 端点正是产品功能），上游为
   受控 uvicorn，边缘 TLS 终止在 Ingress。误报/可接受。

## 标注项（真实存在、本任务不展开的治理建议）

- **29× 可变 action 标签**：`actions/checkout@v4` 等按 tag 引用。建议后续统一 pin 到 commit
  SHA（可用 dependabot 维持更新）。一次性 pin 29 处 diff 面大且需逐版本核对，超出手术范围。
- **release.yml 的 `curl | sh`（syft 安装）**：anchore 官方文档标准做法，运行时有临时 runner
  上。建议后续改用固定版本安装脚本 URL 或 `anchore/sbom-action`。
- **dependabot 无 cooldown**（6 处）：建议每个 ecosystem 增加 `cooldown: {default-days: 7}`，
  降低抢新版供应链投毒风险。

## 复现

```bash
pip3 install semgrep -i https://pypi.tuna.tsinghua.edu.cn/simple
semgrep scan --config auto   # 需可访问 semgrep.dev registry
```
