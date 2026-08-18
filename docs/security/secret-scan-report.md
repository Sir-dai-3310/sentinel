# Secret 扫描报告（gitleaks）

- **日期**: 2026-08-18
- **工具**: gitleaks 8.24.3（官方 release 单二进制，经 gh-proxy 镜像下载）
- **扫描命令**: `gitleaks detect --source . -v --report-path gitleaks-report.json --report-format json`（全量 git 历史，6 commits / 2.86 MB）

## 发现汇总

| # | 规则 | 文件 | 提交 | 判定 | 处置 |
|---|------|------|------|------|------|
| 1 | `kubernetes-secret-yaml` | `k8s/secret.yaml` | ac6a34d | **误报（占位符）** | 已在 `.gitleaks.toml` 按路径 allowlist |
| 2 | `private-key` | `sbom/cosign.key` | 6438c88 | **真实泄露** | 已从仓库移除 + `.gitignore` + 轮换建议 |

### 发现 1 — k8s/secret.yaml（误报，占位符）

文件内注释明确说明：所有值为 `base64("changeme")` 的 DUMMY 占位符，仅用于
`kubectl apply -k` 开箱即用，真实集群要求用 sealed-secrets / external-secrets 替换。
非真实凭据。已通过 `.gitleaks.toml` 的 path allowlist 抑制，避免 CI 重复报警。

### 发现 2 — sbom/cosign.key（真实泄露）

`-----BEGIN ENCRYPTED SIGSTORE PRIVATE KEY-----`，scrypt + nacl/secretbox 加密的
cosign 签名私钥，于 commit `6438c88`（"baseline: v1.3 actual state"）被提交入库。

- 虽为**口令加密**私钥，但私钥材料不应进入版本库（口令可离线爆破）。
- **修复**（本次执行）：
  1. `git rm sbom/cosign.key`（工作区与索引均已移除）；
  2. `.gitignore` 增加 `sbom/cosign.key`、`**/cosign.key`、`*.pem`、`*.key`；
  3. 全仓检索确认 `scripts/`、`.github/`、`docker/`、`sbom/` 无任何对该文件的引用，删除不影响构建/签名流程。
- **仍需人工跟进**：
  - 该私钥仍存在于 git 历史（6438c88）中。因基线纪律要求手术式变更，未做历史重写（filter-repo / BFG）。
  - **必须轮换**：重新生成 cosign 密钥对（`cosign generate-key-pair`），旧公钥 `sbom/cosign.pub` 对应的历史 SBOM 签名应视为不可信，重新签发。

## 复扫验证

修复 + allowlist 后复扫（`--config .gitleaks.toml`）：leaks found: **1**（即历史中的
cosign.key，属已记录并处置项；当前工作树 0 泄露）。

## CI 集成

`.github/workflows/ci.yml` 新增 `secret-scan` job（`gitleaks/gitleaks-action@v2`，
`fetch-depth: 0` 全历史扫描，使用仓库内 `.gitleaks.toml`），并加入 `docker` job 的
`needs` 门控。

## 复现命令

```bash
# 安装（Linux x64）
curl -sL https://github.com/gitleaks/gitleaks/releases/download/v8.24.3/gitleaks_8.24.3_linux_x64.tar.gz | tar xz
# 扫描
./gitleaks detect --source . -v --config .gitleaks.toml
```
