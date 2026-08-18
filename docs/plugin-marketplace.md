# Plugin Marketplace (Design)

Sentinel's plugin architecture (see [plugins.md](plugins.md)) already supports community extensions. This document sketches the distribution and discovery layer — a lightweight "marketplace" — on top of it.

## Goals

- Discover plugins without leaving the CLI/UI.
- Install pinned, integrity-verified plugin versions.
- Give plugin authors a publication path that doesn't require PRs to the main repo.

## Proposed directory structure

A central **registry repository** (`sentinel-plugins/registry`) holding one manifest per plugin:

```
registry/
  index.json                  # generated: name -> latest version + checksum
  plugins/
    slack/
      manifest.toml           # metadata, versions, checksums
      README.md
    pagerduty/
      manifest.toml
    my-company-siem/
      manifest.toml
```

### `manifest.toml`

```toml
[plugin]
name = "slack"
type = "output"              # output | intelligence | parser | rules
description = "Post incident summaries to Slack"
author = "sentinel-community"
license = "MIT"
repository = "https://github.com/example/sentinel-slack"

[[version]]
version = "1.2.0"
sentinel_compat = ">=1.0, <2.0"
artifact = "https://github.com/example/sentinel-slack/releases/download/v1.2.0/slack-1.2.0.tar.gz"
sha256 = "…"
```

## Distribution mechanisms

| Tier | Mechanism | Trust |
|------|-----------|-------|
| **Built-in** | Ships in `sentinel-agents/sentinel_agents/` | Full (repo CI + review) |
| **Verified community** | Registry + sha256 + maintainer review | High |
| **Unverified** | `sentinel plugin install <git-url>` with explicit `--unverified` flag | User's risk |

## CLI flow (target UX)

```bash
sentinel plugin search slack          # query registry index
sentinel plugin install slack@1.2.0   # fetch, verify sha256, install
sentinel plugin list                  # installed + versions
sentinel plugin update --all
```

## Security model

1. Registry PRs require maintainer review (same bar as code PRs).
2. Checksums are pinned at review time; installs fail closed on mismatch.
3. Signed artifacts (cosign) are the planned upgrade path for Verified tier.
4. Plugins run in-process today — treat them as trusted code. Sandboxing (WASM or subprocess isolation) is a future hardening track.

## Status

**Design stage.** The registry format above is the working draft; feedback via GitHub Discussions. The plugin *runtime* is stable — see [plugins.md](plugins.md) to write one today.
