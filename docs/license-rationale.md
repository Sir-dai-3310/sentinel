# License Rationale

Sentinel is licensed under the **MIT License**. This document explains why, and what it means for you.

## Why MIT

1. **Adoption-first**: Security tooling only works if people actually deploy it. MIT removes legal-review friction for enterprises, governments, and startups alike.
2. **Ecosystem compatibility**: Our key dependencies and adjacent projects (Sigma rules ecosystem, FastAPI, React) are permissively licensed. MIT keeps the combined work simple.
3. **Commercial use is a feature**: We explicitly want vendors to build on Sentinel, MSSPs to offer it as a service, and enterprises to embed it. Permissive licensing enables the sustainability paths described in [enterprise.md](enterprise.md).
4. **Contributor clarity**: No CLA. Contributions are inbound=outbound under MIT, per [docs/contributing.md](contributing.md).

## What MIT means for commercial users

- ✅ Use, modify, distribute, and sell — privately or publicly.
- ✅ No source-disclosure obligation for your modifications.
- ⚠️ You must retain the copyright notice and license text in copies or substantial portions.
- ⚠️ No warranty; no liability. If you need indemnification or an SLA, that's a commercial-support conversation (see [SUPPORT.md](https://github.com/sentinel-project/sentinel/blob/main/SUPPORT.md)).
- ❌ MIT grants no trademark rights. "Sentinel" branding may not be used to imply endorsement of a derived product.

## Relationship to SBOM and dependency licenses

Sentinel itself is MIT, but it **dynamically links and bundles third-party dependencies** with their own licenses. We ship a CycloneDX SBOM (`sbom/sentinel-cyclonedx.json`) with every release so you can audit exactly what's inside:

- **Rust crates**: mostly MIT/Apache-2.0 — check `Cargo.lock` via the SBOM.
- **Python packages**: verified via the SBOM; watch for GPL-family transitive deps if you redistribute.
- **Sigma community rules**: content in `rules/` may carry its own license (many are DRL — Detection Rule License). Rule content licensing is the responsibility of the rule author; check per-directory LICENSE files before redistributing rule packs.
- **Release artifacts** are cosign-signed; verify signatures before deploying in regulated environments (see [security.md](security.md)).

If your compliance process needs a full license report, generate one from the SBOM with any CycloneDX-compatible tool (e.g. `ort`, `cdxgen`, Dependency-Track).
