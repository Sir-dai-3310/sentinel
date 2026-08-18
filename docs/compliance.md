# Compliance: GDPR & CCPA

How Sentinel processes personal data and the controls it provides for
data-subject rights and organisational obligations.

## What data is processed

| Data | Where | Why |
|------|-------|-----|
| Log events (may contain IPs, usernames, hostnames, command lines) | `analysis_results.log_event` | Security analysis (legitimate interest / legal obligation) |
| Analysis verdicts & metadata | `analysis_results` | Threat detection record |
| Audit trail of actions | `audit_logs` | Accountability (GDPR Art. 5(2)) |
| Data-subject identifier | `analysis_results.user_id` | Links records to a subject |

Personal data appearing in security telemetry (source IPs, account names,
process command lines) is the primary GDPR-relevant surface.

## Lawful-basis & principles support

- **Storage limitation** — `app/retention.py` deletes analysis results and
  audit logs after configurable windows (`ANALYSIS_RETENTION_DAYS`,
  `AUDIT_RETENTION_DAYS`). See "Retention" below.
- **Data minimisation / integrity & confidentiality** — field-level masking
  (`sentinel_agents/utils/masking.py`) redacts / hashes / truncates sensitive
  fields *before* persistence, so the database stores masked values, never
  clear-text secrets. Enable with `MASKING_ENABLED=true` + `config/masking.yml`.
- **Accountability** — every privacy-relevant action (export, erasure) writes
  an immutable `audit_logs` entry.

## Data-subject rights

| Right | Endpoint | Gate |
|-------|----------|------|
| Access / portability (Art. 15 / 20) | `GET /api/v1/privacy/export?subject=<id>` | admin |
| Erasure ("right to be forgotten", Art. 17) | `DELETE /api/v1/privacy/data?subject=<id>` | admin |

- The **subject** is the `user_id` recorded on analysis results.
- Export returns the full record set for the subject as JSON.
- Erasure removes the subject's analysis results; the *deletion action itself*
  is preserved in the audit log (so you can prove erasure happened without
  keeping the erased data).
- Both are tenant-scoped: in multi-tenant mode a subject's data is only
  touched within the caller's tenant.

## Retention

Defaults (override via env):

| Data | Default retention | Env |
|------|-------------------|-----|
| Analysis results | 30 days | `ANALYSIS_RETENTION_DAYS` |
| Audit logs | 90 days | `AUDIT_RETENTION_DAYS` |
| Sweep cadence | every 24 h | `RETENTION_SWEEP_INTERVAL_HOURS` |

## Masking capabilities

Strategies per field path (see `config/masking.yml`):

- `redact` — replace with `***`
- `hash` — truncated SHA-256 (stable pseudonym, supports correlation without
  storing the value)
- `partial` — IPv4 keeps first two octets (`192.168.***.***`); other strings
  keep a short prefix

## CCPA notes

The same export/erasure endpoints satisfy CCPA "right to know" and "right to
delete". Sentinel does not sell personal information; telemetry is processed
solely to provide the security service.

## Operational checklist

See `docs/compliance-checklist.md` for a deploy-time verification list.
