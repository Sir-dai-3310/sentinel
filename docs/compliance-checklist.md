# Compliance Checklist & Best Practices

Deploy-time verification list for GDPR/CCCA readiness. Check each item and
record evidence (config value, test run, or screenshot).

## Data mapping & minimisation

- [ ] Inventory of personal fields in ingested logs is documented.
- [ ] `config/masking.yml` covers all personal fields (usernames, IPs, emails,
      command lines that may embed secrets).
- [ ] `MASKING_ENABLED=true` is set in production so storage is masked.
- [ ] Unneeded fields are dropped at ingest via `config/preprocessing.yml`
      filters rather than stored.

## Retention & storage limitation

- [ ] `ANALYSIS_RETENTION_DAYS` is set to the business-justified window.
- [ ] `AUDIT_RETENTION_DAYS` meets accountability requirements.
- [ ] The retention sweep is running (check logs for `🧹 Retention sweep`).
- [ ] Backups honour retention: `RETENTION_DAYS` in `scripts/backup.sh` prunes
      old dumps (erased data must age out of backups too).

## Data-subject rights

- [ ] `GET /api/v1/privacy/export?subject=` returns a subject's records.
- [ ] `DELETE /api/v1/privacy/data?subject=` erases them.
- [ ] Both endpoints are admin-gated (verify a non-admin gets 403).
- [ ] Erasure/export actions appear in `audit_logs`.

## Security of processing

- [ ] Transport is TLS-terminating; `ENVIRONMENT=production` sets HSTS/CSP.
- [ ] JWT secret (`JWT_SECRET`) is rotated from the default.
- [ ] RBAC restricts analyze/export/delete to the intended roles.
- [ ] Rate limiting is on (optionally Redis-backed — `docs/redis-usage.md`).
- [ ] DB backups are encrypted at rest and access-controlled.

## Accountability & governance

- [ ] A Data Protection Officer / owner is named.
- [ ] Records of processing activities (RoPA) reference `docs/compliance.md`.
- [ ] A breach-notification runbook exists (`docs/disaster-recovery.md`).
- [ ] Sub-processors (LLM providers) are listed and DPAs signed where required.

## Best practices

- Prefer `hash` masking for identifiers you still need to correlate, `redact`
  for values you never need again, `partial` for network scoping.
- Keep retention as short as the detection use-case allows; longer is not safer.
- Test the erasure path quarterly with a synthetic subject, then confirm the
  audit log proves the deletion.
- Review `config/masking.yml` whenever new log sources are onboarded.
